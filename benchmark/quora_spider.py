import os
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from dotenv import load_dotenv

load_dotenv()

_QUORA_M_B = os.getenv("QUORA_M_B", "").strip()

_SESSION_COOKIES = []
if _QUORA_M_B:
    _SESSION_COOKIES.append({
        "name": "m-b",
        "value": _QUORA_M_B,
        "domain": ".quora.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    })


_QUORA_EXTRACT_JS = """
(limit) => {
    const results = [];
    const seen = new Set();
    const BASE = "https://www.quora.com";

    const links = document.querySelectorAll("a[href*='/How'], a[href*='/What'], a[href*='/Why']");

    for (const link of links) {
        if (results.length >= limit) break;

        const href = link.getAttribute("href") || "";
        const title = link.innerText.trim();

        if (!title || title.length < 10) continue;
        if (seen.has(href)) continue;

        seen.add(href);

        results.push({
            url: href.startsWith("http") ? href : BASE + href,
            title,
            body: ""
        });
    }

    return results;
}
"""


class QuoraSpider(YAWCBaseSpider):
    name = "quora_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "storage_state": {"cookies": _SESSION_COOKIES, "origins": []},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                "extra_http_headers": {
                    "Referer": "https://www.google.com/",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
        },
    }

    def start_requests(self):
        url = f"https://www.quora.com/search?q={self.query}"

        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 5000),
                ],
            },
            callback=self.parse,
        )

    async def parse(self, response):
        page = response.meta["playwright_page"]

        # ❌ login wall detection
        if "login" in page.url:
            self.logger.error("❌ Quora cookie expired. Re-copy m-b cookie.")
            await page.close()
            return

        # warm interaction
        await page.mouse.move(100, 100)

        collected = []
        seen = set()

        for _ in range(15):
            try:
                data = await page.evaluate(_QUORA_EXTRACT_JS, self.k)
            except:
                await page.wait_for_timeout(2000)
                continue

            for d in data:
                if d["url"] not in seen and len(collected) < self.k:
                    seen.add(d["url"])
                    collected.append(d)

            if len(collected) >= self.k:
                break

            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2000)

        await page.close()

        for item in collected:
            yield {
                "url": item["url"],
                "title": item["title"],
                "body": item["body"],
                "platform": "Quora",
            }