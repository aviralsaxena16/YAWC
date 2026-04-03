import json
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parent.parent))

import scrapy
from scrapy_playwright.page import PageMethod
from yawc_base_spider import YAWCBaseSpider
from yawc_config import GEMINI_KEY
import google.generativeai as genai

class MediumSpider(YAWCBaseSpider):
    name = "medium_spider"

    def __init__(self, query="", k="8", chat_id="", trace_dir="", *args, **kwargs):
        super().__init__(query=query, k=k, chat_id=chat_id, trace_dir=trace_dir, *args, **kwargs)
        self.start_url = "https://medium.com/search?q=python"

    def start_requests(self):
        yield scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [PageMethod("wait_for_timeout", 4000)],
            },
            callback=self.parse,
            errback=self.handle_error,
        )

    async def parse(self, response):
        page = response.meta.get("playwright_page")
        if not page: return
        
        try:
            # 1. Grab raw page text
            raw_text = await page.evaluate("() => document.body.innerText")
            
            # 2. Use Gemini to extract the data cleanly
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            llm_prompt = f"Extract the top {self.k} search results from this raw webpage text. Return ONLY a valid JSON list of objects with keys: 'url', 'title', 'body'. Base URL is medium.com. Raw text: {raw_text[:15000]}"
            
            resp = model.generate_content(llm_prompt)
            clean_json = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            
            items = json.loads(clean_json)
            for item in items:
                item["platform"] = "medium"
                yield item
                
        except Exception as e:
            self.logger.error(f"LLM Extraction failed: {e}")
        finally:
            await page.close()