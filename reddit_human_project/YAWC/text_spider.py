"""
YAWC Text Spider v1 — Multi-Platform Text Research Spider
Searches Reddit (primary), StackOverflow (code/tech queries), and Quora (opinion queries).

Platform selection is query-driven:
  - Contains code keywords → StackOverflow
  - Contains opinion/experience keywords → Quora added to mix
  - Default → Reddit only

This is the evolved version of the original reddit_spider.py.
All existing Reddit scraping logic is preserved.

Output fields per item (unified across platforms):
  url        — canonical post URL
  title      — post/question title
  body       — text content (post body, answer snippet, etc.)
  subreddit  — subreddit name (Reddit) or platform name (SO/Quora)
  score      — upvotes / vote count (as string)
  platform   — "Reddit" | "StackOverflow" | "Quora"
"""

import asyncio
import scrapy
from scrapy_playwright.page import PageMethod


CODE_KEYWORDS = {
    "python", "javascript", "typescript", "rust", "go", "golang", "java",
    "c++", "cpp", "c#", "csharp", "swift", "kotlin", "react", "vue",
    "angular", "node", "nodejs", "django", "fastapi", "flask", "rails",
    "docker", "kubernetes", "k8s", "sql", "postgres", "mysql", "mongodb",
    "redis", "aws", "gcp", "azure", "git", "github", "api", "rest",
    "graphql", "css", "html", "bash", "shell", "linux", "error",
    "exception", "bug", "debug", "fix", "code", "function", "class",
    "algorithm", "recursion", "regex", "import", "install", "npm", "pip",
}

OPINION_KEYWORDS = {
    "should i", "is it worth", "experience with", "thoughts on",
    "recommend", "advice", "career", "salary", "interview", "better",
    "vs", "versus", "difference between", "best way to", "how do people",
}


def _is_code_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in CODE_KEYWORDS)


def _is_opinion_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in OPINION_KEYWORDS)


def should_abort_request(req):
    """Block non-essential resources. Allow images only for SO/Quora avatars (not needed)."""
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


class TextSpider(scrapy.Spider):
    name = "text_spider"

    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--blink-settings=imagesEnabled=false",
            ],
        },
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 20_000,
        "CONCURRENT_REQUESTS": 12,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 12,
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, query: str = "", k: str = "8", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query     = query
        self.k         = int(k)
        self.is_code   = _is_code_query(query)
        self.is_opinion = _is_opinion_query(query)

        encoded = query.replace(" ", "+")

        # Always scrape Reddit
        self.reddit_url = (
            f"https://www.reddit.com/search/?q={encoded}&type=link&sort=relevance"
        )

        # StackOverflow for code queries
        self.so_url = (
            f"https://stackoverflow.com/search?q={encoded}&tab=votes"
            if self.is_code else None
        )

        # Quora for opinion queries — not always scraped to avoid rate limits
        self.quora_url = (
            f"https://www.quora.com/search?q={encoded}"
            if self.is_opinion and not self.is_code else None
        )

        self.logger.info(
            f"[YAWC-TEXT] Query='{query}' | code={self.is_code} "
            f"| opinion={self.is_opinion} | so={self.so_url is not None} "
            f"| quora={self.quora_url is not None}"
        )

    # ── Step 1: Start all search requests in parallel ─────────────────────────
    def start_requests(self):
        # Always start with Reddit
        yield scrapy.Request(
            url=self.reddit_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 5000),
                ],
                "source": "reddit",
            },
            callback=self.parse_reddit_search,
            errback=self.handle_error,
        )

        # Add StackOverflow for code queries
        if self.so_url:
            yield scrapy.Request(
                url=self.so_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 4000),
                    ],
                    "source": "stackoverflow",
                },
                callback=self.parse_stackoverflow,
                errback=self.handle_error,
            )

        # Add Quora for opinion queries
        if self.quora_url:
            yield scrapy.Request(
                url=self.quora_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 5000),
                    ],
                    "source": "quora",
                },
                callback=self.parse_quora,
                errback=self.handle_error,
            )

    # ── Reddit: parse search results then fetch posts in parallel ─────────────
    async def parse_reddit_search(self, response):
        page = response.meta.get("playwright_page")

        permalinks = await page.evaluate("""
            () => {
                let posts = Array.from(document.querySelectorAll('shreddit-post'))
                                 .map(p => p.getAttribute('permalink'));
                if (posts.length === 0) {
                    posts = Array.from(document.querySelectorAll('a[href*="/comments/"]'))
                                 .map(a => a.getAttribute('href'));
                }
                return [...new Set(posts)].filter(Boolean);
            }
        """)

        await page.close()

        if not permalinks:
            self.logger.warning("[YAWC-TEXT] No Reddit post links found.")
            return

        # Allocate k slots to Reddit — fewer if SO/Quora also requested
        reddit_k = self.k if not (self.so_url or self.quora_url) else max(4, self.k // 2)

        self.logger.info(
            f"[YAWC-TEXT] Found {len(permalinks)} Reddit posts. "
            f"Fetching top {reddit_k} in parallel."
        )

        for link in permalinks[:reddit_k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 3000),
                    ],
                    "source": "reddit",
                },
                callback=self.parse_reddit_post,
                errback=self.handle_error,
            )

    async def parse_reddit_post(self, response):
        page = response.meta.get("playwright_page")

        title = (
            response.css("h1::text").get()
            or response.css('[slot="title"]::text').get()
            or "Untitled"
        )

        body_parts = (
            response.css("shreddit-post [slot='text-body'] p::text").getall()
            or response.css("div[id$='-post-rtjson-content'] p::text").getall()
            or response.css('[data-testid="post-content"] p::text').getall()
        )

        subreddit = response.css(
            "shreddit-post::attr(subreddit-prefixed-name)"
        ).get() or "r/reddit"

        score = response.css("shreddit-post::attr(score)").get() or "0"

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield {
            "url":      response.url,
            "title":    (title or "").strip(),
            "body":     " ".join(body_parts).strip(),
            "subreddit": subreddit,
            "score":    score,
            "platform": "Reddit",
        }

    # ── StackOverflow: parse search results and top answer snippets ───────────
    async def parse_stackoverflow(self, response):
        page = response.meta.get("playwright_page")

        questions = await page.evaluate(f"""
            () => {{
                const results = [];
                const items = document.querySelectorAll('.js-search-results .s-post-summary');
                for (const item of items) {{
                    if (results.length >= {max(2, self.k // 3)}) break;

                    const titleEl  = item.querySelector('h3 a, .s-link');
                    const title    = titleEl?.textContent?.trim() || '';
                    const href     = titleEl?.getAttribute('href') || '';
                    const url      = href.startsWith('http') ? href : 'https://stackoverflow.com' + href;

                    const excerpt  = item.querySelector('.s-post-summary--content-excerpt');
                    const body     = excerpt?.textContent?.trim() || '';

                    const voteEl   = item.querySelector('.s-post-summary--stats-item__emphasized .s-post-summary--stats-item-number, .vote-count-post');
                    const score    = voteEl?.textContent?.trim() || '0';

                    if (title && url) {{
                        results.push({{ title, url, body, score }});
                    }}
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
                "subreddit": "stackoverflow",
                "score":    q.get("score", "0"),
                "platform": "StackOverflow",
            }

    # ── Quora: parse search results for question snippets ─────────────────────
    async def parse_quora(self, response):
        page = response.meta.get("playwright_page")

        questions = await page.evaluate(f"""
            () => {{
                const results = [];
                // Quora renders question links with data-q-mark
                const links = document.querySelectorAll('a.q_link, [class*="question_link"], a[href*="/What"], a[href*="/How"], a[href*="/Why"], a[href*="/Is"], a[href*="/Are"]');

                const seen = new Set();
                for (const link of links) {{
                    if (results.length >= {max(2, self.k // 4)}) break;

                    const href  = link.getAttribute('href') || '';
                    const url   = href.startsWith('http') ? href : 'https://www.quora.com' + href;
                    const title = link.textContent?.trim() || '';

                    if (!title || title.length < 10 || seen.has(url)) continue;
                    seen.add(url);

                    // Try to grab associated answer snippet
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
                "subreddit": "quora",
                "score":    "0",
                "platform": "Quora",
            }

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC-TEXT] ✗ Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass
