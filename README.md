# YAWC — Yet Another Web Crawler

> A real-time, AI-powered research agent that crawls the web live, synthesizes multi-platform results, and streams answers with inline citations — no paywalls, no hallucinations.

---

## What is YAWC?

YAWC is a full-stack research assistant built around a central chat interface. You ask a question, an LLM classifies your intent, and YAWC spins up Playwright-powered Scrapy spiders to scrape the most relevant platforms in real time. Results are chunked into a vector store, synthesized by the LLM, and streamed back to you word-by-word with clickable source citations.

---

## Features & Specialities

- **Intent-aware platform routing** — the LLM classifies every query by intent (text, video, image) and selects the best 2–4 platforms automatically
- **Multi-platform crawling** — Reddit, Quora, StackOverflow, Hacker News, Wikipedia, YouTube, and image sources (Pexels → Pixabay → Unsplash fallback chain)
- **Quick mode vs. Deep Research mode** — controls how many posts are crawled per platform (configurable per spider)
- **RAG-backed follow-ups** — scraped content is chunked and stored in ChromaDB; follow-up questions query memory instead of re-crawling
- **Live SSE streaming** — real-time status updates ("Spinning up YAWC headless browser…", "Scraped 8 posts…") and word-by-word LLM token streaming
- **Inline citations** — the AI cites sources directly in text `[1]`, hyperlinked to the exact post title, upvote score, and original URL
- **Teach YAWC (custom spider generation)** — point YAWC at any URL, walk through the page with Playwright Codegen, and an LLM compiles a production-ready Scrapy spider automatically
- **PDF export** — export any research session as a branded PDF report
- **Playwright trace capture** — every spider run saves a `.zip` trace file for debugging; downloadable and viewable via the Playwright Trace Viewer
- **Dual LLM support** — plug in Google Gemini (`gemini-2.5-flash`) or Anthropic Claude (`claude-sonnet-4`) via a single env var switch
- **Anti-fragile extraction** — spiders avoid brittle CSS selectors; generated spiders grab raw `document.body.innerText` and use an inline LLM call to parse structured JSON

---

## Architecture

### Backend — FastAPI + Scrapy + Playwright

**`app.py`** — FastAPI entry point. Mounts the YAWC router, enables CORS, runs on port 8000.

**`yawc_config.py`** — Central config. Declares all platform spider mappings, quick/deep `k` values, directory paths (ChromaDB, traces, PDFs), LLM provider selection, and a shared `ThreadPoolExecutor`.

**`yawc_routes.py`** — Core API logic:
- `GET /api/search` — the main SSE endpoint. Classifies intent → routes query → selects platforms → runs spiders → ingests to RAG → streams LLM synthesis
- `POST /api/export-pdf` — renders a Playwright-generated PDF from markdown
- `POST /api/teach` — launches Playwright Codegen for a URL, intercepts the raw script, feeds it to the LLM to produce a `YAWCBaseSpider`-compliant spider, saves to `generated/`
- `GET /api/traces/{chat_id}` — lists available trace zips for a session
- `GET /health` — version, provider, platforms, and feature flags

**`yawc_spider.py`** — Async spider runner. Executes each Scrapy spider as a subprocess, reads JSON output from a temp file, and merges results with source indices.

**`yawc_rag.py`** — ChromaDB RAG layer. Ingests posts as 400-word overlapping chunks using `all-MiniLM-L6-v2` embeddings, scoped per `chat_id`. `query_rag()` retrieves top-k relevant chunks for follow-up questions.

**`yawc_base_spider.py`** — Base class for all spiders. Provides Playwright tracing helpers (`_start_trace`, `_stop_trace`), a shared `handle_error` that saves error screenshots + traces, and `base_settings()` — the standard Scrapy + Playwright settings template.

### Platform Spiders

| Spider | Platform | Method | Best For |
|---|---|---|---|
| `reddit_spider.py` | Reddit | Playwright + scroll loop | Community opinions, product picks |
| `quora_spider.py` | Quora | Playwright + cookie auth | Long-form advice, career guidance |
| `stackoverflow_spider.py` | StackOverflow | Playwright | Code bugs, debugging, API usage |
| `hackernews_spider.py` | Hacker News | Algolia JSON API (no JS) | Tech news, tool comparisons |
| `wikipedia_spider.py` | Wikipedia | REST API (no JS) | Factual background, definitions |
| `youtube_spider.py` | YouTube | `window.ytInitialData` + CSS fallback | Tutorials, demos, gameplay |
| `image_spider.py` | Pexels / Pixabay / Unsplash | Playwright + fallback chain | Visual inspiration, stock photos |

### Frontend — Next.js / React

**`app/page.jsx`** — Single-page chat UI built in React with no external component library. Dark monospace theme (`DM Mono`). Key components:
- `YAWCChat` — root component, manages message state, SSE event source lifecycle
- `EmptyState` — suggestion chips that pre-fill the input
- `Bubble` — renders user messages, assistant responses (with inline markdown), and error states
- `StatusBubble` — animated pulsing dots with live status text during crawling
- `Sources` — collapsible source card grid (title, subreddit, score, link)
- `MDText` — inline markdown renderer (bold, code, paragraphs)
- `InputBar` — sticky bottom bar; Enter to send, Shift+Enter for newline

### LLM Routing Pipeline

Every query goes through a two-stage classification before any spider is launched:

1. **Intent Router** (`_RAG_ROUTER_PROMPT`) — classifies as `FOLLOW_UP` (query memory) or `NEW_SEARCH` (crawl), and `VIDEO`, `IMAGE`, or `TEXT`
2. **Platform Selector** (`_PLATFORM_SELECTOR_PROMPT`) — picks the 2–4 best platforms from the available pool based on query type

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Playwright browsers: `playwright install chromium`

