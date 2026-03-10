"""
YAWC Backend v2 — FastAPI + Async Subprocess + Token Streaming + Deep Research
Features:
  - Async subprocess (non-blocking asyncio.create_subprocess_exec)
  - LLM token streaming via SSE
  - Quick (k=8) and Deep Research (k=30) modes
  - Inline citation references [1][2][3] in the answer
  - Deep research: themes + pros/cons + consensus sections

Install:
    pip install fastapi uvicorn scrapy scrapy-playwright \
                google-generativeai anthropic sse-starlette python-dotenv
    playwright install chromium
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
from typing import AsyncIterator

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
app = FastAPI(title="YAWC API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Cross-Platform Async Spider Runner ──────────────────────────────────────
#
# ROOT CAUSE of the Windows error:
#   asyncio.create_subprocess_exec requires ProactorEventLoop on Windows.
#   FastAPI/uvicorn uses WindowsSelectorEventLoopPolicy by default (Python 3.8+),
#   which does NOT support subprocess. Switching to ProactorEventLoop breaks
#   uvicorn's internal socket handling. There's no clean fix inside the same loop.
#
# SOLUTION — two-path strategy:
#   • Windows → run_in_executor(ThreadPoolExecutor, subprocess.run)
#               The spider runs in a thread pool worker. The FastAPI event loop
#               stays free for other requests. subprocess.run is blocking but
#               confined to its own thread — this is the correct Windows pattern.
#   • Linux/Mac → asyncio.create_subprocess_exec (truly async, no threads needed)
#
# Both paths produce identical results. The temp-file handoff is the same.

# Thread pool for Windows subprocess execution (reused across requests)
_thread_pool = ThreadPoolExecutor(max_workers=4)


def _run_spider_blocking(cmd: list[str], temp_file: str) -> None:
    """Blocking subprocess call — safe to run inside a thread pool executor."""
    result = subprocess.run(
        cmd,
        capture_output=False,   # let Scrapy logs print to terminal live
        text=True,
    )
    if result.returncode not in (0, 1):
        # returncode=1 is normal for Scrapy when some requests fail
        print(f"[YAWC] Spider exited with code {result.returncode}", flush=True)


async def scrape_reddit_async(query: str, k: int, status_callback=None) -> list[dict]:
    """
    Launch Scrapy spider as a non-blocking subprocess (cross-platform).
    Results are written to a temp JSON file, then read into memory.
    No temp file is left on disk.
    """
    # Use system temp dir — works on both Windows and Linux
    import tempfile
    temp_dir  = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, f"yawc_{uuid.uuid4().hex}.json")

    # On Windows /dev/null doesn't exist — use NUL instead
    null_device = "NUL" if platform.system() == "Windows" else "/dev/null"

    cmd = [
        sys.executable, "-m", "scrapy", "runspider",
        "reddit_spider.py",
        "-a", f"query={query}",
        "-a", f"k={k}",
        "-o", temp_file,
        "--logfile", null_device,
    ]

    print(f"[YAWC] Launching spider | query={query!r} k={k} platform={platform.system()}", flush=True)

    IS_WINDOWS = platform.system() == "Windows"

    if IS_WINDOWS:
        # ── Windows path: thread pool executor (non-blocking for asyncio) ──────
        # subprocess.run is blocking, but ThreadPoolExecutor isolates it from
        # the event loop. FastAPI can serve other requests while spider runs.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            _thread_pool,
            _run_spider_blocking,
            cmd,
            temp_file,
        )
    else:
        # ── Unix path: truly async subprocess (no threads needed) ────────────
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

    # ── Read results from temp file ──────────────────────────────────────────
    results = []
    if os.path.exists(temp_file):
        try:
            with open(temp_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                results = raw if isinstance(raw, list) else [raw]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[YAWC] Could not parse results file: {e}", flush=True)
        finally:
            try:
                os.remove(temp_file)
            except OSError:
                pass
    else:
        print(f"[YAWC] ⚠ Temp file not found: {temp_file}", flush=True)

    print(f"[YAWC] Spider done. Found {len(results)} posts.", flush=True)
    return results


# ─── Prompt Builders ──────────────────────────────────────────────────────────

def _build_quick_prompt(query: str, posts: list[dict]) -> str:
    """Quick mode: concise synthesis with inline [N] citations."""
    context_parts = []
    for i, p in enumerate(posts, 1):
        body = (p.get("body") or "").strip() or "(no body text)"
        context_parts.append(
            f"[{i}] {p.get('subreddit','')} | ↑{p.get('score',0)}\n"
            f"Title: {p.get('title','')}\n"
            f"Body: {body[:600]}"
        )
    context = "\n\n".join(context_parts)

    return f"""You are YAWC, an AI that synthesizes Reddit discussions into clear answers.

USER QUESTION: {query}

REDDIT POSTS (reference by number inline, e.g. [1] [3]):
{context}

Instructions:
- Answer the question directly and concisely (2-4 paragraphs).
- Cite sources inline using [N] notation after each claim (e.g. "Users prefer X [1][3]").
- Be honest if posts don't fully answer the question.
- Do NOT invent information beyond what the posts contain.

