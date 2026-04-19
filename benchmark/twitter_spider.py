# ══════════════════════════════════════════════════════════════════════════════
# twitter_spider.py  –  FINAL STABLE VERSION (HOME + FOLLOWING TAB)
# ══════════════════════════════════════════════════════════════════════════════

import os
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from dotenv import load_dotenv

load_dotenv()

_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
_CT0_TOKEN  = os.getenv("TWITTER_CT0_TOKEN", "").strip()

# ── Cookies ─────────────────────────────────────────────
_SESSION_COOKIES = []

for domain in [".x.com", ".twitter.com"]:
    if _AUTH_TOKEN:
        _SESSION_COOKIES.append({
            "name": "auth_token",
            "value": _AUTH_TOKEN,
            "domain": domain,
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "None",
        })

    if _CT0_TOKEN:
        _SESSION_COOKIES.append({
            "name": "ct0",
            "value": _CT0_TOKEN,
            "domain": domain,
            "path": "/",
            "secure": True,
            "sameSite": "None",
        })


# ── JS Extractor ───────────────────────────────────────
_TWITTER_EXTRACT_JS = """
(limit) => {
    const results = [];
    const seen = new Set();

    const tweets = document.querySelectorAll("article");

    for (const t of tweets) {
        if (results.length >= limit) break;

        const textEl = t.querySelector('[data-testid="tweetText"]');
        const text = textEl ? textEl.innerText.trim() : "";

        const timeEl = t.querySelector("time");
        const linkEl = timeEl ? timeEl.closest("a") : null;

        if (!text || !linkEl) continue;

        const url = "https://x.com" + linkEl.getAttribute("href");

        if (seen.has(url)) continue;
        seen.add(url);

        const user = t.querySelector('[data-testid="User-Name"]');
        const title = user ? user.innerText.split("\\n")[0] : "Unknown";

        results.push({
            url,
            title,
            body: text
        });
    }

    return results;
}
"""


def _abort(req):
    return req.resource_type in {"image", "media", "font", "stylesheet"}


class TwitterSpider(YAWCBaseSpider):
    name = "twitter_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_ABORT_REQUEST": _abort,
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "storage_state": {"cookies": _SESSION_COOKIES, "origins": []},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            }
        },
    }

    def start_requests(self):
        if not _AUTH_TOKEN:
            self.logger.error("❌ Missing TWITTER_AUTH_TOKEN")
            return

        yield scrapy.Request(
            url="https://x.com/home",
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 6000),
                ],
            },
            callback=self.parse,
        )

    async def parse(self, response):
        page = response.meta["playwright_page"]

        # 🔥 FIX 1: Spinner killer
        for _ in range(3):
            spinner = page.locator('[role="progressbar"]')
            if await spinner.count() > 0:
                await page.reload()
                await page.wait_for_timeout(5000)
            else:
                break

        # 🔥 FIX 2: Click FOLLOWING tab (CRITICAL)
        try:
            following = page.locator("text=Following")
            if await following.count() > 0:
                await following.first.click()
                await page.wait_for_timeout(5000)
        except:
            self.logger.warning("Could not click Following tab")

        # 🔥 FIX 3: Human behavior
        await page.mouse.move(200, 200)
        await page.mouse.wheel(0, 1000)
        await page.wait_for_timeout(2000)

        # Wait for tweets
        try:
            await page.wait_for_selector("article", timeout=20000)
        except:
            self.logger.warning("Tweets not loaded")

        collected = []
        seen = set()

        scroll_round = 0
        max_scrolls = 20
        stall = 0

        while len(collected) < self.k and scroll_round < max_scrolls:

            tweets = await page.evaluate(_TWITTER_EXTRACT_JS, self.k)

            new_count = 0
            for t in tweets:
                if t["url"] not in seen:
                    seen.add(t["url"])
                    collected.append(t)
                    new_count += 1

            if new_count == 0:
                stall += 1
            else:
                stall = 0

            if stall >= 3:
                break

            scroll_round += 1

            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(3000)

        await page.close()

        for item in collected:
            yield {
                "url": item["url"],
                "title": item["title"],
                "body": item["body"],
                "platform": "Twitter",
            }