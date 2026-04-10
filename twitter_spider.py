# ══════════════════════════════════════════════════════════════════════════════
# twitter_spider.py
# ══════════════════════════════════════════════════════════════════════════════

import scrapy
import os
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from dotenv import load_dotenv

load_dotenv()

def _twitter_abort(req) -> bool:
    return req.resource_type in {
        "image", "media", "font", "stylesheet", "manifest",
    }

# Build the cookie object dynamically from the environment
_twitter_cookies = []
_auth_token = os.getenv("TWITTER_AUTH_TOKEN")
if _auth_token:
    _twitter_cookies.append({
        "name": "auth_token",
        "value": _auth_token,
        "domain": ".twitter.com",
        "path": "/",
        "secure": True,
    })

class TwitterSpider(YAWCBaseSpider):
    """
    Scrapes Twitter (X) search results using ENV variables for Auth.
    Output: url, title (author), body (tweet), score (likes), platform="Twitter"
    """
    name = "twitter_spider"

    custom_settings = {
        **YAWCBaseSpider.base_settings(concurrent=2),
        "PLAYWRIGHT_ABORT_REQUEST": _twitter_abort,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                # Inject the session cookie directly into the headless browser
                "storage_state": {
                    "cookies": _twitter_cookies,
                    "origins": []
                }
            }
        }
    }

    def start_requests(self):
        import urllib.parse
        if not _auth_token:
            self.logger.error("❌ TWITTER_AUTH_TOKEN is not set in environment variables!")
            return

        encoded = urllib.parse.quote(self.query)
        url = f"https://twitter.com/search?q={encoded}&src=typed_query"
        yield scrapy.Request(
            url=url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Wait for tweets to render
                    PageMethod("wait_for_selector", "[data-testid='tweet']", timeout=15000),
                    PageMethod("wait_for_timeout", 2000),
                ],
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        
        tweets = await page.evaluate(f"""
            () => {{
                const results = [];
                const articles = document.querySelectorAll('[data-testid="tweet"]');
                
                for (const article of articles) {{
                    if (results.length >= {self.k}) break;
                    
                    const textEl = article.querySelector('[data-testid="tweetText"]');
                    const body = textEl ? textEl.innerText.trim() : '';
                    
                    const timeEl = article.querySelector('time');
                    const linkEl = timeEl ? timeEl.closest('a') : null;
                    const url = linkEl ? 'https://twitter.com' + linkEl.getAttribute('href') : '';
                    
                    const userEl = article.querySelector('[data-testid="User-Name"]');
                    const title = userEl ? userEl.innerText.split('\\n').trim() : 'Unknown User';
                    
                    const likeEl = article.querySelector('[data-testid="like"]');
                    const score = likeEl ? likeEl.getAttribute('aria-label').replace(/[^0-9]/g, '') : '0';
                    
                    if (body && url) {{
                        results.push({{ title, url, body, score }});
                    }}
                }}
                return results;
            }}
        """)
        await page.close()

        for t in tweets:
            yield {
                "url": t.get("url"),
                "title": t.get("title"),
                "body": t.get("body"),
                "score": t.get("score") or "0",
                "platform": "Twitter",
            }