ANSWER:"""


def _build_deep_prompt(query: str, posts: list[dict]) -> str:
    """Deep Research mode: themes + pros/cons + consensus + citations."""
    context_parts = []
    for i, p in enumerate(posts, 1):
        body = (p.get("body") or "").strip() or "(no body text)"
        context_parts.append(
            f"[{i}] {p.get('subreddit','')} | ↑{p.get('score',0)}\n"
            f"Title: {p.get('title','')}\n"
            f"Body: {body[:500]}"
        )
    context = "\n\n".join(context_parts)

    return f"""You are YAWC, a deep research AI that synthesizes Reddit discussions into structured reports.

USER QUESTION: {query}

REDDIT POSTS ({len(posts)} scraped, reference inline as [N]):
{context}

Produce a structured deep research report with these exact sections:

## Summary
2-3 sentence overview of what Reddit says about this topic.

## Key Themes
The 3-5 most recurring themes or ideas across posts. Use inline citations [N].

## Pros & Cons
**Pros** (what people recommend / praise):
**Cons** (complaints, warnings, caveats):

## Reddit Consensus
What is the overall community verdict or recommendation? Is there disagreement?

## Notable Opinions
1-2 standout takes that are insightful or contrarian.

Rules:
- Cite with [N] after every claim.
- Only use information from the provided posts.
- Be direct. No filler phrases.

DEEP RESEARCH REPORT:"""


# ─── LLM Streaming ────────────────────────────────────────────────────────────

async def stream_gemini(prompt: str) -> AsyncIterator[str]:
    """Stream Gemini tokens via async generator."""
    loop = asyncio.get_event_loop()
    # Gemini streaming: generate_content with stream=True
    response = await loop.run_in_executor(
        None,
        lambda: _gemini_model.generate_content(prompt, stream=True)
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text


async def stream_anthropic(prompt: str) -> AsyncIterator[str]:
    """Stream Anthropic Claude tokens via async generator."""
    loop = asyncio.get_event_loop()

    # Build streaming message in executor to avoid blocking
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
    """Route to the correct LLM streamer."""
    if LLM_PROVIDER == "gemini" and GEMINI_KEY:
        async for token in stream_gemini(prompt):
            yield token
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
        async for token in stream_anthropic(prompt):
            yield token
    else:
        # Fallback: yield a single mock response token-by-token
        msg = f"[No LLM configured] Found {0} posts.\nSet GEMINI_API_KEY or ANTHROPIC_API_KEY in .env"
        for word in msg.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)


# ─── SSE Search Endpoint ──────────────────────────────────────────────────────
# SSE event types:
#   status  → { message: str }                        — progress update
#   token   → { token: str }                          — LLM streaming chunk
#   sources → { sources: [{title,url,subreddit,score,index}] }
#   done    → {}                                      — stream complete
#   error   → { message: str }

@app.get("/api/search")
async def search_stream(
    q: str    = Query(..., min_length=2),
    mode: str = Query("quick"),
) -> EventSourceResponse:
    """
    Streams search progress + LLM tokens via SSE.
    mode=quick  → k=8  posts, concise answer
    mode=deep   → k=30 posts, structured deep report
    """
    # Validate mode manually (avoids regex= vs pattern= FastAPI version issues)
    if mode not in ("quick", "deep"):
        mode = "quick"

    async def event_generator() -> AsyncIterator[dict]:
        k = 8 if mode == "quick" else 30
        try:
            # ── 1. Status: starting ─────────────────────────────────────────
            yield {
                "event": "status",
                "data": json.dumps({
                    "message": f"{'🔍' if mode == 'quick' else '🔬'} "
                               f"{'Quick search' if mode == 'quick' else 'Deep research'} — "
                               f"launching headless browser…",
                }),
            }

            t0 = time.time()

            # ── 2. Run async spider ─────────────────────────────────────────
            posts = await scrape_reddit_async(q, k)
            scrape_time = round(time.time() - t0, 1)

            if not posts:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "message": "No Reddit posts found. Reddit may be blocking the headless browser. Try again or change the query.",
                    }),
                }
                return

            yield {
                "event": "status",
                "data": json.dumps({
                    "message": f"📄 Scraped {len(posts)} posts in {scrape_time}s. "
                               f"{'Synthesizing…' if mode == 'quick' else 'Running deep analysis…'}",
                }),
            }

            # ── 3. Send sources immediately (before LLM finishes) ───────────
            # This lets the UI show source cards while tokens stream in
            sources = [
                {
                    "index": i + 1,
                    "title": p.get("title", ""),
                    "url": p.get("url", ""),
                    "subreddit": p.get("subreddit", ""),
                    "score": p.get("score", 0),
                }
                for i, p in enumerate(posts)
            ]
            yield {
                "event": "sources",
                "data": json.dumps({"sources": sources}),
            }

            # ── 4. Stream LLM tokens ────────────────────────────────────────
            prompt = (
                _build_quick_prompt(q, posts)
                if mode == "quick"
                else _build_deep_prompt(q, posts)
            )

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
        "status": "ok",
        "provider": LLM_PROVIDER,
        "version": "2.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
