
# ══════════════════════════════════════════════════════════════════════════════
# wikipedia_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from yawc_base_spider import YAWCBaseSpider

class WikipediaSpider(YAWCBaseSpider):
    """
    Fetches Wikipedia article summaries via the Wikipedia REST API (no scraping needed).
    Best for: factual background, definitions, historical context, science.
    Output: url, title, body (intro extract), score="N/A", platform="Wikipedia"
    """
    name = "wikipedia_spider"

    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "CONCURRENT_REQUESTS":            4,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY":       0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES":          1,
        "LOG_LEVEL":            "INFO",
    }

    def start_requests(self):
        import urllib.parse
        # Step 1: Wikipedia search API to find relevant articles
        encoded = urllib.parse.quote(self.query)
        url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=search&list=search&srsearch={encoded}"
            f"&srlimit={self.k}&format=json&origin=*"
        )
        yield scrapy.Request(url=url, callback=self.parse_search, errback=self.handle_error)

    def parse_search(self, response):
        try:
            data = response.json()
        except Exception:
            self.logger.warning("[Wikipedia] Failed to parse search JSON")
            return

        results = data.get("query", {}).get("search", [])
        for result in results[: self.k]:
            title = result.get("title", "")
            if not title:
                continue
            import urllib.parse
            encoded_title = urllib.parse.quote(title.replace(" ", "_"))
            # Step 2: Fetch full intro extract per article
            api_url = (
                f"https://en.wikipedia.org/w/api.php"
                f"?action=query&titles={encoded_title}"
                f"&prop=extracts&exintro=true&explaintext=true"
                f"&format=json&origin=*"
            )
            yield scrapy.Request(
                url=api_url,
                meta={"article_title": title},
                callback=self.parse_article,
                errback=self.handle_error,
            )

    def parse_article(self, response):
        title = response.meta.get("article_title", "")
        try:
            data  = response.json()
            pages = data.get("query", {}).get("pages", {})
            page  = next(iter(pages.values()), {})
            body  = page.get("extract", "")
            # Trim to ~800 words for context efficiency
            body  = " ".join(body.split()[:800])
        except Exception:
            body = ""

        import urllib.parse
        encoded_title = urllib.parse.quote(title.replace(" ", "_"))
        yield {
            "url":      f"https://en.wikipedia.org/wiki/{encoded_title}",
            "title":    title,
            "body":     body,
            "score":    "N/A",
            "platform": "Wikipedia",
        }

    async def handle_error(self, failure):
        self.logger.warning(f"[Wikipedia] Failed: {failure.request.url}")

