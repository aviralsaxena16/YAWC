"""
YAWC YouTube Spider v1
Searches YouTube for the top k videos matching a query.
Extracts: title, channel, views, description, watch URL, embed URL, thumbnail.

Uses Playwright to handle YouTube's JS-rendered content.
Blocks all non-essential resources for maximum speed.

Output fields per item:
  url         — full YouTube watch URL
  embed_url   — https://www.youtube.com/embed/<video_id>
  title       — video title
  channel     — channel/author name
  views       — view count string (e.g. "1.2M views")
  description — short description snippet
  thumbnail   — thumbnail image URL
"""

import re
import scrapy
from scrapy_playwright.page import PageMethod


def should_abort_request(req):
    """Block everything non-HTML. Video streams, fonts, images — gone."""
    blocked_types = {
        "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }
    blocked_domains = {
        "doubleclick.net", "googlesyndication.com",
        "google-analytics.com", "googletagmanager.com",
    }
    if req.resource_type in blocked_types:
        return True
    if any(d in req.url for d in blocked_domains):
        return True
    return False


def extract_video_id(url: str) -> str | None:
    """Extract 11-char YouTube video ID from a URL."""
    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"/embed/([a-zA-Z0-9_-]{11})",
        r"/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


class YouTubeSpider(scrapy.Spider):
    name = "youtube_spider"

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
                # Suppress autoplay to avoid media resource loads
                "--autoplay-policy=no-user-gesture-required",
            ],
        },
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 25_000,
        "CONCURRENT_REQUESTS": 1,   # YouTube search is single-page; no benefit from parallel here
        "DOWNLOAD_DELAY": 0,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, query: str = "", k: str = "3", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.k     = int(k)
        # YouTube search URL — filters to videos only
        encoded = query.replace(" ", "+")
        self.search_url = (
            f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAQ%3D%3D"
        )

    # ── Step 1: Load YouTube search results page ──────────────────────────────
    def start_requests(self):
        yield scrapy.Request(
            url=self.search_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Dismiss cookie consent if it appears
                    PageMethod("wait_for_timeout", 3000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    # ── Step 2: Extract video data directly from search results ──────────────
    async def parse_search(self, response):
        page = response.meta.get("playwright_page")

        # YouTube hydrates initial data into window.ytInitialData as JSON.
        # We extract video renderers from it — much more reliable than CSS selectors.
        video_data = await page.evaluate("""
            () => {
                try {
                    const data = window.ytInitialData;
                    // Navigate the JSON to find videoRenderer objects
                    const contents = data
                        ?.contents
                        ?.twoColumnSearchResultsRenderer
                        ?.primaryContents
                        ?.sectionListRenderer
                        ?.contents;

                    if (!contents) return [];

                    const videos = [];
                    for (const section of contents) {
                        const items = section
                            ?.itemSectionRenderer
                            ?.contents || [];
                        for (const item of items) {
                            const v = item?.videoRenderer;
                            if (!v) continue;

                            const videoId   = v.videoId || '';
                            const title     = v.title?.runs?.[0]?.text || '';
                            const channel   = v.ownerText?.runs?.[0]?.text || '';
                            const viewCount = v.viewCountText?.simpleText
                                          || v.viewCountText?.runs?.[0]?.text
                                          || '';
                            const desc      = v.detailedMetadataSnippets
                                              ?.[0]
                                              ?.snippetText
                                              ?.runs
                                              ?.map(r => r.text)
                                              ?.join('') || '';
                            const thumbnail = v.thumbnail?.thumbnails?.slice(-1)[0]?.url || '';

                            if (videoId && title) {
                                videos.push({
                                    videoId, title, channel, viewCount, desc, thumbnail
                                });
                            }
                        }
                    }
                    return videos;
                } catch (e) {
                    return [];
                }
            }
        """)

        await page.close()

        if not video_data:
            # Fallback: try CSS-selector extraction
            self.logger.warning("[YAWC-YT] ytInitialData extraction failed — trying CSS fallback")
            video_data = await self._css_fallback(response)

        count = 0
        for v in video_data:
            if count >= self.k:
                break
            vid = v.get("videoId", "")
            if not vid:
                continue

            yield {
                "url":         f"https://www.youtube.com/watch?v={vid}",
                "embed_url":   f"https://www.youtube.com/embed/{vid}",
                "title":       v.get("title", "").strip(),
                "channel":     v.get("channel", "").strip(),
                "views":       v.get("viewCount", "").strip(),
                "description": v.get("desc", "").strip(),
                "thumbnail":   v.get("thumbnail", "").strip(),
                "platform":    "YouTube",
            }
            count += 1

        if count == 0:
            self.logger.warning(
                f"[YAWC-YT] ⚠ No videos found for '{self.query}'. "
                "YouTube may be blocking the headless browser."
            )

    async def _css_fallback(self, response) -> list[dict]:
        """
        CSS selector fallback in case ytInitialData is unavailable.
        Less reliable but better than nothing.
        """
        results = []
        for anchor in response.css("a#video-title"):
            href  = anchor.attrib.get("href", "")
            title = anchor.attrib.get("title", "") or anchor.css("::text").get("").strip()
            vid   = extract_video_id(href)
            if vid and title:
                results.append({
                    "videoId":   vid,
                    "title":     title,
                    "channel":   "",
                    "viewCount": "",
                    "desc":      "",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                })
        return results

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC-YT] ✗ Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass
