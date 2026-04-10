
# ══════════════════════════════════════════════════════════════════════════════
# quora_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider

def _quora_abort(req) -> bool:
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


class QuoraSpider(YAWCBaseSpider):
    """
    Scrapes Quora search results.
    Best for: long-form life advice, philosophical questions, career guidance, anecdotes.
    Note: Quora aggressively blocks bots; results may be limited.
    Output: url, title, body (answer snippet), score="0", platform="Quora"
    """
    name = "quora_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_ABORT_REQUEST": _quora_abort,
        # Longer timeout — Quora uses aggressive JS rendering
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
    }

    def start_requests(self):
        import urllib.parse
        encoded = urllib.parse.quote(self.query)
        url = f"https://www.quora.com/search?q={encoded}"
        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 6000)],
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
                const seen = new Set();
                // Quora uses various link patterns
                const links = document.querySelectorAll(
                    'a[href*="/What"], a[href*="/How"], a[href*="/Why"], '
                    'a[href*="/Is"], a[href*="/Are"], a[href*="/Can"], a[href*="/Should"]'
                );
                for (const link of links) {{
                    if (results.length >= {self.k}) break;
                    const href  = link.getAttribute('href') || '';
                    const url   = href.startsWith('http') ? href
                                : 'https://www.quora.com' + href;
                    const title = link.textContent?.trim() || '';
                    if (!title || title.length < 10 || seen.has(url)) continue;
                    seen.add(url);
                    const parent  = link.closest('[class*="question"]') || link.parentElement;
                    const snippet = parent?.querySelector('[class*="answer"], [class*="excerpt"]');
                    const body    = snippet?.textContent?.trim() || '';
                    results.push({{ title, url, body }});
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
                "score":    "0",
                "platform": "Quora",
            }


