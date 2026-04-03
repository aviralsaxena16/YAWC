from __future__ import annotations

import os
import sys
import json
import asyncio
import subprocess
import tempfile
import platform
import textwrap
from pathlib import Path

from yawc_config import THREAD_POOL, SPIDER_DIR


def _run_spider_blocking(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode not in (0, 1):
        print(f"[YAWC] Spider exited with code {result.returncode}", flush=True)


async def scrape_platform(
    query: str,
    k: int,
    spider_file: str,
    chat_id: str,
    trace_dir: Path,
) -> list[dict]:
    tmp = tempfile.mktemp(suffix=".json", dir=tempfile.gettempdir())
    null_dev = "NUL" if platform.system() == "Windows" else "/dev/null"
    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "runspider",
        str(SPIDER_DIR / spider_file),
        "-a",
        f"query={query}",
        "-a",
        f"k={k}",
        "-a",
        f"chat_id={chat_id}",
        "-a",
        f"trace_dir={trace_dir}",
        "-o",
        tmp,
        "--logfile",
        null_dev,
    ]
    print(f"[YAWC] Launching {spider_file} k={k}", flush=True)

    if platform.system() == "Windows":
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(THREAD_POOL, _run_spider_blocking, cmd)
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def drain():
            async for line in proc.stderr:
                d = line.decode(errors="replace").rstrip()
                if d:
                    print(f"[{spider_file}] {d}", flush=True)

        await asyncio.gather(drain(), proc.wait())

    results = []
    if os.path.exists(tmp):
        try:
            with open(tmp, "r", encoding="utf-8") as f:
                raw = json.load(f)
                results = raw if isinstance(raw, list) else [raw]
        except Exception as e:
            print(f"[YAWC] Parse error {spider_file}: {e}", flush=True)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return results


async def scrape_platforms(
    query: str, platforms: list[str], mode: str, chat_id: str
) -> list[dict]:
    from yawc_config import TRACE_DIR, PLATFORM_SPIDERS, PLATFORM_K

    trace_dir = TRACE_DIR / chat_id
    trace_dir.mkdir(parents=True, exist_ok=True)

    tasks = [
        scrape_platform(
            query, PLATFORM_K[p][mode], PLATFORM_SPIDERS[p], chat_id, trace_dir
        )
        for p in platforms
    ]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    all_posts = []
    source_idx = 1
    for plat, result in zip(platforms, results_list):
        if isinstance(result, Exception):
            print(f"[YAWC] {plat} error: {result}", flush=True)
            continue
        for post in result:
            post["platform"] = plat.capitalize()
            post["index"] = source_idx
            all_posts.append(post)
            source_idx += 1
    return all_posts


def _spider_scaffold(name: str, url: str, codegen: str) -> str:
    from urllib.parse import urlparse

    domain = urlparse(url).netloc
    return textwrap.dedent(f'''
        """
        YAWC Auto-Generated Spider: {name}
        Target: {url} ({domain})
        Fill in extraction logic using the codegen output in {name}_codegen.py
        """
        import scrapy
        from scrapy_playwright.page import PageMethod
        from yawc_base_spider import YAWCBaseSpider   # see spider_base_spider.py


        class {name.title().replace('_','')}Spider(YAWCBaseSpider):
            name = "{name}_spider"

            def __init__(self, query="", k="8", chat_id="", trace_dir="", *args, **kwargs):
                super().__init__(query=query, k=k, chat_id=chat_id, trace_dir=trace_dir, *args, **kwargs)
                self.start_url = "{url}"

            def start_requests(self):
                yield scrapy.Request(
                    url=self.start_url,
                    meta={{
                        "playwright": True,
                        "playwright_include_page": True,
                        "playwright_page_methods": [PageMethod("wait_for_timeout", 3000)],
                    }},
                    callback=self.parse,
                    errback=self.handle_error,
                )

            async def parse(self, response):
                page = response.meta.get("playwright_page")
                if page:
                    await page.close()
                yield {{"url": response.url, "title": "", "body": "", "platform": "{name}"}}
    ''')
