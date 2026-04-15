# ══════════════════════════════════════════════════════════════════════════════
# quora_spider.py  –  YAWC  |  Cookie auth (m-b session cookie)
# ══════════════════════════════════════════════════════════════════════════════
#
# WHY THE OLD CODE GOT 0 ITEMS:
#   Quora does NOT allow unauthenticated search. Unlike Reddit, there is no
#   anonymous fallback – the server does a hard 302 redirect to the login page
#   before any content is rendered.  The debug screenshot confirmed this:
#   the browser was showing the full quora.com/login page.
#
# HOW TO GET YOUR QUORA SESSION COOKIE:
#   1. Log into quora.com in Chrome (or any browser)
#   2. Press F12 → Application tab → Cookies → https://www.quora.com
#   3. Find the cookie named  "m-b"  and copy its Value field
#   4. In your .env file add:   QUORA_M_B=<paste_the_value_here>
#
#   The m-b cookie is a long-lived session token (~1 year expiry).
#   You only need to refresh it if you get 0 items again.
#
# ══════════════════════════════════════════════════════════════════════════════

import os
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from dotenv import load_dotenv

load_dotenv()

_QUORA_M_B = os.getenv("QUORA_M_B", "").strip()

_SESSION_COOKIES: list[dict] = []
if _QUORA_M_B:
    _SESSION_COOKIES.append({
        "name":   "m-b",
        "value":  _QUORA_M_B,
        "domain": ".quora.com",
        "path":   "/",
        "secure": True,
    })


def _quora_abort(req) -> bool:
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


_QUORA_EXTRACT_JS = """
(limit) => {
    const results = [];
    const seen    = new Set();
    const BASE    = 'https://www.quora.com';

    // Primary: question-style URL paths
    const candidates = document.querySelectorAll(
        'a[href*="/What"], a[href*="/How"], a[href*="/Why"], ' +
        'a[href*="/Is-"],  a[href*="/Are-"],a[href*="/Can-"],' +
        'a[href*="/Should"],a[href*="/Which"],a[href*="/When"]'
    );

    for (const link of candidates) {
        if (results.length >= limit) break;
        const rawHref = link.getAttribute('href') || '';
        if (rawHref.includes('#') || rawHref.startsWith('/profile/') ||
            rawHref.startsWith('/topic/')) continue;

        const url   = rawHref.startsWith('http') ? rawHref : BASE + rawHref;
        const title = link.textContent?.trim() || '';
        if (!title || title.length < 10 || seen.has(url)) continue;
        seen.add(url);

        const card    = link.closest('[class*="question_card"]') || link.parentElement;
        const snippet = card?.querySelector('[class*="answer"], [class*="excerpt"]');
        const body    = snippet?.textContent?.trim() || '';

        results.push({ url, title, body });
    }

    // Fallback: any link whose visible text looks like a question
    if (results.length === 0) {
        for (const link of document.querySelectorAll('a[href]')) {
            if (results.length >= limit) break;
            const text = link.textContent?.trim() || '';
            const href = link.getAttribute('href') || '';
            if (
                text.length > 20 &&
                /^(What|How|Why|Is |Are |Can |Should |Which |When )/i.test(text) &&
                !href.startsWith('/profile/') && !href.startsWith('/topic/') &&
                !seen.has(href)
            ) {
                seen.add(href);
                results.push({
                    url:   href.startsWith('http') ? href : BASE + href,
                    title: text,
                    body:  '',
                });
            }
        }
    }

    return results;
}
"""


class QuoraSpider(YAWCBaseSpider):
    """
    Scrapes Quora search results using the m-b session cookie.

    Usage:
        scrapy crawl quora_spider -a query="how to learn python" -a k=30
        scrapy crawl quora_spider -a query="career advice" -a k=50 -a headless=false
    """

    name = "quora_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_ABORT_REQUEST": _quora_abort,
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

        if not _QUORA_M_B:
            self.logger.error(
                "❌  QUORA_M_B not set in .env.\n"
                "    See comments at top of quora_spider.py for cookie extraction instructions."
            )
            return

        encoded = urllib.parse.quote(self.query)
        url = f"https://www.quora.com/search?q={encoded}&type=question"
        self.logger.info(f"[Quora] Cookie-auth search → {url}")

        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 6000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def _dismiss_modal(self, page) -> None:
        """Silently close any residual login prompt even after auth."""
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        for sel in [
            "button[aria-label='Close']",
            "button[aria-label='close']",
            "[class*='modal'] button",
            "[class*='Modal'] button",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=800):
                    await btn.click(timeout=800)
                    await page.wait_for_timeout(300)
                    break
            except Exception:
                pass

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        # Verify we actually landed on the search page, not the login page
        current_url = page.url
        if "/search" not in current_url:
            self.logger.error(
                f"[Quora] Landed on {current_url} instead of search page.\n"
                "        Your QUORA_M_B cookie may be expired – re-extract it from Chrome."
            )
            await page.close()
            return

        await self._dismiss_modal(page)
        await page.wait_for_timeout(1000)

        # Wait for question links to appear
        try:
            await page.wait_for_selector("a[href*='/How'], a[href*='/What']", timeout=15_000)
        except Exception:
            self.logger.warning("[Quora] Question links slow to appear – continuing anyway.")

        collected: list[dict] = []
        seen_urls: set[str]   = set()
        scroll_round = 0
        max_scrolls  = max(15, self.k // 2)
        stall_count  = 0

        while len(collected) < self.k and scroll_round < max_scrolls:
            await self._dismiss_modal(page)

            questions = await page.evaluate(_QUORA_EXTRACT_JS, self.k)

            new_count = 0
            for q in questions:
                if q["url"] not in seen_urls and len(collected) < self.k:
                    seen_urls.add(q["url"])
                    collected.append(q)
                    new_count += 1

            scroll_round += 1
            self.logger.info(
                f"[Quora] Scroll {scroll_round}: +{new_count} new "
                f"(total {len(collected)}/{self.k})"
            )

            if len(collected) >= self.k:
                break

            if new_count == 0:
                stall_count += 1
                if stall_count >= 4:
                    self.logger.warning("[Quora] Feed appears exhausted.")
                    break
            else:
                stall_count = 0

            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2500)

        await self._stop_trace(page, "quora")
        await page.close()

        self.logger.info(f"[Quora] Yielding {len(collected)} questions.")
        for item in collected:
            yield {
                "url":      item["url"],
                "title":    item["title"].strip(),
                "body":     item["body"].strip(),
                "score":    "0",
                "platform": "Quora",
            }
