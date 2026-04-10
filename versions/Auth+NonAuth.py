import asyncio
import scrapy
from scrapy_playwright.page import PageMethod

# Fix for Windows Selector Event Loop
try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    pass

class HumanRedditSpider(scrapy.Spider):
    name = "reddit_human"

    def __init__(self, target=None, k=50, username=None, password=None, *args, **kwargs):
        super(HumanRedditSpider, self).__init__(*args, **kwargs)
        self.k = int(k)
        self.username = username
        self.password = password
        
        # Determine the target URL
        if target:
            self.start_url = f"https://www.reddit.com/r/{target}/"
            self.target_name = f"r/{target}"
        else:
            self.start_url = "https://www.reddit.com/"
            self.target_name = "Home Feed"

    def start_requests(self):
        # 1. AUTHENTICATED MODE
        if self.username and self.password:
            self.logger.info(f"[*] Auth credentials found. Attempting login as {self.username}...")
            yield scrapy.Request(
                url="https://www.reddit.com/login/",
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": "auth_session", # Create a named context to persist cookies
                },
                callback=self.parse_login,
                errback=self.handle_error
            )
        
        # 2. ANONYMOUS MODE
        else:
            self.logger.info(f"[*] No credentials provided. Scraping {self.target_name} anonymously.")
            yield self._build_home_request()

    async def parse_login(self, response):
        """Handles the login form interaction."""
        page = response.meta["playwright_page"]
        
        try:
            self.logger.info("[-] Filling login credentials...")
            
            # Wait for username field (Reddit login pages change often, these are standard IDs)
            await page.wait_for_selector('input[name="username"]')
            await page.fill('input[name="username"]', self.username)
            await page.fill('input[name="password"]', self.password)
            
            # Click Login and wait for navigation
            self.logger.info("[-] Clicking login...")
            async with page.expect_navigation(timeout=30000):
                await page.click('button[type="submit"]')
                
            self.logger.info("[+] Login successful! Proceeding to target.")
            
            # Close login page to free resources
            await page.close()

            # Now start the main scraping loop using the SAME context (cookies persist)
            yield self._build_home_request(context_name="auth_session")

        except Exception as e:
            self.logger.error(f"[!] Login failed: {e}")
            await page.close()

    def _build_home_request(self, context_name="default"):
        """Helper to build the main feed request."""
        return scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_context": context_name,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "shreddit-post", timeout=20000),
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
        max_scrolls = self.k // 5 

        self.logger.info(f"[*] Starting smooth scroll on {self.target_name}...")

        # --- SMOOTH SCROLL LOOP ---
        while len(all_links) < self.k and scroll_attempts < max_scrolls:
            # Scroll logic
            await page.evaluate("window.scrollBy(0, 1500)")
            await page.wait_for_timeout(2500) 
            
            # Extract links
            current_links = await page.evaluate("""
                () => {
                    const posts = document.querySelectorAll('shreddit-post');
                    return Array.from(posts).map(p => p.getAttribute('permalink')).filter(l => l);
                }
            """)
            
            new_count = 0
            for link in current_links:
                if link not in all_links:
                    all_links.add(link)
                    new_count += 1
            
            scroll_attempts += 1
            if new_count > 0:
                self.logger.info(f"[*] Scroll {scroll_attempts}: Found {new_count} new posts (Total: {len(all_links)})")

        self.logger.info(f"[+] Scroll complete. Scraping details for {len(all_links)} posts...")

        # Pass the context name to ensure detail pages use the same login session
        context_name = response.meta.get("playwright_context", "default")

        for link in list(all_links)[:self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": context_name, # Critical for auth persistence
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "shreddit-comment", timeout=15000),
                    ]
                },
                callback=self.parse_post,
                errback=self.handle_error
            )
        
        await page.close()

    async def parse_post(self, response):
        page = response.meta.get("playwright_page")
        
        data = {
            "url": response.url,
            "title": response.css("h1::text").get(),
            # Fallback selectors for different reddit layouts
            "body": response.css("shreddit-post [slot='text-body'] p::text").getall() or \
                    response.css("div[id$='-post-rtjson-content'] p::text").getall(),
            "comments": response.css("shreddit-comment div[slot='comment'] p::text").getall()
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