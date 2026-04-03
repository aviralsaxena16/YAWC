
# ══════════════════════════════════════════════════════════════════════════════
# hackernews_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from yawc_base_spider import YAWCBaseSpider

class HackerNewsSpider(YAWCBaseSpider):
    """
    Scrapes Hacker News search via Algolia HN Search API (JSON — no JS rendering needed).
    Best for: tech news, engineering discussions, tool comparisons, startup insight.
    Output: url, title, body (story text / comment), score (points), platform="HackerNews"
    """
    name = "hackernews_spider"

    # HN Algolia API is plain JSON — no Playwright needed
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "CONCURRENT_REQUESTS":            8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY":       0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES":          1,
        "LOG_LEVEL":            "INFO",
    }

    def start_requests(self):
        import urllib.parse
        encoded = urllib.parse.quote(self.query)
        # Use Algolia HN search — returns clean JSON, no scraping needed
        url = (
            f"https://hn.algolia.com/api/v1/search?query={encoded}"
            f"&tags=story&hitsPerPage={self.k * 2}"
        )
        yield scrapy.Request(url=url, callback=self.parse_json, errback=self.handle_error)

    def parse_json(self, response):
        try:
            data = response.json()
        except Exception:
            self.logger.warning("[HN] Failed to parse JSON response")
            return

        hits = data.get("hits", [])
        count = 0
        for hit in hits:
            if count >= self.k:
                break
            object_id = hit.get("objectID", "")
            title = hit.get("title") or hit.get("story_title") or ""
            url   = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
            body  = hit.get("story_text") or hit.get("comment_text") or ""
            score = str(hit.get("points") or hit.get("num_comments") or 0)
            if not title:
                continue
            yield {
                "url":      url,
                "title":    title.strip(),
                "body":     body.strip(),
                "score":    score,
                "platform": "HackerNews",
            }
            count += 1

    async def handle_error(self, failure):
        self.logger.warning(f"[HN] Failed: {failure.request.url}")

