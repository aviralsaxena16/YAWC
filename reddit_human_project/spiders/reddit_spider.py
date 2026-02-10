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

    def __init__(self, target=None, k=50, *args, **kwargs):
        super(HumanRedditSpider, self).__init__(*args, **kwargs)
        self.k = int(k)  # Goal: How many posts to collect before opening details
        if target:
            self.start_url = f"https://www.reddit.com/r/{target}/"
        else:
            self.start_url = "https://www.reddit.com/"

    def start_requests(self):
        yield scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                # Initial wait to ensure the first set of posts render
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
        max_scrolls = self.k // 5  # Estimated scrolls to reach 'k' posts

        self.logger.info(f"[*] Starting smooth scroll to collect {self.k} posts...")

        # --- SMOOTH SCROLL LOOP ---
        while len(all_links) < self.k and scroll_attempts < max_scrolls:
            # Scroll down like a human
            await page.evaluate("window.scrollBy(0, 1500)")
            # Wait for new posts to 'hydrate' or load in the DOM
            await page.wait_for_timeout(2500) 
            
            # Extract links currently visible
            current_links = await page.evaluate("""
                () => {
                    const posts = document.querySelectorAll('shreddit-post');
                    return Array.from(posts).map(p => p.getAttribute('permalink')).filter(l => l);
                }
            """)
            
            for link in current_links:
                all_links.add(link)
            
            scroll_attempts += 1
            self.logger.info(f"[*] Scrolled {scroll_attempts} times. Collected {len(all_links)} links so far.")

        # Once we have enough links, we yield requests for each individual post
        self.logger.info(f"[+] Reached goal. Now deep scraping {len(all_links)} posts...")

        for link in list(all_links)[:self.k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "shreddit-comment", timeout=15000),
                    ]
                },
                callback=self.parse_post,
                errback=self.handle_error
            )
        
        # Close the feed browser instance
        await page.close()

    async def parse_post(self, response):
        page = response.meta.get("playwright_page")
        
        data = {
            "url": response.url,
            "title": response.css("h1::text").get(),
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
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except:
                pass