### Backend

```bash
# 1. Clone and enter the project
git clone <your-repo>
cd yawc

# 2. Install Python dependencies
pip install fastapi uvicorn scrapy scrapy-playwright playwright \
            chromadb sentence-transformers python-dotenv \
            google-generativeai anthropic sse-starlette psutil

# 3. Create your .env file (see Environment Variables below)
cp .env.example .env

# 4. Start the backend
python app.py
# Server runs at http://localhost:8000
```

### Frontend

```bash
cd frontend   # or wherever your Next.js app lives

# Install dependencies
npm install

# Set the backend URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" >> .env.local

# Start the dev server
npm run dev
# UI runs at http://localhost:3000
```

### Environment Variables — Main Project

Create a `.env` file in your backend root:

```dotenv
# ── YAWC Environment Variables ──────────────────────────────────────────────

# Choose your LLM provider: "gemini" or "anthropic"
LLM_PROVIDER=

# Google Gemini (gemini-2.5-flash — fast + cheap)
GEMINI_API_KEY=

# Anthropic Claude (fallback)
ANTHROPIC_API_KEY=

# ── Next.js frontend ─────────────────────────────────────────────────────────
# Paste your backend URL here (no trailing slash)
NEXT_PUBLIC_API_URL=

# Twitter auth cookie (required for Twitter spider)
TWITTER_AUTH_TOKEN=
```

---

## Benchmark — Headless vs. Headful

The `benchmark/` folder contains a standalone Playwright benchmark (`benchmark.py`) that compares headless vs. headful performance across Reddit, Quora, and Twitter, targeting 50 items per platform.

### Benchmark Environment Variables

Create a `.env` file inside the `benchmark/` folder:

```dotenv
TWITTER_AUTH_TOKEN=
TWITTER_CT0_TOKEN=
QUORA_M_B=
```

**How to get these values:**

**Twitter** — Log into twitter.com in Chrome → F12 → Application → Cookies → `.twitter.com` → copy `auth_token` and `ct0`

**Quora** — Log into quora.com in Chrome → F12 → Application → Cookies → `https://www.quora.com` → copy the `m-b` cookie value

### Running the Benchmark

```bash
cd benchmark
pip install playwright psutil python-dotenv
playwright install chromium
python benchmark.py
```

### Results (Target: 50 items per platform)

| Platform | Items | Headless Time | Headful Time | Headless RAM | Headful RAM |
|---|---|---|---|---|---|
| Reddit | 50 / 50 | 25.9s | 22.8s | 85 MB | 210 MB |
| Quora | 50 / 50 | 58.4s | 45.2s | 95 MB | 275 MB |
| Twitter (X) | 50 / 50 | 34.1s | 31.8s | 110 MB | 315 MB |

### Key Takeaways

**Headless mode** is the clear winner for production use:
- Uses **2.5–3× less RAM** across all platforms (85–110 MB vs. 210–315 MB)
- Marginally slower than headful (by 2–13 seconds), which is an acceptable trade-off at scale
- Easier to run in containerized/CI environments with no display server

**Headful mode** is slightly faster because:
- Platforms like Quora and Twitter are less aggressive about blocking "real-looking" browser sessions
- Useful for debugging or when a site actively resists headless detection

YAWC's main spiders run headless by default. Pass `-a headless=false` to any spider for headful mode during development.

---

## Teach YAWC — Custom Spider Generation

YAWC can generate production spiders for any website in minutes:

1. Call `POST /api/teach` with a `url` and optional `spider_name`
2. YAWC launches **Playwright Codegen** — a browser opens and records your navigation
3. Walk through the target site (search, scroll, interact)
4. When you close the browser, YAWC intercepts the raw recorded script and feeds it to the LLM
5. The LLM compiles a full `YAWCBaseSpider` subclass that uses `document.body.innerText` + an inline LLM call for extraction (no brittle CSS selectors)
6. The spider is saved to `generated/<name>_spider.py` in your backend directory

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/search?q=&mode=&chat_id=` | Main SSE search stream |
| `POST` | `/api/export-pdf` | Export session as PDF |
| `POST` | `/api/teach` | Generate custom spider via Codegen |
| `GET` | `/api/traces/{chat_id}` | List trace files for a session |
| `GET` | `/api/traces/{chat_id}/download/{filename}` | Download a trace zip |
| `POST` | `/api/traces/{chat_id}/view/{filename}` | Launch Playwright Trace Viewer |
| `GET` | `/health` | Health check + feature flags |

---

## Project Structure

```
yawc/
├── app.py                  # FastAPI entry point
├── yawc_config.py          # Central config & platform registry
├── yawc_routes.py          # API routes, LLM routing, SSE streaming
├── yawc_spider.py          # Async spider subprocess runner
├── yawc_rag.py             # ChromaDB RAG ingestion & retrieval
├── yawc_base_spider.py     # Base Scrapy spider with tracing
├── reddit_spider.py
├── quora_spider.py
├── stackoverflow_spider.py
├── hackernews_spider.py
├── wikipedia_spider.py
├── youtube_spider.py
├── image_spider.py
├── generated/              # Auto-generated spiders from Teach YAWC
├── traces/                 # Playwright trace zips per chat_id
├── pdfs/                   # Exported research PDFs
├── chroma_db/              # Persistent ChromaDB vector store
├── benchmark/
│   ├── benchmark.py        # Headless vs. headful comparison runner
│   ├── reddit_spider.py    # Benchmark-specific spider variants
│   ├── quora_spider.py
│   ├── twitter_spider.py
│   ├── yawc_base_spider.py
│   └── .env                # Benchmark credentials
└── frontend/
    └── app/
        └── page.jsx        # Next.js chat UI
```
