# ══════════════════════════════════════════════════════════════════════════════
# yawc_base_spider.py  –  YAWC  |  Shared base spider
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import scrapy


class YAWCBaseSpider(scrapy.Spider):
    """
    Base class for all YAWC platform spiders.

    CLI args  (-a key=value):
      query     Search query string       (default: "python")
      k         Max items to collect      (default: 50)
      headless  "true" / "false"          (default: true)
      trace     "true" / "false"          (default: false) – Playwright trace

    Sub-classes must implement:
      start_requests(self)
      parse_search(self, response)   [async]
    """

    @staticmethod
    def base_settings(concurrent: int = 3) -> dict:
        return {
            "DOWNLOAD_HANDLERS": {
                "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            },
            # ── CRITICAL for Windows ─────────────────────────────────────────
            # Playwright needs ProactorEventLoop on Windows to spawn browser
            # subprocesses. SelectorEventLoop (the old default) will hang or
            # crash when Playwright tries to launch Chromium.
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "ASYNCIO_EVENT_LOOP": (
                "asyncio.ProactorEventLoop"
                if sys.platform == "win32"
                else "asyncio.SelectorEventLoop"
            ),
            "PLAYWRIGHT_BROWSER_TYPE": "chromium",
            "PLAYWRIGHT_LAUNCH_OPTIONS": {
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                ],
            },
            "CONCURRENT_REQUESTS":             concurrent,
            "CONCURRENT_REQUESTS_PER_DOMAIN":  concurrent,
            "DOWNLOAD_DELAY":                  1,
            "AUTOTHROTTLE_ENABLED":            True,
            "AUTOTHROTTLE_START_DELAY":        1,
            "AUTOTHROTTLE_MAX_DELAY":          10,
            "ROBOTSTXT_OBEY":                  False,
            "LOG_LEVEL":                       "INFO",
            "FEEDS": {
                "output_%(name)s.jsonl": {
                    "format":    "jsonlines",
                    "overwrite": True,
                }
            },
        }

    def __init__(
        self,
        query:    str = "python",
        k:        str = "50",
        headless: str = "true",
        trace:    str = "false",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.query    = query
        self.k        = int(k)
        self.headless = headless.lower() != "false"
        self.trace    = trace.lower() == "true"

        # Apply headless to launch options
        self.custom_settings = dict(self.custom_settings or {})
        launch = self.custom_settings.setdefault("PLAYWRIGHT_LAUNCH_OPTIONS", {})
        launch["headless"] = self.headless

        self.logger.info(
            f"[{self.name}] Mode: {'HEADLESS' if self.headless else 'HEADFUL'}  "
            f"| Query: '{self.query}'  | k={self.k}"
        )

    # ── Playwright trace helpers ──────────────────────────────────────────────

    async def _start_trace(self, page) -> None:
        if not self.trace or page is None:
            return
        try:
            await page.context.tracing.start(screenshots=True, snapshots=True)
        except Exception as exc:
            self.logger.warning(f"[{self.name}] Trace start failed: {exc}")

    async def _stop_trace(self, page, suffix: str = "trace") -> None:
        if not self.trace or page is None:
            return
        os.makedirs("traces", exist_ok=True)
        path = f"traces/{self.name}_{suffix}.zip"
        try:
            await page.context.tracing.stop(path=path)
            self.logger.info(f"[{self.name}] Trace → {path}")
        except Exception as exc:
            self.logger.warning(f"[{self.name}] Trace stop failed: {exc}")

    # ── Shared error handler ──────────────────────────────────────────────────

    async def handle_error(self, failure) -> None:
        url  = failure.request.url
        page = failure.request.meta.get("playwright_page")
        self.logger.error(f"[{self.name}] Request failed: {url} — {failure.getErrorMessage()}")
        if page:
            try:
                os.makedirs("debug", exist_ok=True)
                path = f"debug/{self.name}_error.png"
                await page.screenshot(path=path)
                self.logger.info(f"[{self.name}] Error screenshot → {path}")
                await page.close()
            except Exception:
                pass
