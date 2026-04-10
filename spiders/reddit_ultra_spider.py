import asyncio
import scrapy
from scrapy_playwright.page import PageMethod  # type: ignore[import]


# Helper function to block unnecessary resources and speed up Playwright
def should_abort_request(request):
    """Block images, fonts, media, AND websockets to save max bandwidth."""
    return request.resource_type in ["image", "media", "font", "stylesheet", "websocket", "eventsource", "manifest"]

class UltraRedditSpider(scrapy.Spider):
    name = "reddit_ultra"

    # Register the request interceptor and ultra-fast settings
    custom_settings = {
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,  # <-- Runs invisibly in the background
            "args": ["--disable-gpu", "--blink-settings=imagesEnabled=false"]
        },
        "CONCURRENT_REQUESTS": 8,  # <-- Scrape 8 posts at the exact same time
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "LOG_LEVEL": "INFO", 
    }

    def __init__(self, target=None, k=50, username=None, password=None, *args, **kwargs):
        super(UltraRedditSpider, self).__init__(*args, **kwargs)
        self.k = int(k)
        self.username = username
        self.password = password
        
        if target:
            self.start_url = f"https://www.reddit.com/r/{target}/"
            self.target_name = f"r/{target}"
        else:
            self.start_url = "https://www.reddit.com/"
            self.target_name = "Home Feed"

    def start_requests(self):
        if self.username and self.password:
            self.logger.info(f"[*] Auth credentials found. Attempting login as {self.username}...")
            yield scrapy.Request(
                url="https://www.reddit.com/login/",
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": "auth_session",
                },
                callback=self.parse_login,
                errback=self.handle_error
            )
        else:
            self.logger.info(f"[*] No credentials provided. Scraping {self.target_name} anonymously.")
            yield self._build_home_request()

    async def parse_login(self, response):
        page = response.meta["playwright_page"]
        try:
            await page.wait_for_selector('input[name="username"]', timeout=15000)
            await page.fill('input[name="username"]', self.username)
            await page.fill('input[name="password"]', self.password)
            
            async with page.expect_navigation(timeout=30000):
                await page.click('button[type="submit"]')
                
            await page.close()
            yield self._build_home_request(context_name="auth_session")
        except Exception as e:
            self.logger.error(f"[!] Login failed: {e}")
            await page.close()

    def _build_home_request(self, context_name="default"):
        return scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_context": context_name,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "shreddit-post", timeout=15000),
                ],
            },
            callback=self.parse_home,
            errback=self.handle_error
        )

    async def parse_home(self, response):
        page = response.meta.get("playwright_page")
        if not page:
            return

        all_links = set()
        scroll_attempts = 0
        max_scrolls = max(self.k // 5, 1)

        while len(all_links) < self.k and scroll_attempts < max_scrolls:
            await page.evaluate("window.scrollBy(0, 2000)")
            # Reduced timeout for faster scrolling
            await page.wait_for_timeout(1000) 
            
            current_links = await page.evaluate("""
                () => {
                    const posts = document.querySelectorAll('shreddit-post');
                    return Array.from(posts).map(p => p.getAttribute('permalink')).filter(l => l);
                }
            """)
            
            for link in current_links:
                all_links.add(link)
            
            scroll_attempts += 1

        self.logger.info(f"[+] Scroll complete. Deep scraping {len(all_links)} posts...")
        context_name = response.meta.get("playwright_context", "default")

        for link in list(all_links)[:self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": context_name,
                    "playwright_page_methods": [
                        # REMOVED wait_for_selector("shreddit-comment")!
                        # Just wait for basic DOM to load, then immediately scrape.
                        PageMethod("wait_for_load_state", "domcontentloaded"),
                        PageMethod("wait_for_timeout", 1000), 
                    ]
                },
                callback=self.parse_post,
                errback=self.handle_error
            )
        
        await page.close()

    async def parse_post(self, response):
        page = response.meta.get("playwright_page")
        
        # REMOVED comments array extraction
        data = {
            "url": response.url,
            "title": response.css("h1::text").get(),
            "body": response.css("shreddit-post [slot='text-body'] p::text").getall() or \
                    response.css("div[id$='-post-rtjson-content'] p::text").getall(),
        }
        
        if page:
            try:
                await page.close()
            except:
                pass
            
        yield data

    async def handle_error(self, failure):
        self.logger.error(f"[!] Request Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except:
                pass