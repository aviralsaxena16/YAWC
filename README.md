# YAWC — Yet Another Web Crawler

> A "Deep Research" chat interface that scrapes Reddit **live** with a headless browser,  
> feeds the results into Gemini / Claude, and streams the answer back to a slick Next.js UI.

```
User query → FastAPI → Scrapy + Playwright → Reddit live scrape
         ↘ SSE status events ("Searching…", "Scraped 8 posts…")
                            ↓ in-memory posts
                      Gemini / Claude LLM
                            ↓ synthesized answer
                      Next.js chat UI (streaming SSE)
```

---

## Project Structure

```
yawc/
├── reddit_spider.py   # Scrapy + Playwright spider (search-mode, no comments)
├── main.py            # FastAPI backend (Crochet + SSE streaming)
├── YAWCChat.jsx       # Next.js / React chat UI (drop into app/page.jsx)
├── .env.example       # Copy to .env and fill in API keys
└── README.md
```

---

## Setup

### 1 — Python backend

```bash
# Create a virtual env
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install Python deps
pip install fastapi uvicorn scrapy scrapy-playwright \
            crochet google-generativeai anthropic \
            sse-starlette python-dotenv twisted

# Install Playwright browser (Chromium only — lean)
playwright install chromium --with-deps

# Copy env file and fill in your keys
cp .env.example .env

# Start the API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2 — Next.js frontend

```bash
npx create-next-app@latest yawc-ui --app --typescript --tailwind
cd yawc-ui

# Drop YAWCChat.jsx into the app directory:
cp ../YAWCChat.jsx app/page.jsx   # or app/page.tsx (rename accordingly)

# Add the API URL to .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" >> .env.local

# Run dev server
npm run dev
```

Open **http://localhost:3000** — done.

---

## How It Works

### Why Crochet instead of subprocess?

Scrapy is built on the Twisted async framework.  
FastAPI is built on asyncio.  
The two reactors **cannot coexist in the same thread**, and Twisted's reactor  
**cannot be restarted** once stopped (`ReactorNotRestartable` error).

**Crochet** solves this by running the Twisted reactor in a dedicated background thread
and exposing a clean `@crochet.run_in_reactor` decorator. The FastAPI thread calls
`eventual.wait()` which blocks only a thread pool worker — the asyncio event loop stays free.

```
FastAPI thread          Twisted reactor thread (Crochet)
─────────────           ──────────────────────────────────
run_in_executor  ──────► @run_in_reactor → CrawlerRunner.crawl()
eventual.wait()  ◄──────  Deferred resolves when crawl finishes
return posts             (reactor keeps running for next request)
```

### In-Memory Handoff (zero disk I/O)

The spider receives a `result_collector: list` reference on construction.
In `parse_post`, it calls `self.result_collector.append(post_data)`.
The same list object is passed in from `main.py` and read after crawl completion.
**No JSON files, no temp files, no subprocess pipes.**

### SSE Streaming (live status updates)

The `/api/search` endpoint returns a `EventSourceResponse` and streams three event types:

| Event    | When                                     | Payload                         |
|----------|------------------------------------------|---------------------------------|
| `status` | During scraping / synthesis              | `{ message: "..." }`           |
| `result` | Done — full answer ready                 | `{ answer, sources[] }`        |
| `error`  | Scrape failed / no posts found           | `{ message: "..." }`           |

The Next.js UI connects with the native browser `EventSource` API — no libraries needed.

---

## Latency Optimization Techniques

| Technique | Saving |
|-----------|--------|
| `PLAYWRIGHT_ABORT_REQUEST` blocks images, fonts, CSS, media | ~60% page load time |
| No `shreddit-comment` wait — skip comments entirely | ~2–4s per post |
| `CONCURRENT_REQUESTS: 8` — all posts fetched in parallel | Linear → parallel |
| `RETRY_TIMES: 1` — fail fast, don't retry forever | Removes long tail |
| `AUTOTHROTTLE_ENABLED: False` — no artificial rate limiting | Removes delay jitter |
| `DOWNLOAD_DELAY: 0` — no wait between requests | Removes constant delay |
| In-memory handoff — no disk write/read round-trip | ~10–50ms |
| `k=8` by default — only top 8 posts scraped | Caps total scrape time |
| `--blink-settings=imagesEnabled=false` Chromium flag | Extra insurance |
| Body text capped at 800 chars per post in prompt | Smaller LLM prompt = faster |

**Typical end-to-end latency:** 8–18 seconds  
(3–6s scrape + 2–5s Gemini synthesis + SSE overhead)

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `anthropic` |
| `GEMINI_API_KEY` | — | Your Google AI Studio key |
| `ANTHROPIC_API_KEY` | — | Your Anthropic key |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for the Next.js UI |

Change `k` (number of posts) in `scrape_reddit_sync(query, k=8)` in `main.py`.

---

## Notes & Caveats

- Reddit may block headless Chromium. If scraping fails, try enabling `headless: False` temporarily to debug.
- For production, add request headers to mimic a real browser via `PLAYWRIGHT_DEFAULT_NAVIGATION_OPTIONS`.
- The Gemini `gemini-2.5-flash` model is recommended for speed. Swap to `gemini-2.0-pro` for quality.
- YAWC is for personal/research use. Always respect Reddit's Terms of Service.
