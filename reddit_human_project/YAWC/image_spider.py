"""
YAWC Image Spider v1
Searches for images using Unsplash (primary) with a Pinterest CSS fallback.

Why Unsplash as primary:
  - No login wall for search results
  - Stable CSS selectors (no heavy shadow DOM)
  - Direct high-quality image CDN URLs
  - Permissively licensed content

Why Pinterest as fallback:
  - Broader creative/inspiration coverage
  - Requires more aggressive JS waiting

Output fields per item:
  url        — page URL (Unsplash photo page or Pinterest pin)
  image_url  — direct image URL (usable in <img src> and markdown)
  alt        — descriptive alt text
  source     — "Unsplash" | "Pinterest"
  width      — image width (if available)
  height     — image height (if available)
  likes      — like/save count (or 0)
  title      — photo title / pin title
"""

import scrapy
from scrapy_playwright.page import PageMethod


def should_abort_request(req):
    """Block heavyweight non-content resources."""
    blocked_types = {
        "media", "font",
        "websocket", "eventsource", "manifest",
    }
    # Allow images — we need them to extract image src URLs
    blocked_domains = {
        "doubleclick.net", "googlesyndication.com",
        "google-analytics.com", "googletagmanager.com",
        "sentry.io", "datadog-browser-agent.com",
    }
    if req.resource_type in blocked_types:
        return True
    if any(d in req.url for d in blocked_domains):
        return True
    return False


class ImageSpider(scrapy.Spider):
    name = "image_spider"

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
            ],
        },
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 25_000,
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, query: str = "", k: str = "5", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query   = query
        self.k       = int(k)
        self.results = []

        # Primary: Unsplash search
        encoded = query.replace(" ", "%20")
        self.unsplash_url  = f"https://unsplash.com/s/photos/{encoded}"
        self.pinterest_url = f"https://www.pinterest.com/search/pins/?q={encoded}"

    # ── Step 1: Try Unsplash first ────────────────────────────────────────────
    def start_requests(self):
        yield scrapy.Request(
            url=self.unsplash_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Wait for the image grid to hydrate
                    PageMethod("wait_for_selector", "figure", timeout=12000),
                ],
                "source": "unsplash",
            },
            callback=self.parse_unsplash,
            errback=self.fallback_pinterest,
        )

    # ── Unsplash parser ────────────────────────────────────────────────────────
    async def parse_unsplash(self, response):
        page   = response.meta.get("playwright_page")
        source = response.meta.get("source", "unsplash")

        images = await page.evaluate(f"""
            () => {{
                const results = [];
                // Unsplash uses <figure> elements with a nested <img>
                const figures = document.querySelectorAll('figure');
                for (const fig of figures) {{
                    if (results.length >= {self.k}) break;

                    const img  = fig.querySelector('img');
                    if (!img) continue;

                    // Prefer srcset largest, fall back to src
                    let imageUrl = '';
                    if (img.srcset) {{
                        const parts = img.srcset.split(',').map(s => s.trim().split(' '));
                        // Pick the highest resolution (last or widest)
                        const biggest = parts.sort((a, b) => {{
                            const wa = parseInt(a[1]) || 0;
                            const wb = parseInt(b[1]) || 0;
                            return wb - wa;
                        }})[0];
                        imageUrl = biggest?.[0] || img.src;
                    }} else {{
                        imageUrl = img.src;
                    }}

                    // Clean Unsplash URLs: remove cropping params, force quality
                    if (imageUrl.includes('images.unsplash.com')) {{
                        const base = imageUrl.split('?')[0];
                        imageUrl = base + '?w=1200&q=80&auto=format&fit=crop';
                    }}

                    const alt   = img.alt || img.title || '';
                    const link  = fig.querySelector('a[href*="/photos/"]');
                    const pageUrl = link ? 'https://unsplash.com' + link.getAttribute('href') : '';

                    if (imageUrl && !imageUrl.startsWith('data:')) {{
                        results.push({{ imageUrl, alt, pageUrl }});
                    }}
                }}
                return results;
            }}
        """)

        await page.close()

        if not images:
            self.logger.warning("[YAWC-IMG] Unsplash returned no images — trying Pinterest")
            yield scrapy.Request(
                url=self.pinterest_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 6000),
                    ],
                    "source": "pinterest",
                },
                callback=self.parse_pinterest,
                errback=self.handle_error,
            )
            return

        for item in images:
            yield {
                "url":       item.get("pageUrl") or self.unsplash_url,
                "image_url": item.get("imageUrl", ""),
                "alt":       item.get("alt", "").strip(),
                "source":    "Unsplash",
                "title":     item.get("alt", "").strip(),
                "likes":     0,
            }

    # ── Pinterest fallback parser ─────────────────────────────────────────────
    async def parse_pinterest(self, response):
        page = response.meta.get("playwright_page")

        # Scroll once to trigger more pins to load
        await page.evaluate("window.scrollBy(0, 1200)")
        await page.wait_for_timeout(2000)

        images = await page.evaluate(f"""
            () => {{
                const results = [];
                // Pinterest pin images live in [data-test-id="pin"] or div[role="listitem"]
                const pins = document.querySelectorAll('[data-test-id="pin-visual-wrapper"] img, div[role="listitem"] img');

                for (const img of pins) {{
                    if (results.length >= {self.k}) break;

                    let imageUrl = img.src || '';
                    const alt    = img.alt || '';

                    // Pinterest serves /236x/, /474x/, /736x/ — upgrade to /736x/
                    imageUrl = imageUrl.replace(/\\/\\d+x\\//g, '/736x/');

                    // Skip tiny icons / avatars
                    if (!imageUrl || imageUrl.includes('profile') || imageUrl.includes('avatar')) continue;
                    if (img.width < 100 || img.height < 100) continue;

                    const pinLink = img.closest('a');
                    const pageUrl = pinLink
                        ? 'https://www.pinterest.com' + (pinLink.getAttribute('href') || '')
                        : '';

                    results.push({{ imageUrl, alt, pageUrl }});
                }}
                return results;
            }}
        """)

        await page.close()

        for item in images:
            yield {
                "url":       item.get("pageUrl") or self.pinterest_url,
                "image_url": item.get("imageUrl", ""),
                "alt":       item.get("alt", "").strip() or self.query,
                "source":    "Pinterest",
                "title":     item.get("alt", "").strip() or self.query,
                "likes":     0,
            }

    async def fallback_pinterest(self, failure):
        """Called when Unsplash request itself errors (timeout, blocked)."""
        self.logger.warning(f"[YAWC-IMG] Unsplash failed: {failure}. Falling back to Pinterest.")
        yield scrapy.Request(
            url=self.pinterest_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 6000),
                ],
            },
            callback=self.parse_pinterest,
            errback=self.handle_error,
        )

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC-IMG] ✗ All sources failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass
