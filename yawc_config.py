from __future__ import annotations

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

# ─── Directories ──────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"))
TRACE_DIR = Path(os.getenv("TRACE_DIR", "./traces"))
PDF_DIR = Path(os.getenv("PDF_DIR", "./pdfs"))
SPIDER_DIR = Path(os.getenv("SPIDER_DIR", "."))

for _d in (CHROMA_PERSIST_DIR, TRACE_DIR, PDF_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ─── LLM Setup (will be used by route modules) ─────────────────────────────────
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

THREAD_POOL = ThreadPoolExecutor(max_workers=8)

PLATFORM_SPIDERS: dict[str, str] = {
    "reddit": "reddit_spider.py",
    "stackoverflow": "stackoverflow_spider.py",
    "hackernews": "hackernews_spider.py",
    "wikipedia": "wikipedia_spider.py",
    "quora": "quora_spider.py",
    "youtube": "youtube_spider.py",
    "image": "image_spider.py",
}

PLATFORM_K: dict[str, dict[str, int]] = {
    "reddit": {"quick": 6, "deep": 20},
    "stackoverflow": {"quick": 4, "deep": 10},
    "hackernews": {"quick": 4, "deep": 10},
    "wikipedia": {"quick": 2, "deep": 4},
    "quora": {"quick": 3, "deep": 8},
    "youtube": {"quick": 3, "deep": 6},
    "image": {"quick": 6, "deep": 12},
}
