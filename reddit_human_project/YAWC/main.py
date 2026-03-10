"""
YAWC Backend — FastAPI + Crochet + Gemini/Anthropic
Runs the Scrapy/Playwright spider inside FastAPI without ReactorNotRestartable.

Install deps:
    pip install fastapi uvicorn scrapy scrapy-playwright \
                crochet google-generativeai anthropic \
                sse-starlette python-dotenv
    playwright install chromium
"""

import os
import json
import asyncio
import threading
import time
from typing import AsyncIterator

import crochet
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from twisted.internet import defer

from reddit_spider import YAWCSearchSpider, get_yawc_settings

load_dotenv()

# ─── Crochet: tames the Twisted reactor inside FastAPI ──────────────────────
crochet.setup()
configure_logging({"LOG_LEVEL": "WARNING"})

# ─── LLM setup ────────────────────────────────────────────────────────────────
GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()   # "gemini" | "anthropic"

if LLM_PROVIDER == "gemini" and GEMINI_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    _gemini_model = genai.GenerativeModel("gemini-2.5-flash")

elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
    import anthropic as _anthropic
    _anthropic_client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="YAWC API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Scrapy runner (singleton — reactor must NOT be restarted) ────────────────
_runner = CrawlerRunner(settings=get_yawc_settings())


@crochet.run_in_reactor
def _run_spider(query: str, k: int, result_collector: list) -> defer.Deferred:
    """Run spider in the Twisted reactor thread via Crochet."""
    return _runner.crawl(
        YAWCSearchSpider,
        query=query,
        k=k,
        result_collector=result_collector,
    )


def scrape_reddit_sync(query: str, k: int = 8) -> list[dict]:
    """
    Blocking wrapper: calls Crochet, waits for crawl to finish.
    Returns list of post dicts in-memory — zero disk I/O.
    """
    results: list[dict] = []
    eventual = _run_spider(query, k, results)
    eventual.wait(timeout=120)   # max 2 min before giving up
    return results


# ─── LLM synthesis ────────────────────────────────────────────────────────────
def _build_prompt(query: str, posts: list[dict]) -> str:
    context_parts = []
    for i, p in enumerate(posts, 1):
        body = p.get("body", "").strip() or "(no body text)"
        context_parts.append(
            f"[Post {i}] {p.get('subreddit', '')} | Score: {p.get('score', 0)}\n"
            f"Title: {p.get('title', '')}\n"
            f"URL: {p.get('url', '')}\n"
            f"Body: {body[:800]}"       # cap per-post to keep prompt size reasonable
        )

    context = "\n\n---\n\n".join(context_parts)

    return f"""You are YAWC — an AI research assistant that synthesizes Reddit discussions into clear, accurate answers.

USER QUESTION: {query}

REDDIT POSTS SCRAPED IN REAL-TIME:
{context}

---
Instructions:
- Synthesize insights from the posts above to answer the question directly.
- Cite posts by number (e.g., [Post 3]) where relevant.
- Be honest if the posts don't fully answer the question.
- Keep the response concise but complete (3–6 paragraphs max).
- Do NOT make up information beyond what the posts contain.

YOUR SYNTHESIZED ANSWER:"""


async def synthesize_with_llm(query: str, posts: list[dict]) -> str:
    prompt = _build_prompt(query, posts)

    if LLM_PROVIDER == "gemini" and GEMINI_KEY:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _gemini_model.generate_content(prompt)
        )
        return response.text

    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
        )
        return response.content[0].text

    else:
        # Fallback: echo context without LLM (useful for testing)
        return f"[No LLM configured] Found {len(posts)} Reddit posts about '{query}':\n\n" + \
               "\n".join(f"• {p['title']}" for p in posts[:5])


# ─── SSE streaming endpoint ───────────────────────────────────────────────────
@app.get("/api/search")
async def search_stream(q: str = Query(..., min_length=2)) -> EventSourceResponse:
    """
    Server-Sent Events endpoint.
    Streams status events so the UI can show live progress (like ChatGPT Deep Research).

    Events:
        status  — intermediate messages ("Searching Reddit…", "Scraping N posts…")
        result  — final JSON payload {answer, sources}
        error   — something went wrong
    """

    async def event_generator() -> AsyncIterator[dict]:
        try:
            # ── 1. Acknowledge ─────────────────────────────────────────────
            yield {"event": "status", "data": json.dumps({"message": "🔍 Searching Reddit…"})}

            t0 = time.time()

            # ── 2. Run spider in thread (blocking, must NOT block event loop) ─
            loop = asyncio.get_event_loop()
            posts = await loop.run_in_executor(None, scrape_reddit_sync, q, 8)

            scrape_time = round(time.time() - t0, 1)

            if not posts:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "No Reddit posts found. Try a different query."}),
                }
                return

            yield {
                "event": "status",
                "data": json.dumps({
                    "message": f"📄 Scraped {len(posts)} posts in {scrape_time}s. Thinking…",
                }),
            }

            # ── 3. Synthesize ──────────────────────────────────────────────
            answer = await synthesize_with_llm(q, posts)

            sources = [
                {
                    "title": p.get("title", ""),
                    "url": p.get("url", ""),
                    "subreddit": p.get("subreddit", ""),
                    "score": p.get("score", 0),
                }
                for p in posts
            ]

            yield {
                "event": "result",
                "data": json.dumps({"answer": answer, "sources": sources}),
            }

        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({"message": f"Error: {str(exc)}"}),
            }

    return EventSourceResponse(event_generator())


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "provider": LLM_PROVIDER}


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
