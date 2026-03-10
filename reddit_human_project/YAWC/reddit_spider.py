"""
YAWC Reddit Spider v2 — Parallel Search-Mode Spider
Features:
  - Query-based Reddit search (not feed)
  - Skips comments for speed
  - Blocks all non-HTML resources
  - Writes results to a temp JSON file (read by async subprocess runner in main.py)
  - Supports quick (k=8) and deep (k=30) modes
"""

import asyncio
import scrapy
from scrapy_playwright.page import PageMethod


# ─── Resource Blocker ────────────────────────────────────────────────────────
def should_abort_request(req):
    """Block everything non-essential. Only HTML pages matter."""
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


class YAWCSearchSpider(scrapy.Spider):
    name = "yawc_search"

    custom_settings = {
        # ── Twisted / Playwright wiring ───────────────────────────────────────
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,   # Silent in production; set False to debug visually
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--blink-settings=imagesEnabled=false",
            ],
        },

        # ── Speed settings ────────────────────────────────────────────────────
        # CONCURRENT_REQUESTS is the KEY parallel lever.
        # All post-detail requests fire simultaneously — true parallel crawl.
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 20_000,
        "CONCURRENT_REQUESTS": 12,        # ← parallel post fetches (increase carefully)
        "CONCURRENT_REQUESTS_PER_DOMAIN": 12,
        "DOWNLOAD_DELAY": 0,              # no artificial throttle
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,                 # fail fast
        "LOG_LEVEL": "INFO",

        # ── Output ────────────────────────────────────────────────────────────
        # Output file is set via -o flag from main.py subprocess call.
        # No FEEDS setting here — keeps spider reusable.
    }

    def __init__(self, query: str = "", k: str = "8", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.k = int(k)
        encoded = query.replace(" ", "+")
        self.search_url = (
            f"https://www.reddit.com/search/?q={encoded}&type=link&sort=relevance"
        )

    # ── Step 1: Load the Reddit search results page ───────────────────────────
    def start_requests(self):
        yield scrapy.Request(
            url=self.search_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Wait generously for Reddit's JS to hydrate
                    PageMethod("wait_for_timeout", 5000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    # ── Step 2: Extract post permalinks from search results ───────────────────
    async def parse_search(self, response):
        page = response.meta.get("playwright_page")

        permalinks = await page.evaluate("""
            () => {
                // Try modern shreddit-post web components first
                let posts = Array.from(document.querySelectorAll('shreddit-post'))
                                 .map(p => p.getAttribute('permalink'));

                // Fallback: any link containing /comments/
                if (posts.length === 0) {
                    posts = Array.from(document.querySelectorAll('a[href*="/comments/"]'))
                                 .map(a => a.getAttribute('href'));
                }

                // Deduplicate + filter nulls
                return [...new Set(posts)].filter(Boolean);
            }
        """)

        await page.close()

        if not permalinks:
            self.logger.warning(
                "\n[YAWC] ⚠ No post links found! "
                "Reddit may be blocking the headless browser.\n"
            )
            return

        self.logger.info(
            f"[YAWC] ✓ Found {len(permalinks)} posts for '{self.query}'. "
            f"Scraping top {self.k} in parallel (CONCURRENT_REQUESTS={self.settings.getint('CONCURRENT_REQUESTS')})…"
        )

        # ★ All requests are yielded at once → Scrapy dispatches them in parallel
        # up to CONCURRENT_REQUESTS. This is the core parallel crawl pattern.
        for link in permalinks[: self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Wait only for the post body to render — NO comment wait
                        PageMethod("wait_for_timeout", 3000),
                    ],
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )

    # ── Step 3: Extract post data (body only, zero comment scraping) ──────────
    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

        # Multiple CSS selector fallbacks for Reddit's evolving shadow DOM
        title = (
            response.css("h1::text").get()
            or response.css('[slot="title"]::text').get()
            or "Untitled"
        )

        body_parts = (
            response.css("shreddit-post [slot='text-body'] p::text").getall()
            or response.css("div[id$='-post-rtjson-content'] p::text").getall()
            or response.css('[data-testid="post-content"] p::text').getall()
        )

        post_data = {
            "url": response.url,
            "subreddit": response.css(
                "shreddit-post::attr(subreddit-prefixed-name)"
            ).get() or "",
            "score": response.css("shreddit-post::attr(score)").get() or "0",
            "title": title.strip() if title else "",
            "body": " ".join(body_parts).strip(),
        }

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield post_data

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC] ✗ Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass
