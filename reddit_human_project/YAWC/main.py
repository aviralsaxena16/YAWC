import os
import json
import asyncio
import time
import uuid
from typing import AsyncIterator
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import sys
import subprocess
load_dotenv()

# ─── LLM Setup ────────────────────────────────────────────────────────────────
GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

if LLM_PROVIDER == "gemini" and GEMINI_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
    import anthropic as _anthropic
    _anthropic_client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)

app = FastAPI(title="YAWC API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Subprocess Spider Runner ─────────────────────────────────────────────────
async def scrape_reddit_isolated(query: str, k: int = 8) -> list[dict]:
    """Runs the Scrapy spider and streams logs LIVE to the terminal."""
    temp_file = f"temp_results_{uuid.uuid4().hex}.json"
    
    cmd = [
        sys.executable, "-m", "scrapy", "runspider", "reddit_spider.py",
        "-a", f"query={query}",
        "-a", f"k={k}",
        "-o", temp_file
    ]
    
    print(f"\n[YAWC] Launching spider for query: '{query}'")
    print("--- 🕷️ SCRAPY LIVE LOGS START ---\n")
    
    def run_spider_sync():
        # By removing capture_output, Scrapy prints directly to your terminal
        return subprocess.run(cmd)

    try:
        loop = asyncio.get_event_loop()
        process = await loop.run_in_executor(None, run_spider_sync)
        
        print("\n--- 🕷️ SCRAPY LIVE LOGS END ---")
            
        results = []
        if os.path.exists(temp_file):
            with open(temp_file, 'r', encoding='utf-8') as f:
                try:
                    results = json.load(f)
                except json.JSONDecodeError:
                    pass
            os.remove(temp_file)
            
        print(f"[YAWC] Spider finished. Found {len(results)} posts.")
        return results

    except Exception as e:
        print(f"\n🚨 FATAL SUBPROCESS ERROR: {repr(e)}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return []# ─── LLM Synthesis ────────────────────────────────────────────────────────────
def _build_prompt(query: str, posts: list[dict]) -> str:
    context_parts = []
    for i, p in enumerate(posts, 1):
        body = p.get("body", "").strip() or "(no body text)"
        context_parts.append(
            f"[Post {i}] {p.get('subreddit', '')} | Score: {p.get('score', 0)}\n"
            f"Title: {p.get('title', '')}\n"
            f"URL: {p.get('url', '')}\n"
            f"Body: {body[:800]}"
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
        response = await loop.run_in_executor(None, lambda: _gemini_model.generate_content(prompt))
        return response.text
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: _anthropic_client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1500, messages=[{"role": "user", "content": prompt}]
        ))
        return response.content[0].text
    else:
        return f"[No LLM configured] Found {len(posts)} Reddit posts about '{query}':\n\n" + \
               "\n".join(f"• {p['title']}" for p in posts[:5])

# ─── API Endpoint ─────────────────────────────────────────────────────────────
@app.get("/api/search")
async def search_stream(q: str = Query(..., min_length=2)) -> EventSourceResponse:
    async def event_generator() -> AsyncIterator[dict]:
        try:
            yield {"event": "status", "data": json.dumps({"message": "🔍 Spinning up YAWC headless browser..."})}
            t0 = time.time()
            
            # Run the isolated spider
            posts = await scrape_reddit_isolated(q, 8)
            scrape_time = round(time.time() - t0, 1)

            if not posts:
                yield {"event": "error", "data": json.dumps({"message": "No Reddit posts found or spider was blocked. Try a different query."})}
                return

            yield {"event": "status", "data": json.dumps({"message": f"📄 Scraped {len(posts)} posts in {scrape_time}s. Synthesizing answer..."})}
            
            answer = await synthesize_with_llm(q, posts)
            sources = [
                {"title": p.get("title", ""), "url": p.get("url", ""), "subreddit": p.get("subreddit", ""), "score": p.get("score", 0)}
                for p in posts
            ]

            yield {"event": "result", "data": json.dumps({"answer": answer, "sources": sources})}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"message": f"Error: {str(exc)}"}) }

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)