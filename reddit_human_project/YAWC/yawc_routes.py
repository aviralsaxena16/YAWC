from __future__ import annotations

import json
import time
import asyncio
import hashlib
import re
from pathlib import Path
from typing import AsyncIterator
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yawc_config import (
    GEMINI_KEY,
    ANTHROPIC_KEY,
    LLM_PROVIDER,
    TRACE_DIR,
    PDF_DIR,
    SPIDER_DIR,
    PLATFORM_SPIDERS,
    PLATFORM_K,
)
from yawc_rag import ingest_posts, query_rag
from yawc_spider import scrape_platforms

router = APIRouter()


_RAG_ROUTER_PROMPT = """You are a query router for YAWC, an AI research agent.

Decide TWO things:

1. query_intent:
   - FOLLOW_UP: clarification or drill-down on something already researched this session
     (e.g. "tell me more", "expand on point 3", "compare those", "summarise")
   - NEW_SEARCH: needs fresh scraping — new topic, specific facts, or the session has no history

2. media_intent:
   - VIDEO: user wants tutorials, demos, or mentions video/YouTube
   - IMAGE: user wants photos, visual inspiration, or mentions images/pictures
   - TEXT:  everything else (default)

Reply with ONLY valid JSON, nothing else:
{"query_intent": "FOLLOW_UP|NEW_SEARCH", "media_intent": "VIDEO|IMAGE|TEXT"}"
"""

_PLATFORM_SELECTOR_PROMPT = """You are YAWC's platform selector. Pick the BEST 2-4 platforms for this query.

Available platforms:
- reddit:        Product reviews, hobbyist advice, raw human opinions, community picks
- stackoverflow: Code errors, debugging, programming how-to, API usage
- hackernews:    Tech industry news, engineering discussions, tool comparisons, startup insight
- wikipedia:     Factual definitions, historical context, scientific background
- quora:         Long-form personal advice, career guidance, philosophical questions
- youtube:       Tutorials, demos, gameplay — ONLY when media_intent=VIDEO
- image:         Visual inspiration, product photos — ONLY when media_intent=IMAGE

Rules:
1. media_intent=VIDEO  → return exactly ["youtube"]
2. media_intent=IMAGE  → return exactly ["image"]
3. media_intent=TEXT   → choose 2-4 from: reddit, stackoverflow, hackernews, wikipedia, quora
   - Code/programming  → stackoverflow + hackernews (+ optionally reddit)
   - Products/gear     → reddit (+ optionally quora)
   - Factual/science   → wikipedia + reddit
   - Opinion/advice    → reddit + quora
   - Tech news/tools   → hackernews + reddit

Reply with ONLY a JSON array. Example: ["reddit","stackoverflow"]"""

_DISPLAY_NAMES = {
    "Reddit": "Reddit",
    "Stackoverflow": "StackOverflow",
    "Hackernews": "Hacker News",
    "Wikipedia": "Wikipedia",
    "Quora": "Quora",
    "Youtube": "YouTube",
    "Image": "Images",
}

_session_topics: dict[str, list[str]] = {}

def get_session_topics(chat_id: str) -> list[str]:
    return _session_topics.get(chat_id, [])


def add_session_topic(chat_id: str, topic: str) -> None:
    _session_topics.setdefault(chat_id, [])
    _session_topics[chat_id].append(topic[:200])
    _session_topics[chat_id] = _session_topics[chat_id][-20:]


class PDFRequest(BaseModel):
    chat_id: str
    markdown: str
    title: str = "YAWC Research Report"
    query: str = ""


class TeachRequest(BaseModel):
    url: str
    spider_name: str = ""


