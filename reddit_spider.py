
# ══════════════════════════════════════════════════════════════════════════════
# reddit_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider


class RedditSpider(YAWCBaseSpider):
    """
    Scrapes Reddit search results.
    Best for: product recommendations, hobbyist advice, raw community opinions.
    Output: url, title, body, subreddit, score, platform="Reddit"
    """
    name = "reddit_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=12),
        "PLAYWRIGHT_ABORT_REQUEST": lambda req: req.resource_type in {
            "image", "media", "font", "stylesheet",
            "websocket", "eventsource", "manifest",
        },
    }

    def start_requests(self):
        encoded = self.query.replace(" ", "+")
        url = f"https://www.reddit.com/search/?q={encoded}&type=link&sort=relevance"
        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 5000)],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        permalinks = await page.evaluate("""
            () => {
                let posts = Array.from(document.querySelectorAll('shreddit-post'))
                                 .map(p => p.getAttribute('permalink'));
                if (!posts.length)
                    posts = Array.from(document.querySelectorAll('a[href*="/comments/"]'))
                                 .map(a => a.getAttribute('href'));
                return [...new Set(posts)].filter(Boolean);
            }
        """)
        await page.close()

        if not permalinks:
            self.logger.warning("[Reddit] No posts found — Reddit may be blocking.")
            return

        for link in permalinks[: self.k]:
            yield scrapy.Request(
                url=response.urljoin(link),
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [PageMethod("wait_for_timeout", 3000)],
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )

    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

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
        subreddit = response.css(
            "shreddit-post::attr(subreddit-prefixed-name)"
        ).get() or ""
        score = response.css("shreddit-post::attr(score)").get() or "0"

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield {
            "url":       response.url,
            "title":     (title or "").strip(),
            "body":      " ".join(body_parts).strip(),
            "subreddit": subreddit,
            "score":     score,
            "platform":  "Reddit",
        }

