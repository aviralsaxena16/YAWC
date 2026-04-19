# ══════════════════════════════════════════════════════════════════════════════
# reddit_spider.py  –  YAWC  |  Unauthenticated  |  Fixed selectors
# ══════════════════════════════════════════════════════════════════════════════
#
# WHY THE OLD CODE GOT 0 ITEMS:
#   shreddit-post is only rendered when Reddit detects a logged-in session.
#   Anonymous visitors get plain HTML: <article> or [data-testid="post-container"].
#   The fix: detect which selector is active and use that one.
#
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider


def _reddit_abort(req) -> bool:
    return req.resource_type in {"image", "media", "font", "stylesheet", "manifest"}


# JS that detects which post selector is live and extracts structured data.
_REDDIT_EXTRACT_JS = """
() => {
    const results = [];

    // ── Path A: logged-in web-component layout ────────────────────────────
    const wcPosts = document.querySelectorAll('shreddit-post');
    if (wcPosts.length > 0) {
        for (const el of wcPosts) {
            const permalink = el.getAttribute('permalink') || '';
            const url = permalink.startsWith('http')
                ? permalink
                : 'https://www.reddit.com' + permalink;
            results.push({
                url,
                title:         el.getAttribute('post-title') || '',
                score:         el.getAttribute('score')      || '0',
                author:        el.getAttribute('author')     || '',
                subreddit:     el.getAttribute('subreddit-prefixed-name') || '',
                comment_count: el.getAttribute('comment-count') || '0',
                body: el.querySelector('[slot="text-body"]')?.innerText?.trim() || '',
            });
        }
        return results;
    }

    // ── Path B: anonymous new-Reddit layout ───────────────────────────────
    // Posts are wrapped in <article> or a div with data-testid="post-container"
    const containers = document.querySelectorAll(
        '[data-testid="post-container"], article'
    );
    for (const c of containers) {
        // Title link
        const titleLink = c.querySelector(
            'a[data-click-id="body"], h3 a, h1 a, [data-testid="post-title"] a, ' +
            'a[href*="/comments/"]'
        );
        const title = titleLink?.textContent?.trim() || c.querySelector('h3, h1')?.textContent?.trim() || '';
        const href  = titleLink?.getAttribute('href') || '';
        const url   = href.startsWith('http') ? href : 'https://www.reddit.com' + href;

        if (!title || !href) continue;

        // Score
        const scoreEl = c.querySelector(
            '[id*="vote-arrows"] .score, [data-click-id="upvote"] + span, ' +
            'button[aria-label*="upvote"] ~ span, [data-testid="vote-count"]'
        );
        const score = scoreEl?.textContent?.trim() || '0';

        // Subreddit
        const subEl = c.querySelector('a[href*="/r/"]');
        const subreddit = subEl?.textContent?.trim() || '';

        results.push({ url, title, score, author: '', subreddit, comment_count: '0', body: '' });
    }

    // ── Path C: fallback – grab any /comments/ links with visible text ─────
    if (results.length === 0) {
        const seen = new Set();
        for (const a of document.querySelectorAll('a[href*="/comments/"]')) {
            const href  = a.getAttribute('href') || '';
            const title = a.textContent?.trim() || '';
            if (!title || title.length < 10 || seen.has(href)) continue;
            seen.add(href);
            results.push({
                url: href.startsWith('http') ? href : 'https://www.reddit.com' + href,
                title, score: '0', author: '', subreddit: '', comment_count: '0', body: '',
            });
        }
    }

    return results;
}
"""


class RedditSpider(YAWCBaseSpider):
    """
    Scrapes Reddit home page anonymously (no login required).

    Usage:
        scrapy crawl reddit_spider -a k=50
        scrapy crawl reddit_spider -a headless=false
    """

    name = "reddit_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=3),
        "PLAYWRIGHT_ABORT_REQUEST": _reddit_abort,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 45_000,
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "viewport": {"width": 1280, "height": 900},
                "locale": "en-US",
                "timezone_id": "America/New_York",
            }
        },
    }

    def start_requests(self):
        url = "https://www.reddit.com/"
        self.logger.info(f"[Reddit] Home page crawl → {url}")

        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Wait for ANY of the known post selectors
                    PageMethod("wait_for_timeout", 4000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        # Try to wait for whichever post selector is present
        for sel in [
            "[data-testid='post-container']",
            "article",
            "shreddit-post",
            "a[href*='/comments/']",
        ]:
            try:
                await page.wait_for_selector(sel, timeout=6_000, state="attached")
                self.logger.info(f"[Reddit] Active selector: {sel}")
                break
            except Exception:
                continue

        collected: list[dict] = []
        seen_urls: set[str] = set()
        scroll_round = 0
        max_scrolls  = 40

        while len(collected) < self.k and scroll_round < max_scrolls:
            posts = await page.evaluate(_REDDIT_EXTRACT_JS)

            new_count = 0
            for p in posts:
                if p["url"] and p["url"] not in seen_urls and len(collected) < self.k:
                    seen_urls.add(p["url"])
                    collected.append(p)
                    new_count += 1

            scroll_round += 1
            self.logger.info(
                f"[Reddit] Scroll {scroll_round}: +{new_count} new (total {len(collected)}/{self.k})"
            )

            if len(collected) >= self.k:
                break

            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

        await self._stop_trace(page, "reddit")
        await page.close()

        self.logger.info(f"[Reddit] Yielding {len(collected)} posts.")
        for item in collected:
            yield {
                "url":           item["url"],
                "title":         item["title"].strip(),
                "body":          item["body"],
                "score":         item["score"],
                "author":        item["author"],
                "subreddit":     item["subreddit"],
                "comment_count": item["comment_count"],
                "platform":      "Reddit",
            }
