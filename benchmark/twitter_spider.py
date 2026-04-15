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

if _AUTH_TOKEN:
    _SESSION_COOKIES.append({
        "name": "auth_token",
        "value": _AUTH_TOKEN,
        "domain": ".x.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    })

if _CT0_TOKEN:
    _SESSION_COOKIES.append({
        "name": "ct0",
        "value": _CT0_TOKEN,
        "domain": ".x.com",
        "path": "/",
        "secure": True,
        "sameSite": "None",
    })


# ── Extraction JS ───────────────────────────────────────
_TWITTER_EXTRACT_JS = """
(limit) => {
    const results = [];
    const seen = new Set();

    const tweets = document.querySelectorAll("article");

    for (const t of tweets) {
        if (results.length >= limit) break;

        const textEl = t.querySelector('[data-testid="tweetText"]');
        const text = textEl ? textEl.innerText : "";

        const link = t.querySelector('a[href*="/status/"]');
        if (!text || !link) continue;

        const url = "https://x.com" + link.getAttribute("href");

        if (seen.has(url)) continue;
        seen.add(url);

        results.push({
            url,
            title: text.split("\\n")[0],
            body: text
        });
    }

    return results;
}
"""


class TwitterSpider(YAWCBaseSpider):
    name = "twitter_home_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "storage_state": {"cookies": _SESSION_COOKIES, "origins": []},
                "extra_http_headers": {
                    "Referer": "https://x.com/",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
        },
    }

    # ── Start directly on HOME ───────────────────────────
    def start_requests(self):
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

        # 🧠 Step 1: handle infinite spinner
        try:
            spinner = page.locator('[role="progressbar"]')
            if await spinner.count() > 0:
                self.logger.info("[Twitter] Spinner detected → reload")
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(6000)
        except Exception:
            pass

        # 🧠 Step 2: wait for tweets to appear
        try:
            await page.wait_for_selector("article", timeout=30000)
        except Exception:
            self.logger.warning("[Twitter] No tweets detected yet...")

        collected = []
        seen = set()

        # 🧠 Step 3: scroll and collect
        for _ in range(20):
            try:
                tweets = await page.evaluate(_TWITTER_EXTRACT_JS, self.k)
            except Exception:
                await page.wait_for_timeout(3000)
                continue

            new_count = 0
            for t in tweets:
                if t["url"] not in seen and len(collected) < self.k:
                    seen.add(t["url"])
                    collected.append(t)
                    new_count += 1

            self.logger.info(f"[Twitter HOME] +{new_count} tweets (total {len(collected)})")

            if len(collected) >= self.k:
                break

            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)

        await page.close()

        for item in collected:
            yield {
                "url": item["url"],
                "title": item["title"],
                "body": item["body"],
                "platform": "Twitter",
            }