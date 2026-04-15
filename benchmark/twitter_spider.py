# ══════════════════════════════════════════════════════════════════════════════
# twitter_spider.py  –  YAWC  |  Cookie auth (silent, no login screen)
# ══════════════════════════════════════════════════════════════════════════════
#
# WHY THE OLD CODE GOT 0 ITEMS:
#   Twitter's search page shows a loading spinner for 5-15 seconds before
#   tweets hydrate. wait_for_selector with 15s timeout was often too short,
#   especially in headless mode where rendering is slower.
#   Fix: increased to 30s + added a scroll-based retry loop.
#
# HOW TO GET YOUR COOKIES (do this in Chrome, logged in):
#   F12 → Application → Cookies → .twitter.com (or .x.com)
#   Copy "auth_token" → TWITTER_AUTH_TOKEN in .env
#   Copy "ct0"        → TWITTER_CT0_TOKEN  in .env  (optional but recommended)
#
# ══════════════════════════════════════════════════════════════════════════════

import os
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from dotenv import load_dotenv

load_dotenv()

_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
_CT0_TOKEN  = os.getenv("TWITTER_CT0_TOKEN",  "").strip()

_SESSION_COOKIES: list[dict] = []
if _AUTH_TOKEN:
    for domain in [".twitter.com", ".x.com"]:
        _SESSION_COOKIES.append({
            "name": "auth_token", "value": _AUTH_TOKEN,
            "domain": domain, "path": "/", "secure": True, "httpOnly": True,
        })
if _CT0_TOKEN:
    for domain in [".twitter.com", ".x.com"]:
        _SESSION_COOKIES.append({
            "name": "ct0", "value": _CT0_TOKEN,
            "domain": domain, "path": "/", "secure": True,
        })


def _twitter_abort(req) -> bool:
    return req.resource_type in {"image", "media", "font", "stylesheet", "manifest"}


_TWITTER_EXTRACT_JS = """
(limit) => {
    const results = [];
    const seen    = new Set();

    for (const article of document.querySelectorAll('[data-testid="tweet"]')) {
        if (results.length >= limit) break;

        const textEl = article.querySelector('[data-testid="tweetText"]');
        const body   = textEl ? textEl.innerText.trim() : '';

        const timeEl = article.querySelector('time');
        const linkEl = timeEl ? timeEl.closest('a') : null;
        const href   = linkEl ? linkEl.getAttribute('href') : '';
        const url    = href   ? 'https://x.com' + href      : '';

        if (!body || !url || seen.has(url)) continue;
        seen.add(url);

        const userEl  = article.querySelector('[data-testid="User-Name"]');
        const title   = userEl ? userEl.innerText.split('\\n')[0].trim() : 'Unknown';

        const parseCount = testid => {
            const el  = article.querySelector(`[data-testid="${testid}"]`);
            if (!el) return '0';
            const lbl = el.getAttribute('aria-label') || '';
            const m   = lbl.match(/([\\d,]+)/);
            return m ? m[1].replace(/,/g,'') : '0';
        };

        results.push({
            url, title, body,
            score:    parseCount('like'),
            retweets: parseCount('retweet'),
            replies:  parseCount('reply'),
        });
    }
    return results;
}
"""


class TwitterSpider(YAWCBaseSpider):
    """
    Scrapes Twitter/X search – session cookie injected silently, no login UI.

    Usage:
        scrapy crawl twitter_spider -a query="Artificial Intelligence" -a k=50
        scrapy crawl twitter_spider -a query="LLMs" -a k=80 -a headless=false
    """

    name = "twitter_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_ABORT_REQUEST": _twitter_abort,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 45_000,
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "storage_state": {
                    "cookies": _SESSION_COOKIES,
                    "origins": [],
                },
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "viewport":    {"width": 1280, "height": 900},
                "locale":      "en-US",
                "timezone_id": "America/New_York",
            }
        },
    }

    def start_requests(self):
        import urllib.parse
        if not _AUTH_TOKEN:
            self.logger.error(
                "❌  TWITTER_AUTH_TOKEN not set in .env.\n"
                "    See comments at top of twitter_spider.py for instructions."
            )
            return

        encoded = urllib.parse.quote(self.query)
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        self.logger.info(f"[Twitter] Cookie-auth search → {url}")

        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Give the page a long initial wait – Twitter's React bundle
                    # can take 10-20 s to render in headless mode.
                    PageMethod("wait_for_timeout", 6000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        # Wait up to 30 s for the first tweet to appear
        try:
            await page.wait_for_selector(
                "[data-testid='tweet']", timeout=30_000, state="attached"
            )
        except Exception:
            self.logger.warning("[Twitter] Timed out waiting for tweets – will try to extract anyway.")

        collected: list[dict] = []
        seen_urls: set[str]   = set()
        scroll_round = 0
        max_scrolls  = max(20, self.k // 3)
        stall_count  = 0

        while len(collected) < self.k and scroll_round < max_scrolls:
            tweets = await page.evaluate(_TWITTER_EXTRACT_JS, self.k)

            new_count = 0
            for t in tweets:
                if t["url"] not in seen_urls and len(collected) < self.k:
                    seen_urls.add(t["url"])
                    collected.append(t)
                    new_count += 1

            scroll_round += 1
            self.logger.info(
                f"[Twitter] Scroll {scroll_round}: +{new_count} new "
                f"(total {len(collected)}/{self.k})"
            )

            if len(collected) >= self.k:
                break

            if new_count == 0:
                stall_count += 1
                if stall_count >= 4:
                    self.logger.warning("[Twitter] Feed appears exhausted.")
                    break
            else:
                stall_count = 0

            await page.mouse.wheel(0, 2500)
            await page.wait_for_timeout(2500)

        await self._stop_trace(page, "twitter")
        await page.close()

        self.logger.info(f"[Twitter] Yielding {len(collected)} tweets.")
        for item in collected:
            yield {
                "url":      item["url"],
                "title":    item["title"],
                "body":     item["body"],
                "score":    item["score"],
                "retweets": item["retweets"],
                "replies":  item["replies"],
                "platform": "Twitter",
            }
