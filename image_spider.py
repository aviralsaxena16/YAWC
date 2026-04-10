
# ══════════════════════════════════════════════════════════════════════════════
# image_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider


def _image_abort(req) -> bool:
    # Images MUST be allowed — we need src URLs
    return req.resource_type in {
        "media", "font", "websocket", "eventsource", "manifest",
    } or any(d in req.url for d in {
        "doubleclick.net", "googlesyndication.com",
        "google-analytics.com", "sentry.io",
    })


class ImageSpider(YAWCBaseSpider):
    """
    Scrapes Unsplash (primary) then Pexels (fallback) for images.
    Both have large, easily scrapeable repositories with good alt text.
    Avoids Pinterest which aggressively blocks headless browsers.
    Output: url, image_url, alt, source, title, likes, platform="Image"
    """
    name = "image_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=1),
        "PLAYWRIGHT_ABORT_REQUEST": _image_abort,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 25_000,
        # Allow images to load so we can read their src attributes
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": [
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu", "--disable-extensions",
            ],
        },
    }

    def start_requests(self):
        encoded = self.query.replace(" ", "%20")
        yield scrapy.Request(
            url=f"https://unsplash.com/s/photos/{encoded}",
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "figure", timeout=12000),
                ],
                "source": "unsplash",
            },
            callback=self.parse_unsplash,
            errback=self.fallback_pexels,
        )

    async def parse_unsplash(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        images = await page.evaluate(f"""
            () => {{
                const results = [];
                for (const fig of document.querySelectorAll('figure')) {{
                    if (results.length >= {self.k}) break;
                    const img = fig.querySelector('img');
                    if (!img) continue;
                    let imageUrl = '';
                    if (img.srcset) {{
                        const parts = img.srcset.split(',').map(s => s.trim().split(' '));
                        const best  = parts.sort((a, b) =>
                            (parseInt(b[1]) || 0) - (parseInt(a[1]) || 0))[0];
                        imageUrl = best?.[0] || img.src;
                    }} else {{
                        imageUrl = img.src;
                    }}
                    if (imageUrl.includes('images.unsplash.com')) {{
                        imageUrl = imageUrl.split('?')[0] + '?w=1200&q=80&auto=format&fit=crop';
                    }}
                    const link   = fig.querySelector('a[href*="/photos/"]');
                    const pageUrl = link ? 'https://unsplash.com' + link.getAttribute('href') : '';
                    const alt    = img.alt || img.title || '';
                    if (imageUrl && !imageUrl.startsWith('data:'))
                        results.push({{ imageUrl, alt, pageUrl }});
                }}
                return results;
            }}
        """)
        await page.close()

        if not images:
            self.logger.warning("[Image] Unsplash returned nothing — trying Pexels")
            encoded = self.query.replace(" ", "+")
            yield scrapy.Request(
                url=f"https://www.pexels.com/search/{encoded}/",
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [PageMethod("wait_for_timeout", 5000)],
                    "source": "pexels",
                },
                callback=self.parse_pexels,
                errback=self.handle_error,
            )
            return

        for item in images:
            yield {
                "url":       item.get("pageUrl") or response.url,
                "image_url": item.get("imageUrl", ""),
                "alt":       item.get("alt", "").strip(),
                "title":     item.get("alt", "").strip(),
                "source":    "Unsplash",
                "likes":     0,
                "platform":  "Image",
            }

    async def parse_pexels(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        await page.evaluate("window.scrollBy(0, 1400)")
        await page.wait_for_timeout(2000)

        images = await page.evaluate(f"""
            () => {{
                const results = [];
                const imgs = document.querySelectorAll(
                    'article img, [class*="photo"] img, [class*="PhotoItem"] img'
                );
                for (const img of imgs) {{
                    if (results.length >= {self.k}) break;
                    let src = img.src || '';
                    const alt = img.alt || '';
                    // Pexels srcset — pick largest
                    if (img.srcset) {{
                        const parts = img.srcset.split(',').map(s => s.trim().split(' '));
                        const best = parts.sort((a,b) =>
                            (parseInt(b[1]) || 0) - (parseInt(a[1]) || 0))[0];
                        src = best?.[0] || src;
                    }}
                    // Skip avatars / tiny images
                    if (!src || img.width < 100 || src.includes('avatar')) continue;
                    const link   = img.closest('a');
                    const pageUrl = link ? (
                        link.href.startsWith('http') ? link.href
                        : 'https://www.pexels.com' + link.getAttribute('href')
                    ) : '';
                    results.push({{ imageUrl: src, alt, pageUrl }});
                }}
                return results;
            }}
        """)
        await page.close()

        for item in images:
            yield {
                "url":       item.get("pageUrl") or response.url,
                "image_url": item.get("imageUrl", ""),
                "alt":       item.get("alt", "").strip() or self.query,
                "title":     item.get("alt", "").strip() or self.query,
                "source":    "Pexels",
                "likes":     0,
                "platform":  "Image",
            }

    async def fallback_pexels(self, failure):
        self.logger.warning(f"[Image] Unsplash request failed — falling back to Pexels")
        encoded = self.query.replace(" ", "+")
        yield scrapy.Request(
            url=f"https://www.pexels.com/search/{encoded}/",
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 5000)],
            },
            callback=self.parse_pexels,
            errback=self.handle_error,
        )