_PDF_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body { font-family: Arial, sans-serif; margin: 32px; }
.cover { margin-bottom: 24px; border-bottom: 2px solid #333; padding-bottom: 12px; }
.cover-title { font-size: 26px; font-weight: bold; }
.cover-meta { color: #555; margin-top: 8px; font-size: 0.9rem; }
.content { margin-top: 24px; }
</style>
</head>
<body>
<div class="cover">
  <div class="cover-tag">YAWC · Research Report</div>
  <div class="cover-title">{title}</div>
  {query_block}
  <div class="cover-meta">Generated: {timestamp} · Chat ID: {chat_id}</div>
</div>
<div class="content">{body_html}</div>
<div class="footer" style="margin-top: 48px; font-size: 0.8rem; color: #777;">YAWC · RESEARCH ENGINE · {timestamp}</div>
</body>
</html>
"""


def _md_to_html(md: str) -> str:
    import re
    lines = md.split("\n")
    html, para = [], []

    def flush():
        if para:
            text = " ".join(para).strip()
            if text:
                html.append(f"<p>{text}</p>")
            para.clear()

    def inline(t: str) -> str:
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = re.sub(r"\[(\d+)\]", r'<span class="citation">[\1]</span>', t)
        t = re.sub(r"!\[([^\]]*)\]\((https?://[^)]+)\)", r'<img src="\2" alt="\1">', t)
        return t

    for line in lines:
        if line.startswith("## "):
            flush()
            html.append(f"<h2>{inline(line[3:].strip())}</h2>")
        elif not line.strip():
            flush()
        else:
            para.append(inline(line.strip()))
    flush()
    return "\n".join(html)


async def _render_pdf(html: str, out: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=str(out),
            format="A4",
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            print_background=True,
        )
        await browser.close()


def _find_latest_trace(chat_id: str) -> str | None:
    d = TRACE_DIR / chat_id
    if not d.exists():
        return None
    zips = sorted(d.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0].name if zips else None


def _route_query_blocking(query: str, session_topics: list[str]) -> dict:
    topics_str = ", ".join(session_topics[-5:]) if session_topics else "none yet"
    user_msg = f"Current query: {query}\nPrevious topics this session: {topics_str}"
    full_prompt = _RAG_ROUTER_PROMPT + "\n\n" + user_msg

    try:
        if LLM_PROVIDER == "gemini" and GEMINI_KEY:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
            resp = _gemini_model.generate_content(full_prompt)
            raw = resp.text.strip()
        elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
            import anthropic as _anthropic_lib
            _anthropic_client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_KEY)
            msg = _anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=60,
                messages=[{"role": "user", "content": full_prompt}],
            )
            raw = msg.content[0].text.strip()
        else:
            return {"query_intent": "NEW_SEARCH", "media_intent": "TEXT"}

        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        result = json.loads(raw)
        qi = result.get("query_intent", "NEW_SEARCH")
        mi = result.get("media_intent", "TEXT")
        if qi not in ("FOLLOW_UP", "NEW_SEARCH"):
            qi = "NEW_SEARCH"
        if mi not in ("VIDEO", "IMAGE", "TEXT"):
            mi = "TEXT"
        return {"query_intent": qi, "media_intent": mi}
    except Exception as e:
        print(f"[YAWC] Router error: {e}", flush=True)
        return {"query_intent": "NEW_SEARCH", "media_intent": "TEXT"}


async def route_query(query: str, session_topics: list[str]) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        __import__("yawc_config").THREAD_POOL,
        _route_query_blocking,
        query,
        session_topics,
    )


def _select_platforms_blocking(query: str, media_intent: str) -> list[str]:
    user_msg = f"Query: {query}\nMedia intent: {media_intent}"
    full_prompt = _PLATFORM_SELECTOR_PROMPT + "\n\n" + user_msg
    try:
        if LLM_PROVIDER == "gemini" and GEMINI_KEY:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
            resp = _gemini_model.generate_content(full_prompt)
            raw = resp.text.strip()
        elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
            import anthropic as _anthropic_lib
            _anthropic_client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_KEY)
            msg = _anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=80,
                messages=[{"role": "user", "content": full_prompt}],
            )
            raw = msg.content[0].text.strip()
        else:
            return {"VIDEO": ["youtube"], "IMAGE": ["image"]}.get(media_intent, ["reddit"])

        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        platforms = json.loads(raw)
        valid = [p for p in platforms if p in PLATFORM_SPIDERS]
        return valid if valid else ["reddit"]
    except Exception as e:
        print(f"[YAWC] Platform selector error: {e}", flush=True)
        return {"VIDEO": ["youtube"], "IMAGE": ["image"]}.get(media_intent, ["reddit"])


async def select_platforms(query: str, media_intent: str) -> list[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        __import__("yawc_config").THREAD_POOL,
        _select_platforms_blocking,
        query,
        media_intent,
    )


async def stream_gemini(prompt: str) -> AsyncIterator[str]:
    import google.generativeai as genai
    from yawc_config import GEMINI_KEY

    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: model.generate_content(prompt, stream=True),
    )
    for chunk in resp:
        if chunk.text:
            yield chunk.text


async def stream_anthropic(prompt: str) -> AsyncIterator[str]:
    import anthropic as _anthropic_lib
    from yawc_config import ANTHROPIC_KEY

    client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_KEY)
    ctx = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    with ctx as stream:
        for text in stream.text_stream:
            yield text


async def stream_llm(prompt: str) -> AsyncIterator[str]:
    if LLM_PROVIDER == "gemini" and GEMINI_KEY:
        async for tok in stream_gemini(prompt):
            yield tok
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
        async for tok in stream_anthropic(prompt):
            yield tok
    else:
        for chunk in "[No LLM configured] Set GEMINI_API_KEY or ANTHROPIC_API_KEY.".split():
            yield chunk + " "
            await asyncio.sleep(0.02)


def normalize_sources(posts: list[dict], media_intent: str) -> list[dict]:
    sources = []
    for p in posts:
        raw_plat = p.get("platform", "Web")
        display = _DISPLAY_NAMES.get(raw_plat, raw_plat)
        src: dict = {
            "index": p.get("index", 0),
            "title": p.get("title", ""),
            "url": p.get("url", ""),
            "platform": display,
            "score": str(p.get("score", p.get("views", p.get("likes", 0)))),
        }
        if media_intent == "VIDEO":
            src.update({
                "embed_url": p.get("embed_url", ""),
                "channel": p.get("channel", ""),
                "thumbnail": p.get("thumbnail", ""),
            })
        elif media_intent == "IMAGE":
            src.update({
                "image_url": p.get("image_url", ""),
                "alt": p.get("alt", ""),
            })
        sources.append(src)
    return sources


def _format_context(posts: list[dict], media_intent: str) -> str:
    parts = []
    for p in posts:
        plat = _DISPLAY_NAMES.get(p.get("platform", ""), p.get("platform", ""))
        score = p.get("score") or p.get("views") or p.get("likes") or "0"
        body = (p.get("body") or p.get("description") or "").strip() or "(no body)"
        idx = p.get("index", "?")
        if media_intent == "VIDEO":
            parts.append(
                f"[{idx}] YouTube | Channel: {p.get('channel','?')} | Views: {score}\n"
                f"Title: {p.get('title','')}\n"
                f"Description: {body[:400]}\n"
                f"Embed URL: {p.get('embed_url','')}"
            )
        elif media_intent == "IMAGE":
            parts.append(
                f"[{idx}] {plat}\n"
                f"Alt: {p.get('alt','')}\n"
                f"Image URL: {p.get('image_url','')}"
            )
        else:
            parts.append(
                f"[{idx}] {plat} | Score: {score}\n"
                f"Title: {p.get('title','')}\n"
                f"Body: {body[:600]}"
            )
    return "\n\n---\n\n".join(parts)


def build_prompt(query: str, posts: list[dict], media_intent: str, mode: str) -> str:
    context = _format_context(posts, media_intent)
    if media_intent == "VIDEO":
        instructions = (
            "For each recommended video output on its own line:\n"
            "  [YOUTUBE_EMBED: <embed_url>]\n"
            "Then give title + one-sentence reason. Cite inline with [N]."
        )
    elif media_intent == "IMAGE":
        instructions = (
            "For each image embed it as:\n"
            "  ![<alt text>](<image_url>)\n"
            "Comment on style, colour, and composition. Cite with [N]."
        )
    elif mode == "quick":
        instructions = (
            "Answer directly and concisely (2–4 paragraphs). "
            "Cite sources inline with [N]. Use ## headings only if multiple sections are clearly needed."
        )
    else:
        instructions = (
            "Write a structured deep-research report:\n\n"
            "## Summary\n2–3 sentence overview.\n\n"
            "## Key Themes\n3–5 recurring themes. Cite with [N].\n\n"
            "## Pros & Cons\n**Pros**: ...\n**Cons**: ...\n\n"
            "## Community Consensus\nOverall verdict across platforms.\n\n"
            "## Notable Perspectives\n1–2 standout or contrarian takes.\n\n"
            + "Platform guide (use when making attribution claims):\n"
            + "• Reddit        → community opinions, product picks, personal experience\n"
            + "• StackOverflow → verified code solutions, technical accuracy\n"
            + "• Hacker News   → engineering culture, tool comparisons, startup insight\n"
            + "• Wikipedia     → factual definitions, historical/scientific background\n"
            + "• Quora         → long-form personal advice, anecdotal guidance\n"
            + "• YouTube       → tutorial walkthroughs, demonstrations\n"
        )
    return (
        "You are YAWC, an AI that synthesises multi-platform web research.\n\n"
        f"USER QUESTION: {query}\n\n"
        f"SCRAPED CONTENT ({len(posts)} results from {len(set(p.get('platform') for p in posts))} platforms):\n"
        f"{context}\n\n"
        f"Instructions:\n{instructions}\n\n"
        "Do NOT invent information beyond what the sources contain.\n\n"
        "ANSWER:"
    )


def build_rag_prompt(query: str, chunks: list[dict]) -> str:
    parts = [
        f"[MEM-{i}] {c.get('platform','')} — {c.get('title','')}\n{c.get('text','')}"
        for i, c in enumerate(chunks, 1)
    ]
    context = "\n\n---\n\n".join(parts)
    return (
        "You are YAWC. The user asks a follow-up about topics already researched this session.\n"
        "Answer using the memory excerpts below. Do not say you cannot access the web.\n\n"
        f"FOLLOW-UP QUESTION: {query}\n\n"
        f"MEMORY EXCERPTS:\n{context}\n\n"
        "Instructions:\n"
        "- Answer the follow-up directly.\n"
        "- Reference memory excerpts with [MEM-N].\n"
        "- If memory is insufficient, say so clearly.\n\n"
        "ANSWER:"
    )


@router.get("/api/search")
async def search_stream(
    q: str = Query(..., min_length=2),
    mode: str = Query("quick"),
    chat_id: str = Query(..., min_length=1),
) -> EventSourceResponse:
    if mode not in ("quick", "deep"):
        mode = "quick"

    async def generator() -> AsyncIterator[dict]:
        try:
            yield {"event": "status", "data": json.dumps({"message": "🧠 Analysing intent…"})}
            topics = get_session_topics(chat_id)
            routing = await route_query(q, topics)
            qi = routing["query_intent"]
            mi = routing["media_intent"]

            if qi == "FOLLOW_UP":
                yield {"event": "routing", "data": json.dumps({"query_intent": "FOLLOW_UP", "media_intent": mi, "platforms": []})}
                yield {"event": "status", "data": json.dumps({"message": "⚡ Follow-up detected — querying memory…"})}
                chunks = await query_rag(chat_id, q)
                if not chunks:
                    qi = "NEW_SEARCH"
                    yield {"event": "status", "data": json.dumps({"message": "💭 No memory found — performing fresh search…"})}
                else:
                    yield {"event": "rag_hit", "data": json.dumps({"chunks_used": len(chunks)})}
                    async for tok in stream_llm(build_rag_prompt(q, chunks)):
                        yield {"event": "token", "data": json.dumps({"token": tok})}
                    add_session_topic(chat_id, q)
                    yield {"event": "done", "data": json.dumps({})}
                    return

            platforms = await select_platforms(q, mi)
            yield {"event": "routing", "data": json.dumps({"query_intent": "NEW_SEARCH", "media_intent": mi, "platforms": platforms})}
            icon = {"VIDEO": "🎬", "IMAGE": "🖼️", "TEXT": "🔍"}.get(mi, "🔍")
            plat_label = " · ".join(p.capitalize() for p in platforms)
            yield {"event": "status", "data": json.dumps({"message": f"{icon} Scraping {plat_label}…"})}

            t0 = time.time()
            posts = await scrape_platforms(q, platforms, mode, chat_id)
            elapsed = round(time.time() - t0, 1)

            if not posts:
                trace_file = _find_latest_trace(chat_id)
                err = {"message": "No results found. Platforms may be blocking the crawler."}
                if trace_file:
                    err["trace_file"] = trace_file
                yield {"event": "error", "data": json.dumps(err)}
                return

            sources = normalize_sources(posts, mi)
            yield {"event": "status", "data": json.dumps({"message": f"✅ {len(posts)} results in {elapsed}s — synthesising…"})}
            yield {"event": "sources", "data": json.dumps({"sources": sources, "media_intent": mi})}

            asyncio.create_task(ingest_posts(chat_id, posts))
            async for tok in stream_llm(build_prompt(q, posts, mi, mode)):
                yield {"event": "token", "data": json.dumps({"token": tok})}

            get_session_topics(chat_id)
            add_session_topic(chat_id, q)
            yield {"event": "done", "data": json.dumps({})}

        except Exception as exc:
            import traceback
            traceback.print_exc()
            trace_file = _find_latest_trace(chat_id)
            err = {"message": f"Server error: {exc}"}
            if trace_file:
                err["trace_file"] = trace_file
            yield {"event": "error", "data": json.dumps(err)}

    return EventSourceResponse(generator())


@router.post("/api/export-pdf")
async def export_pdf(req: PDFRequest):
    import datetime
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    qb = f'<div class="cover-query">"{req.query}"</div>' if req.query else ""
    html = _PDF_HTML.format(
        title=req.title,
        query_block=qb,
        timestamp=ts,
        chat_id=req.chat_id,
        body_html=_md_to_html(req.markdown),
    )
    fname = f"yawc_{req.chat_id[:8]}_{int(time.time())}.pdf"
    path = PDF_DIR / fname
    try:
        await _render_pdf(html, path)
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=fname,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/api/teach")
async def teach_spider(req: TeachRequest):
    from urllib.parse import urlparse
    import re as _re
    from yawc_spider import _spider_scaffold

    domain = urlparse(req.url).netloc.lstrip("www.").replace(".", "_").replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "_", (req.spider_name or domain).lower())

    out_dir = SPIDER_DIR / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{name}_codegen.py"

    cmd = [
        "playwright",
        "codegen",
        "--target",
        "python-async",
        "--output",
        str(out_file),
        req.url,
    ]
    print(f"[YAWC/TEACH] {' '.join(cmd)}", flush=True)
    try:
        loop = asyncio.get_event_loop()
        proc = await asyncio.wait_for(
            loop.run_in_executor(
                __import__("yawc_config").THREAD_POOL,
                lambda: __import__("subprocess").run(cmd, capture_output=True, text=True, timeout=300),
            ),
            timeout=310,
        )
        if not out_file.exists():
            return {
                "status": "cancelled",
                "message": "Codegen closed without saving. Ensure you click Record in Playwright Inspector.",
            }
        generated = out_file.read_text(encoding="utf-8")
        scaffold = _spider_scaffold(name, req.url, generated)
        sc_path = out_dir / f"{name}_spider.py"
        sc_path.write_text(scaffold, encoding="utf-8")
        return {
            "status": "success",
            "out_file": str(out_file),
            "scaffold": str(sc_path),
            "code_preview": generated[:1500],
        }
    except asyncio.TimeoutError:
        return {"status": "timeout", "message": "Codegen timed out (5 min)."}
    except FileNotFoundError:
        raise HTTPException(500, "playwright not found. Run: playwright install chromium")
    except Exception as e:
        raise HTTPException(500, f"Codegen failed: {e}")


@router.get("/api/traces/{chat_id}")
def list_traces(chat_id: str):
    d = TRACE_DIR / chat_id
    if not d.exists():
        return {"traces": []}
    zips = sorted(d.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"traces": [{"filename": z.name, "size_kb": round(z.stat().st_size / 1024, 1)} for z in zips]}


@router.get("/api/traces/{chat_id}/download/{filename}")
def download_trace(chat_id: str, filename: str):
    p = TRACE_DIR / chat_id / filename
    if not p.exists() or p.suffix != ".zip":
        raise HTTPException(404, "Trace file not found")
    return FileResponse(path=str(p), media_type="application/zip", filename=filename)


@router.post("/api/traces/{chat_id}/view/{filename}")
def view_trace(chat_id: str, filename: str):
    p = TRACE_DIR / chat_id / filename
    if not p.exists():
        raise HTTPException(404, "Trace file not found")
    try:
        __import__("subprocess").Popen([
            "playwright",
            "show-trace",
            str(p),
        ], stdout=__import__("subprocess").DEVNULL, stderr=__import__("subprocess").DEVNULL)
        return {
            "status": "launched",
            "message": "Playwright Trace Viewer launched. Open http://localhost:9323 in your browser.",
        }
    except FileNotFoundError:
        raise HTTPException(500, "playwright not found. Run: playwright install chromium")
    except Exception as e:
        raise HTTPException(500, f"Could not launch trace viewer: {e}")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "5.0.0",
        "provider": LLM_PROVIDER,
        "platforms": list(PLATFORM_SPIDERS.keys()),
        "features": {"rag": True, "pdf": True, "teach": True, "tracing": True},
    }


def _find_latest_trace(chat_id: str) -> str | None:
    d = TRACE_DIR / chat_id
    if not d.exists():
        return None
    zips = sorted(d.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0].name if zips else None
