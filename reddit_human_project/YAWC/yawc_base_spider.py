"""
YAWC Base Spider — yawc_base_spider.py
=======================================
All YAWC platform spiders inherit from YAWCBaseSpider.

Provides:
  - Playwright tracing (start on open, stop + save on close / error)
  - Trace files saved to: <trace_dir>/<spider_name>_<timestamp>.zip
  - Standard __init__ signature (query, k, chat_id, trace_dir)
  - handle_error that closes the page AND saves the trace

Usage in each spider:
    from yawc_base_spider import YAWCBaseSpider

    class RedditSpider(YAWCBaseSpider):
        name = "reddit_spider"
        ...

Playwright Tracing custom_settings to add to each spider:
    "PLAYWRIGHT_CONTEXTS": {
        "default": {
            "tracing": {
                "screenshots": True,
                "snapshots":   True,
                "sources":     True,
            }
        }
    }

How tracing works with scrapy-playwright:
  - scrapy-playwright opens a browser context per spider run.
  - We use page.context to start/stop traces in parse callbacks.
  - On handle_error we stop and save the trace before closing the page.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import scrapy
from scrapy_playwright.page import PageMethod


def _default_abort(req) -> bool:
    """Block non-essential resources. Subclasses can override."""
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


class YAWCBaseSpider(scrapy.Spider):
    """
    Base class for all YAWC spiders.
    Subclasses must define: name, start_requests(), parse()
    """

    # Subclasses override this to allow images (image_spider) etc.
    ABORT_RESOURCE_TYPES: frozenset[str] = frozenset({
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    })

    def __init__(
        self,
        query:     str = "",
        k:         str = "8",
        chat_id:   str = "",
        trace_dir: str = "",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.query     = query
        self.k         = int(k)
        self.chat_id   = chat_id or "default"
        self.trace_dir = Path(trace_dir) if trace_dir else Path("./traces") / self.chat_id
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        # Track which browser contexts have tracing started
        self._tracing_started: set[int] = set()

    # ── Tracing helpers ───────────────────────────────────────────────────────

    async def _start_trace(self, page) -> None:
        """Start tracing on this page's browser context (once per context)."""
        try:
            ctx_id = id(page.context)
            if ctx_id not in self._tracing_started:
                await page.context.tracing.start(
                    screenshots=True,
                    snapshots=True,
                    sources=True,
                )
                self._tracing_started.add(ctx_id)
        except Exception as e:
            self.logger.debug(f"[TRACE] Could not start tracing: {e}")

    async def _stop_trace(self, page, label: str = "ok") -> Optional[Path]:
        """Stop tracing and save to a .zip file. Returns the path or None."""
        try:
            ctx_id = id(page.context)
            if ctx_id not in self._tracing_started:
                return None
            ts       = int(time.time())
            filename = f"{self.name}_{label}_{ts}.zip"
            out_path = self.trace_dir / filename
            await page.context.tracing.stop(path=str(out_path))
            self._tracing_started.discard(ctx_id)
            self.logger.info(f"[TRACE] Saved trace: {out_path}")
            return out_path
        except Exception as e:
            self.logger.warning(f"[TRACE] Could not stop tracing: {e}")
            return None

    # ── Default error handler (subclasses can call super()) ──────────────────

    async def handle_error(self, failure) -> None:
        """
        Default error handler.
        Closes the Playwright page and saves a trace .zip tagged with 'error'.
        """
        url  = failure.request.url
        page = failure.request.meta.get("playwright_page")
        self.logger.warning(f"[{self.name}] ✗ Failed: {url} — {failure.getErrorMessage()}")

        if page:
            trace_path = await self._stop_trace(page, label="error")
            if trace_path:
                self.logger.warning(
                    f"[{self.name}] 🐛 Trace saved: {trace_path.name} "
                    f"(chat_id={self.chat_id})"
                )
            try:
                await page.close()
            except Exception:
                pass

    # ── Shared custom_settings template (merge into subclass custom_settings) ─

    @classmethod
    def base_settings(cls, concurrent: int = 8) -> dict:
        """
        Returns the standard Playwright Scrapy settings.
        Spider classes should merge this into their own custom_settings.

        Usage:
            custom_settings = {
                **YAWCBaseSpider.base_settings(concurrent=12),
                "LOG_LEVEL": "INFO",
                # ... spider-specific overrides
            }
        """
        return {
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
                ],
            },
            # Tracing is started/stopped manually in callbacks (not via context config)
            # because scrapy-playwright's context config tracing support varies by version.
            "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 20_000,
            "CONCURRENT_REQUESTS":            concurrent,
            "CONCURRENT_REQUESTS_PER_DOMAIN": concurrent,
            "DOWNLOAD_DELAY":         0,
            "AUTOTHROTTLE_ENABLED":   False,
            "RETRY_TIMES":            1,
            "LOG_LEVEL":              "INFO",
        }
