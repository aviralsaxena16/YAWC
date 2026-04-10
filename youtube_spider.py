# ══════════════════════════════════════════════════════════════════════════════
# youtube_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import re as _re
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider


def _youtube_abort(req) -> bool:
    blocked = {
        "media", "font", "websocket", "eventsource", "manifest",
    }
    blocked_domains = {
        "doubleclick.net", "googlesyndication.com",
        "google-analytics.com", "googletagmanager.com",
    }
    if req.resource_type in blocked:
        return True
    return any(d in req.url for d in blocked_domains)


class YouTubeSpider(YAWCBaseSpider):
    """
    Searches YouTube and extracts video metadata via window.ytInitialData.
    Best for: tutorials, how-to guides, gameplay, demonstrations.
    Output: url, embed_url, title, channel, views, description, thumbnail, platform="YouTube"
    """
    name = "youtube_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=1),
        "PLAYWRIGHT_ABORT_REQUEST": _youtube_abort,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 25_000,
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": [
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
                "--disable-extensions", "--autoplay-policy=no-user-gesture-required",
            ],
        },
    }

    def start_requests(self):
        encoded = self.query.replace(" ", "+")
        # sp=EgIQAQ%3D%3D filters to videos only
        url = f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAQ%3D%3D"
        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 4000)],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        await self._start_trace(page)

        video_data = await page.evaluate("""
            () => {
                try {
                    const data     = window.ytInitialData;
                    const contents = data?.contents
                        ?.twoColumnSearchResultsRenderer
                        ?.primaryContents
                        ?.sectionListRenderer
                        ?.contents;
                    if (!contents) return [];
                    const videos = [];
                    for (const section of contents) {
                        for (const item of (section?.itemSectionRenderer?.contents || [])) {
                            const v = item?.videoRenderer;
                            if (!v || !v.videoId) continue;
                            videos.push({
                                videoId:   v.videoId,
                                title:     v.title?.runs?.[0]?.text || '',
                                channel:   v.ownerText?.runs?.[0]?.text || '',
                                viewCount: v.viewCountText?.simpleText
                                        || v.viewCountText?.runs?.[0]?.text || '',
                                desc: v.detailedMetadataSnippets?.[0]
                                        ?.snippetText?.runs?.map(r => r.text)?.join('') || '',
                                thumbnail: v.thumbnail?.thumbnails?.slice(-1)[0]?.url || '',
                            });
                        }
                    }
                    return videos;
                } catch(e) { return []; }
            }
        """)

        if not video_data:
            # CSS fallback
            video_data = [
                {
                    "videoId":   _re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", a.attrib.get("href", "")).group(1)
                                 if _re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", a.attrib.get("href", "")) else "",
                    "title":     a.attrib.get("title", ""),
                    "channel":   "",
                    "viewCount": "",
                    "desc":      "",
                    "thumbnail": "",
                }
                for a in response.css("a#video-title")
                if a.attrib.get("href", "")
            ]

        await page.close()

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

