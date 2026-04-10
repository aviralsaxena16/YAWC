
# ══════════════════════════════════════════════════════════════════════════════
# stackoverflow_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider

class StackOverflowSpider(YAWCBaseSpider):
    """
    Scrapes StackOverflow search results.
    Best for: code bugs, programming how-to, API usage, debugging.
    Output: url, title, body (accepted answer snippet), score, platform="StackOverflow"
    """
    name = "stackoverflow_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=6),
        "PLAYWRIGHT_ABORT_REQUEST": lambda req: req.resource_type in {
            "image", "media", "font", "stylesheet",
            "websocket", "eventsource", "manifest",
        },
    }

    def start_requests(self):
        encoded = self.query.replace(" ", "+")
        url = f"https://stackoverflow.com/search?q={encoded}&tab=votes"
        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 4000)],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        questions = await page.evaluate(f"""
            () => {{
                const results = [];
                const items = document.querySelectorAll('.js-search-results .s-post-summary');
                for (const item of items) {{
                    if (results.length >= {self.k}) break;
                    const titleEl  = item.querySelector('h3 a, .s-link');
                    const title    = titleEl?.textContent?.trim() || '';
                    const href     = titleEl?.getAttribute('href') || '';
                    const url      = href.startsWith('http') ? href
                                   : 'https://stackoverflow.com' + href;
                    const excerpt  = item.querySelector('.s-post-summary--content-excerpt');
                    const body     = excerpt?.textContent?.trim() || '';
                    const voteEl   = item.querySelector(
                        '.s-post-summary--stats-item__emphasized .s-post-summary--stats-item-number'
                    );
                    const score = voteEl?.textContent?.trim() || '0';
                    if (title && url)
                        results.push({{ title, url, body, score }});
                }}
                return results;
            }}
        """)
        await page.close()

        for q in questions:
            yield {
                "url":      q.get("url", ""),
                "title":    q.get("title", "").strip(),
                "body":     q.get("body", "").strip(),
                "score":    q.get("score", "0"),
                "platform": "StackOverflow",
            }

    async def handle_error(self, failure):
        await super().handle_error(failure)

