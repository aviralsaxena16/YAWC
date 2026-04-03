"""
YAWC Auto-Generated Spider: internshala_com
Target: https://internshala.com/ (internshala.com)
Fill in extraction logic using the codegen output in internshala_com_codegen.py
"""
import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider   # see spider_base.py


class InternshalaComSpider(YAWCBaseSpider):
    name = "internshala_com_spider"

    def __init__(self, query="", k="8", chat_id="", trace_dir="", *args, **kwargs):
        super().__init__(query=query, k=k, chat_id=chat_id, trace_dir=trace_dir, *args, **kwargs)
        # TODO: Build search URL from self.query
        self.start_url = "https://internshala.com/"

    def start_requests(self):
        yield scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 3000)],
            },
            callback=self.parse,
            errback=self.handle_error,
        )

    async def parse(self, response):
        page = response.meta.get("playwright_page")
        # TODO: Extract items using selectors from internshala_com_codegen.py
        # items = await page.evaluate("() => []")
        # for item in items[:self.k]:
        #     yield {"title": item, "url": response.url, "body": "", "platform": "internshala_com"}
        if page:
            await page.close()