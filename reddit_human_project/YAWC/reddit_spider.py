import asyncio
import scrapy
from scrapy_playwright.page import PageMethod


def should_abort_request(req):
    return req.resource_type in {"image", "media", "font", "stylesheet", "websocket", "eventsource", "manifest"}

class YAWCSearchSpider(scrapy.Spider):
    name = "yawc_search"

    custom_settings = {
        # --- CRITICAL SETTINGS FOR `runspider` ---
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": False,  # Keep False so you can see if Reddit blocks you during testing
            "args": [
                "--disable-gpu",
                "--blink-settings=imagesEnabled=false",
            ],
        },
        # --- YOUR SPEED OPTIMIZATIONS ---
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 20_000,
        "CONCURRENT_REQUESTS": 8,
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, query: str = "", k: str = "8", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.k = int(k)
        encoded = query.replace(" ", "+")
        self.search_url = f"https://www.reddit.com/search/?q={encoded}&type=link&sort=relevance"

    def start_requests(self):
        yield scrapy.Request(
            url=self.search_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # 1. Remove the strict selector. Just give Reddit 5 seconds to load naturally.
                    PageMethod("wait_for_timeout", 5000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        
        # 2. Super-robust extraction with fallbacks
        permalinks = await page.evaluate("""
            () => {
                // Try modern shreddit-post first
                let posts = Array.from(document.querySelectorAll('shreddit-post')).map(p => p.getAttribute('permalink'));
                
                // Fallback: look for ANY link that goes to a Reddit comment thread
                if (posts.length === 0) {
                    posts = Array.from(document.querySelectorAll('a[href*="/comments/"]'))
                                 .map(a => a.getAttribute('href'));
                }
                
                // Remove duplicates and empty values
                return [...new Set(posts)].filter(Boolean);
            }
        """)
        await page.close()

        if not permalinks:
            self.logger.warning("\n[!] YAWC Warning: No links found! Reddit might be blocking us or the page structure changed.\n")

        for link in permalinks[: self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Give the post details 3 seconds to load, no strict tripwires
                        PageMethod("wait_for_timeout", 3000),
                    ],
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )
    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

        title = response.css("h1::text").get() or response.css('[slot="title"]::text').get() or "Untitled"
        body_parts = response.css("shreddit-post [slot='text-body'] p::text").getall() or \
                     response.css("div[id$='-post-rtjson-content'] p::text").getall()
        
        post_data = {
            "url": response.url,
            "subreddit": response.css("shreddit-post::attr(subreddit-prefixed-name)").get() or "",
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
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass