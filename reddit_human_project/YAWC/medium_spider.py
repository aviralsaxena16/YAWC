from urllib.parse import urljoin
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider

class MediumSpider(YAWCBaseSpider):
    name = "medium_spider"

    def __init__(self, query="python", k="8", chat_id="", trace_dir="", *args, **kwargs):
        super().__init__(query=query, k=k, chat_id=chat_id, trace_dir=trace_dir, *args, **kwargs)
        # The start_url is derived from the user's target URL and inferred search query.
        self.start_url = f"https://medium.com/search?q={self.query}"

    def start_requests(self):
        yield scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    # Wait for a reasonable time for dynamic content to load.
                    # A more robust approach might involve waiting for a specific selector.
                    PageMethod("wait_for_timeout", 5000), 
                    # Optionally, wait until a key element like an article title is visible:
                    # PageMethod("wait_for_selector", "article h2 a")
                ],
            },
            callback=self.parse,
            errback=self.handle_error,
        )

    async def parse(self, response):
        page = response.meta.get("playwright_page")
        
        if not page:
            self.logger.error("Playwright page object not found in response.meta for %s", response.url)
            # Fallback to Scrapy's built-in selectors if page isn't available, or skip
            # For this task, we assume Playwright page is always present.
            return

        try:
            # Use page.evaluate() to execute JavaScript in the browser context.
            # This allows efficient extraction of multiple elements and their attributes.
            # The selectors are inferred by inspecting the structure of medium.com search results.
            extracted_items = await page.evaluate('''() => {
                const results = [];
                // Select all article elements, which typically represent individual search results.
                document.querySelectorAll('article').forEach(article => {
                    // Extract the title and URL. The title is usually within an h2 tag,
                    // which contains an <a> tag with the href.
                    const titleLink = article.querySelector('h2 a');
                    
                    // Extract the summary/body. Medium often uses a paragraph with a specific class
                    // like 'pw-post-body-paragraph' for the post's summary on search pages.
                    const summaryElement = article.querySelector('p.pw-post-body-paragraph'); 
                    
                    const url = titleLink ? titleLink.href : null;
                    const title = titleLink ? titleLink.innerText.trim() : null;
                    const body = summaryElement ? summaryElement.innerText.trim() : null;

                    // Only yield an item if both a URL and a title are successfully found.
                    if (url && title) {
                        results.push({
                            url: url,
                            title: title,
                            body: body,
                            platform: "medium"
                        });
                    }
                });
                return results;
            }''')

            for item in extracted_items:
                yield item

        except Exception as e:
            self.logger.error(f"Error during page evaluation on {response.url}: {e}")
        finally:
            # Always close the Playwright page to release resources.
            if page:
                try: 
                    await page.close()
                except Exception as e: 
                    self.logger.warning(f"Failed to close playwright page for {response.url}: {e}")