"""
YAWC Reddit Spider — Query-Based, In-Memory, No-Comments
Optimized for speed: blocks media, skips comments, returns data in-memory.
"""

import asyncio
import scrapy
from scrapy_playwright.page import PageMethod
from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from twisted.internet import defer
import crochet

try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    pass

# ─── Resource Blocker ────────────────────────────────────────────────────────
def should_abort_request(req):
    """Block everything non-essential. Only HTML pages matter."""
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


# ─── Spider ──────────────────────────────────────────────────────────────────
class YAWCSearchSpider(scrapy.Spider):
    name = "yawc_search"

    custom_settings = {
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 20_000,
        "CONCURRENT_REQUESTS": 8,          # parallel post fetches
        "DOWNLOAD_DELAY": 0,               # no artificial delay
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,                  # fail fast
        "LOG_LEVEL": "WARNING",
    }

    def __init__(self, query: str = "", k: int = 8, result_collector=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.k = int(k)
        self.result_collector: list = result_collector if result_collector is not None else []
        encoded = query.replace(" ", "+")
        self.search_url = (
            f"https://www.reddit.com/search/?q={encoded}&type=link&sort=relevance"
        )

    # ── Step 1: Load search results page ──────────────────────────────────────
    def start_requests(self):
        yield scrapy.Request(
            url=self.search_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod(
                        "wait_for_selector",
                        "shreddit-post",
                        timeout=15_000,
                    ),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    # ── Step 2: Collect top-k post permalinks ──────────────────────────────────
    async def parse_search(self, response):
        page = response.meta.get("playwright_page")

        permalinks = await page.evaluate("""
            () => {
                const posts = document.querySelectorAll('shreddit-post');
                return Array.from(posts)
                    .map(p => p.getAttribute('permalink'))
                    .filter(Boolean);
            }
        """)

        await page.close()

        self.logger.warning(f"[YAWC] Found {len(permalinks)} posts for '{self.query}'. Scraping top {self.k}...")

        for link in permalinks[: self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Wait only for the post body, NOT comments
                        PageMethod(
                            "wait_for_selector",
                            "shreddit-post",
                            timeout=10_000,
                        ),
                    ],
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )

    # ── Step 3: Extract post data (body only, no comments) ────────────────────
    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

        # Multiple CSS fallbacks for Reddit's evolving DOM
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

        subreddit = response.css("shreddit-post::attr(subreddit-prefixed-name)").get() or ""
        score = response.css("shreddit-post::attr(score)").get() or "0"

        post_data = {
            "url": response.url,
            "subreddit": subreddit,
            "score": score,
            "title": title.strip() if title else "",
            "body": " ".join(body_parts).strip(),
        }

        # ★ In-Memory Handoff: append directly to shared list
        self.result_collector.append(post_data)

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield post_data  # also yields normally (useful for Scrapy pipelines)

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC] Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass


# ─── Scrapy Settings ──────────────────────────────────────────────────────────
def get_yawc_settings() -> dict:
    return {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--blink-settings=imagesEnabled=false",
            ],
        },
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "CONCURRENT_REQUESTS": 8,
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "WARNING",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    }
