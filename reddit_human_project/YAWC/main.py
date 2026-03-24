"""
YAWC Backend v4 — Intent Router + Multi-Platform Spider Dispatcher
FastAPI + Async Subprocess + Token Streaming + Mixed-Media Synthesis

New in V4:
  - LLM Intent Router: classifies query → VIDEO | IMAGE | TEXT
  - Modular spider dispatch: youtube_spider, image_spider, text_spider
  - Mixed-media prompt builder: [YOUTUBE_EMBED: url], ![alt](url), [N] citations
  - Source platform tagging: YouTube, StackOverflow, Pinterest, Reddit, Quora

Install:
    pip install fastapi uvicorn scrapy scrapy-playwright \
                google-generativeai anthropic sse-starlette python-dotenv
    playwright install chromium

Env vars (.env):
    GEMINI_API_KEY=...
    ANTHROPIC_API_KEY=...
    LLM_PROVIDER=gemini   # or "anthropic"
"""

import os
import sys
import json
import asyncio
import time
import uuid
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

load_dotenv()

# ─── LLM Setup ────────────────────────────────────────────────────────────────
GEMINI_KEY    = os.getenv("GEMINI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER  = os.getenv("LLM_PROVIDER", "gemini").lower()

if LLM_PROVIDER == "gemini" and GEMINI_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    _gemini_model = genai.GenerativeModel("gemini-2.5-flash")

elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
    import anthropic as _anthropic
    _anthropic_client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="YAWC API", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for Windows subprocess execution
_thread_pool = ThreadPoolExecutor(max_workers=4)

# ─── Intent Types ─────────────────────────────────────────────────────────────
IntentType = Literal["VIDEO", "IMAGE", "TEXT"]

# Spider file map — maps intent → spider filename
SPIDER_MAP: dict[IntentType, str] = {
    "VIDEO": "youtube_spider.py",
    "IMAGE": "image_spider.py",
    "TEXT":  "text_spider.py",
}

# Default k (number of results) per intent
K_MAP: dict[IntentType, dict[str, int]] = {
    "VIDEO": {"quick": 3, "deep": 6},
    "IMAGE": {"quick": 5, "deep": 10},
    "TEXT":  {"quick": 8, "deep": 30},
}

# ─── LLM Intent Router ────────────────────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """You are a query intent classifier. Given a user search query, classify it into exactly ONE of these three categories:

VIDEO  — The user wants tutorials, how-to videos, gameplay footage, video reviews, or explicitly mentions "video", "watch", "YouTube".
IMAGE  — The user wants visual inspiration, photos, diagrams, design ideas, wallpapers, or explicitly mentions "picture", "image", "photo", "inspiration".
TEXT   — Everything else: general questions, coding help, discussions, comparisons, recommendations, news, opinions.

Reply with ONLY one word: VIDEO, IMAGE, or TEXT. No explanation."""


def _classify_intent_blocking(query: str) -> IntentType:
    """
    Synchronous LLM call to classify query intent.
    Designed to be run inside an executor (non-blocking for asyncio).
    Falls back to TEXT on any error.
    """
    prompt = f"{INTENT_SYSTEM_PROMPT}\n\nQuery: {query}"

    try:
        if LLM_PROVIDER == "gemini" and GEMINI_KEY:
            response = _gemini_model.generate_content(prompt)
            raw = response.text.strip().upper()
        elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
            message = _anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip().upper()
        else:
            return "TEXT"  # No LLM configured

        # Validate — only accept exact known intents
        if raw in ("VIDEO", "IMAGE", "TEXT"):
            return raw  # type: ignore[return-value]
        return "TEXT"

    except Exception as e:
        print(f"[YAWC] Intent classification failed: {e}. Defaulting to TEXT.", flush=True)
        return "TEXT"


async def classify_intent(query: str) -> IntentType:
    """Non-blocking wrapper around _classify_intent_blocking."""
    loop = asyncio.get_event_loop()
    intent: IntentType = await loop.run_in_executor(
        _thread_pool,
        _classify_intent_blocking,
        query,
    )
    print(f"[YAWC] Intent: '{query}' → {intent}", flush=True)
    return intent


# ─── Cross-Platform Async Spider Runner ──────────────────────────────────────

def _run_spider_blocking(cmd: list[str]) -> None:
    """Blocking subprocess call — safe inside a thread pool executor."""
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode not in (0, 1):
        print(f"[YAWC] Spider exited with code {result.returncode}", flush=True)


async def scrape_async(
    query: str,
    k: int,
    spider_file: str,
) -> list[dict]:
    """
    Launch the appropriate Scrapy spider as a non-blocking subprocess.
    Results land in a temp JSON file, then loaded into memory.

    All spiders receive:
        -a query=<query>
        -a k=<k>
    and write output to a temp file via -o flag.
    """
    import tempfile
    temp_dir  = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, f"yawc_{uuid.uuid4().hex}.json")
    null_dev  = "NUL" if platform.system() == "Windows" else "/dev/null"

    cmd = [
        sys.executable, "-m", "scrapy", "runspider",
        spider_file,
        "-a", f"query={query}",
        "-a", f"k={k}",
        "-o", temp_file,
        "--logfile", null_dev,
    ]

    print(
        f"[YAWC] Launching {spider_file} | query={query!r} k={k} "
        f"platform={platform.system()}",
        flush=True,
    )

    if platform.system() == "Windows":
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_thread_pool, _run_spider_blocking, cmd)
    else:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def drain_stderr():
            async for line in process.stderr:
                decoded = line.decode(errors="replace").rstrip()
                if decoded:
                    print(f"[SPIDER] {decoded}", flush=True)

        await asyncio.gather(drain_stderr(), process.wait())

    results = []
    if os.path.exists(temp_file):
        try:
            with open(temp_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                results = raw if isinstance(raw, list) else [raw]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[YAWC] Could not parse results: {e}", flush=True)
        finally:
            try:
                os.remove(temp_file)
            except OSError:
                pass
    else:
        print(f"[YAWC] ⚠ Temp file not found: {temp_file}", flush=True)

    print(f"[YAWC] Done. {len(results)} results from {spider_file}.", flush=True)
    return results


# ─── Mixed-Media Prompt Builders ──────────────────────────────────────────────

def _build_video_prompt(query: str, posts: list[dict], mode: str) -> str:
    """
    Video mode: instructs LLM to embed YouTube iframes via [YOUTUBE_EMBED: url].
    Each post has: url, embed_url, title, description, channel, views.
    """
    context_parts = []
    for i, p in enumerate(posts, 1):
        context_parts.append(
            f"[{i}] YouTube | Channel: {p.get('channel', 'Unknown')}\n"
            f"Title: {p.get('title', '')}\n"
            f"Views: {p.get('views', 'N/A')}\n"
            f"Description: {(p.get('description') or '')[:400]}\n"
            f"Watch URL: {p.get('url', '')}\n"
            f"Embed URL: {p.get('embed_url', '')}"
        )
    context = "\n\n".join(context_parts)

    depth = (
        "Provide a concise 2-paragraph overview."
        if mode == "quick"
        else "Provide a structured report: Summary, Key Takeaways per video, Best For, and Notable Differences."
    )

    return f"""You are YAWC, an AI that synthesizes YouTube search results into helpful answers.

USER QUESTION: {query}

YOUTUBE VIDEOS (reference by number inline, e.g. [1] [2]):
{context}

Instructions:
- {depth}
- For EACH video you recommend, output a YouTube embed tag on its own line in this exact format:
  [YOUTUBE_EMBED: <embed_url>]
  Replace <embed_url> with the actual Embed URL from the video data above.
- After the embed tag, write the video title and a one-sentence reason to watch it.
- Use inline citations [N] when referencing video content in your prose.
- Do NOT invent information. Only use data from the provided videos.

ANSWER:"""


def _build_image_prompt(query: str, posts: list[dict], mode: str) -> str:
    """
    Image mode: instructs LLM to render images via standard markdown ![alt](url).
    Each post has: url, image_url, alt, source, width, height.
    """
    context_parts = []
    for i, p in enumerate(posts, 1):
        context_parts.append(
            f"[{i}] Source: {p.get('source', 'image')}\n"
            f"Alt: {p.get('alt', '')}\n"
            f"Image URL: {p.get('image_url', '')}\n"
            f"Page URL: {p.get('url', '')}"
        )
    context = "\n\n".join(context_parts)

    depth = (
        "Write a brief 1-paragraph visual summary."
        if mode == "quick"
        else "Write a structured visual report: Overview, Style Analysis, Color Palette Notes, and Usage Recommendations."
    )

    return f"""You are YAWC, an AI that synthesizes visual search results into helpful answers.

USER QUESTION: {query}

IMAGES FOUND (reference by number inline, e.g. [1] [2]):
{context}

Instructions:
- {depth}
- For EACH image you discuss, embed it using standard markdown on its own line:
  ![<alt text>](<image_url>)
  Use the exact Image URL from the data above.
- Use inline citations [N] when referencing images in prose.
- Comment on visual style, color, composition where relevant.
- Do NOT invent alt text — use the provided alt or a concise descriptive phrase.

ANSWER:"""


def _build_text_prompt(query: str, posts: list[dict], mode: str) -> str:
    """
    Text mode: Reddit / StackOverflow / Quora synthesis with [N] inline citations.
    Each post has: url, title, body, subreddit/platform, score.
    """
    context_parts = []
    for i, p in enumerate(posts, 1):
        platform_label = p.get("subreddit") or p.get("platform", "web")
        body = (p.get("body") or "").strip() or "(no body text)"
        context_parts.append(
            f"[{i}] {platform_label} | ↑{p.get('score', 0)}\n"
            f"Title: {p.get('title', '')}\n"
            f"Body: {body[:600]}"
        )
    context = "\n\n".join(context_parts)

    if mode == "quick":
        instructions = (
            "Answer the question directly and concisely (2-4 paragraphs). "
            "Cite sources inline using [N] notation after each claim."
        )
    else:
        instructions = (
            "Produce a structured deep research report with these exact sections:\n\n"
            "## Summary\n2-3 sentence overview.\n\n"
            "## Key Themes\nThe 3-5 most recurring themes. Cite with [N].\n\n"
            "## Pros & Cons\n**Pros**: ...\n**Cons**: ...\n\n"
            "## Reddit Consensus\nOverall community verdict.\n\n"
            "## Notable Opinions\n1-2 standout or contrarian takes."
        )

    return f"""You are YAWC, an AI that synthesizes web discussions into clear answers.

USER QUESTION: {query}

POSTS (reference by number inline, e.g. [1][3]):
{context}

Instructions:
- {instructions}
- Be honest if posts don't fully answer the question.
- Do NOT invent information beyond what the posts contain.

ANSWER:"""


def build_prompt(
    query: str,
    posts: list[dict],
    intent: IntentType,
    mode: str,
) -> str:
    if intent == "VIDEO":
        return _build_video_prompt(query, posts, mode)
    if intent == "IMAGE":
        return _build_image_prompt(query, posts, mode)
    return _build_text_prompt(query, posts, mode)


# ─── LLM Streaming ────────────────────────────────────────────────────────────

async def stream_gemini(prompt: str) -> AsyncIterator[str]:
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _gemini_model.generate_content(prompt, stream=True),
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text


async def stream_anthropic(prompt: str) -> AsyncIterator[str]:
    loop = asyncio.get_event_loop()

    def _create_stream():
        return _anthropic_client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

    stream_ctx = await loop.run_in_executor(None, _create_stream)
    with stream_ctx as stream:
        for text in stream.text_stream:
            yield text


async def stream_llm(prompt: str) -> AsyncIterator[str]:
    if LLM_PROVIDER == "gemini" and GEMINI_KEY:
        async for token in stream_gemini(prompt):
            yield token
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
        async for token in stream_anthropic(prompt):
            yield token
    else:
        msg = "[No LLM configured] Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env"
        for word in msg.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)


# ─── Source Normalizer ────────────────────────────────────────────────────────

def normalize_sources(posts: list[dict], intent: IntentType) -> list[dict]:
    """
    Normalize scraped results into a consistent source format for the frontend.
    Adds a `platform` field the UI uses to render the correct badge icon.
    """
    sources = []
    for i, p in enumerate(posts, 1):
        url = p.get("url", "")

        # Infer platform from URL if not explicitly set
        if intent == "VIDEO":
            pl = "YouTube"
        elif intent == "IMAGE":
            if "pinterest" in url:
                pl = "Pinterest"
            elif "unsplash" in url:
                pl = "Unsplash"
            else:
                pl = "Images"
        else:
            if "stackoverflow" in url:
                pl = "StackOverflow"
            elif "quora" in url:
                pl = "Quora"
            else:
                pl = p.get("subreddit") or "Reddit"

        source: dict = {
            "index":    i,
            "title":    p.get("title", ""),
            "url":      url,
            "platform": pl,
            "score":    p.get("score", p.get("views", p.get("likes", 0))),
        }

        # Extra fields for video/image
        if intent == "VIDEO":
            source["embed_url"] = p.get("embed_url", "")
            source["channel"]   = p.get("channel", "")
            source["thumbnail"] = p.get("thumbnail", "")
        elif intent == "IMAGE":
            source["image_url"] = p.get("image_url", "")
            source["alt"]       = p.get("alt", "")

        sources.append(source)

    return sources


# ─── SSE Search Endpoint ──────────────────────────────────────────────────────

@app.get("/api/search")
async def search_stream(
    q:    str = Query(..., min_length=2),
    mode: str = Query("quick"),
) -> EventSourceResponse:
    """
    Streams search progress + LLM tokens via SSE.

    SSE event types:
      intent  → { intent: "VIDEO"|"IMAGE"|"TEXT" }
      status  → { message: str }
      sources → { sources: [...], intent: str }
      token   → { token: str }
      done    → {}
      error   → { message: str }
    """
    if mode not in ("quick", "deep"):
        mode = "quick"

    async def event_generator() -> AsyncIterator[dict]:
        try:
            # ── 1. Classify intent ──────────────────────────────────────────
            yield {
                "event": "status",
                "data": json.dumps({"message": "🧠 Classifying query intent…"}),
            }

            intent = await classify_intent(q)

            yield {
                "event": "intent",
                "data": json.dumps({"intent": intent}),
            }

            # ── 2. Determine spider + k ─────────────────────────────────────
            spider_file = SPIDER_MAP[intent]
            k           = K_MAP[intent][mode]

            intent_emoji = {"VIDEO": "🎬", "IMAGE": "🖼️", "TEXT": "📄"}[intent]
            mode_label   = "Quick search" if mode == "quick" else "Deep research"

            yield {
                "event": "status",
                "data": json.dumps({
                    "message": (
                        f"{intent_emoji} {mode_label} — "
                        f"launching headless browser for {intent.lower()} search…"
                    ),
                }),
            }

            t0    = time.time()
            posts = await scrape_async(q, k, spider_file)
            elapsed = round(time.time() - t0, 1)

            if not posts:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "message": (
                            f"No {intent.lower()} results found. "
                            "The headless browser may be blocked. Try a different query."
                        ),
                    }),
                }
                return

            # ── 3. Emit sources immediately ─────────────────────────────────
            sources = normalize_sources(posts, intent)

            yield {
                "event": "status",
                "data": json.dumps({
                    "message": (
                        f"✅ Found {len(posts)} {intent.lower()} results in {elapsed}s. "
                        "Synthesizing answer…"
                    ),
                }),
            }

            yield {
                "event": "sources",
                "data": json.dumps({"sources": sources, "intent": intent}),
            }

            # ── 4. Stream LLM tokens ────────────────────────────────────────
            prompt = build_prompt(q, posts, intent, mode)

            async for token in stream_llm(prompt):
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            # ── 5. Done ─────────────────────────────────────────────────────
            yield {"event": "done", "data": json.dumps({})}

        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield {
                "event": "error",
                "data": json.dumps({"message": f"Server error: {str(exc)}"}),
            }

    return EventSourceResponse(event_generator())


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status":   "ok",
        "provider": LLM_PROVIDER,
        "version":  "4.0.0",
        "intents":  list(SPIDER_MAP.keys()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
