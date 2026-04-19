"""
Reddit Long-Running Crawler — 24 hr capable, nohup-friendly
============================================================
Run anonymously:
    nohup python reddit_crawler.py --target python --posts 500 > logs/crawler.log 2>&1 &

Run authenticated:
    nohup python reddit_crawler.py --target python --posts 500 \
        --username myuser --password mypass > logs/crawler.log 2>&1 &

Stop & resume: Ctrl+C or kill the process. Output saved incrementally to
output/<target>_posts.jsonl — resume is automatic on next run.

Full options: python reddit_crawler.py --help
"""

import asyncio
import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import scrapy
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from scrapy_playwright.page import PageMethod

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
LOG_DIR    = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Logging — file + stdout, captures everything including scrapy internals
# ──────────────────────────────────────────────────────────────────────────────
def setup_logging(target_name: str) -> logging.Logger:
    safe     = target_name.replace("/", "_")
    log_file = LOG_DIR / f"crawler_{safe}_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt      = "%(asctime)s [%(levelname)s] %(message)s"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers[:]:
        root.removeHandler(h)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt))

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(fmt))

    root.addHandler(fh)
    root.addHandler(sh)

    logger = logging.getLogger("reddit_crawler")
    logger.info(f"Log file: {log_file}")
    return logger


# ──────────────────────────────────────────────────────────────────────────────
# Progress / resume store
# ──────────────────────────────────────────────────────────────────────────────
class ProgressStore:
    def __init__(self, target_name: str, logger: logging.Logger):
        safe = target_name.replace("/", "_")
        self.output_path = OUTPUT_DIR / f"{safe}_posts.jsonl"
        self.seen_urls: set = set()
        self.logger = logger
        self._load_existing()

    def _load_existing(self):
        if not self.output_path.exists():
            return
        count = 0
        with open(self.output_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    self.seen_urls.add(obj.get("url", ""))
                    count += 1
                except json.JSONDecodeError:
                    pass
        if count:
            self.logger.info(f"[RESUME] Loaded {count} previously saved posts from {self.output_path}")

    @property
    def saved_count(self) -> int:
        return len(self.seen_urls)

    def is_seen(self, url: str) -> bool:
        return url in self.seen_urls

    def save(self, data: dict) -> bool:
        url = data.get("url", "")
        if url in self.seen_urls:
            return False
        self.seen_urls.add(url)
        with open(self.output_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")
        return True


# ──────────────────────────────────────────────────────────────────────────────
# Spider
# ──────────────────────────────────────────────────────────────────────────────
class HumanRedditSpider(scrapy.Spider):
    name = "reddit_human"

    # Class-level defaults — overwritten by runner via spider_opened signal
    store        = None
    app_logger   = None
    run_until    = 0.0
    target_posts = 500
    cooldown_ms  = 2500
    fetch_delay  = 4.0

    # All known Reddit post selectors across layouts
    FEED_SELECTORS = [
        "shreddit-post",
        "[data-testid='post-container']",
        ".Post",
        "div[data-fullname]",
        "a[data-click-id='body']",
        "a[href*='/comments/']",
    ]

    def __init__(self, target=None, username=None, password=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username        = username
        self.password        = password
        self._start_time     = time.time()
        self._posts_this_run = 0
        self._last_stats_log = time.time()

        if target:
            self.start_url   = f"https://www.reddit.com/r/{target}/"
            self.target_name = f"r/{target}"
        else:
            self.start_url   = "https://www.reddit.com/"
            self.target_name = "Home Feed"

    # ── safe logger (works even before app_logger is injected) ───────────────
    def _log(self, msg: str, level: str = "info"):
        lg = self.app_logger or logging.getLogger("reddit_crawler")
        getattr(lg, level)(msg)

    def _time_exceeded(self) -> bool:
        return self.run_until > 0 and time.time() >= self.run_until

    def _remaining_h(self) -> float:
        return max(0, (self.run_until - time.time()) / 3600)

    def _elapsed_m(self) -> float:
        return (time.time() - self._start_time) / 60

    def _maybe_log_stats(self, extra: str = ""):
        now = time.time()
        if now - self._last_stats_log >= 60:
            saved = self.store.saved_count if self.store else "?"
            self._log(
                f"[STATS] elapsed={self._elapsed_m():.1f}m  "
                f"remaining={self._remaining_h():.2f}h  "
                f"saved_total={saved}  "
                f"saved_this_run={self._posts_this_run}  {extra}"
            )
            self._last_stats_log = now

    # ── detect which selector Reddit is using ────────────────────────────────
    async def _detect_feed_selector(self, page):
        for sel in self.FEED_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                self._log(f"[SELECTOR] Matched: '{sel}'")
                return sel
            except Exception:
                self._log(f"[SELECTOR] Not found: '{sel}'", "debug")
        return None

    # ── entry point ──────────────────────────────────────────────────────────
    def start_requests(self):
        if self._time_exceeded():
            self._log("[TIME] Run window already elapsed — exiting.")
            return

        if self.username and self.password:
            self._log(f"[AUTH] Logging in as {self.username} …")
            yield scrapy.Request(
                url="https://www.reddit.com/login/",
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": "auth_session",
                },
                callback=self.parse_login,
                errback=self.handle_error,
            )
        else:
            self._log(f"[ANON] Scraping {self.target_name} anonymously.")
            yield self._build_feed_request()

    # ── login ─────────────────────────────────────────────────────────────────
    async def parse_login(self, response):
        page = response.meta["playwright_page"]
        try:
            await page.wait_for_selector('input[name="username"]', timeout=15000)
            await page.fill('input[name="username"]', self.username)
            await page.fill('input[name="password"]', self.password)
            async with page.expect_navigation(timeout=30000):
                await page.click('button[type="submit"]')
            self._log("[AUTH] Login successful.")
            await page.close()
            yield self._build_feed_request(context="auth_session")
        except Exception as exc:
            self._log(f"[AUTH] Login failed: {exc}", "error")
            await page.close()

    # ── scroll & collect links ────────────────────────────────────────────────
    async def parse_home(self, response):
        page    = response.meta.get("playwright_page")
        context = response.meta.get("playwright_context", "default")

        if not page:
            self._log("[FEED] No playwright page in response!", "error")
            return

        self._log(f"[FEED] Landed on: {page.url}")
        self._log(f"[FEED] Page title: {await page.title()}")

        feed_sel = await self._detect_feed_selector(page)

        if not feed_sel:
            if self.start_url.startswith("https://www.reddit.com/"):
                old_url = self.start_url.replace("www.reddit.com", "old.reddit.com")
                self._log(f"[FEED] No selector matched on new Reddit, retrying with old Reddit: {old_url}", "warning")
                try:
                    await page.goto(old_url, wait_until="networkidle", timeout=30000)
                    feed_sel = await self._detect_feed_selector(page)
                except Exception as exc:
                    self._log(f"[FEED] Old Reddit navigation failed: {exc}", "warning")

        if not feed_sel:
            # Save screenshot + page source snippet for debugging
            ss_path = LOG_DIR / f"feed_debug_{int(time.time())}.png"
            try:
                await page.screenshot(path=str(ss_path))
                self._log(f"[FEED] Screenshot saved: {ss_path}", "error")
            except Exception:
                pass
            content = await page.content()
            self._log(f"[FEED] Page source (first 3000 chars):\n{content[:3000]}", "error")
            await page.close()
            return

        # JS extractor — handles both shreddit-post and legacy layouts
        js_extract = f"""
        () => {{
            let links = [];

            // shreddit-post (new Reddit 2023+)
            const shreddit = document.querySelectorAll('{feed_sel}');
            if (shreddit.length > 0) {{
                links = Array.from(shreddit)
                    .map(p => p.getAttribute('permalink') || p.getAttribute('data-permalink'))
                    .filter(Boolean);
            }}

            // fallback: anchor tags used in old/transitional new-Reddit
            if (links.length === 0) {{
                links = Array.from(document.querySelectorAll('a[data-click-id="body"], a[href*="/comments/"]'))
                    .map(a => a.getAttribute('href'))
                    .filter(l => l && l.startsWith('/r/'));
            }}

            return [...new Set(links)];
        }}
        """

        all_links: set = set()
        scroll_no     = 0
        stale_scrolls = 0
        MAX_STALE     = 12

        already_saved = self.store.saved_count if self.store else 0
        needed        = self.target_posts - already_saved
        self._log(f"[SCROLL] Need {needed} more posts (already saved: {already_saved})")

        while True:
            if self._time_exceeded():
                self._log("[TIME] 24 hr budget exhausted — stopping scroll.")
                break
            if self.store and self.store.saved_count >= self.target_posts:
                self._log("[DONE] Target post count reached.")
                break
            if len(all_links) >= needed:
                self._log(f"[SCROLL] Have {len(all_links)} links — proceeding to scrape.")
                break
            if stale_scrolls >= MAX_STALE:
                self._log(f"[SCROLL] Feed exhausted after {MAX_STALE} stale scrolls.")
                break

            prev = len(all_links)
            await page.evaluate("window.scrollBy(0, 1500)")
            await page.wait_for_timeout(self.cooldown_ms)

            raw = await page.evaluate(js_extract)
            for link in raw:
                full = ("https://www.reddit.com" + link) if link.startswith("/") else link
                if not self.store or not self.store.is_seen(full):
                    all_links.add(link)

            scroll_no += 1
            gained = len(all_links) - prev

            if gained == 0:
                stale_scrolls += 1
                self._log(f"[SCROLL] #{scroll_no}: no new posts (stale {stale_scrolls}/{MAX_STALE})", "debug")
            else:
                stale_scrolls = 0
                self._log(f"[SCROLL] #{scroll_no}: +{gained} links (total={len(all_links)})")

            self._maybe_log_stats(f"scroll={scroll_no}")

        self._log(f"[SCROLL] Queuing {len(all_links)} post requests.")
        await page.close()

        for link in list(all_links):
            if self._time_exceeded():
                break
            full_url = ("https://www.reddit.com" + link) if link.startswith("/") else link
            if self.store and self.store.is_seen(full_url):
                continue
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": context,
                    "playwright_page_methods": [
                        PageMethod(
                            "wait_for_selector",
                            "shreddit-comment, [data-testid='comment'], .Comment",
                            timeout=12000,
                        ),
                    ],
                    "download_delay": self.fetch_delay,
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )

    # ── parse individual post ────────────────────────────────────────────────
    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

        data = {
            "url":        response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "title": (
                response.css("h1::text").get(default="")
                or response.css("[data-adclicklocation='title'] h3::text").get(default="")
            ).strip(),
            "body": (
                response.css("shreddit-post [slot='text-body'] p::text").getall()
                or response.css("div[id$='-post-rtjson-content'] p::text").getall()
                or response.css(".Post .RichTextJSON-root p::text").getall()
            ),
            "comments": (
                response.css("shreddit-comment div[slot='comment'] p::text").getall()
                or response.css("[data-testid='comment'] p::text").getall()
            ),
        }

        if page:
            try:
                await page.close()
            except Exception:
                pass

        if self.store:
            saved = self.store.save(data)
            if saved:
                self._posts_this_run += 1
                total = self.store.saved_count
                if total % 10 == 0:
                    self._log(
                        f"[SAVED] {total} posts total  "
                        f"({self._posts_this_run} this run)  "
                        f"remaining={self._remaining_h():.2f}h"
                    )
                self._maybe_log_stats()

        yield data

    # ── error handler ────────────────────────────────────────────────────────
    async def handle_error(self, failure):
        self._log(f"[ERR] {failure.request.url} — {failure.value}", "warning")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass

    # ── request builder ───────────────────────────────────────────────────────
    def _build_feed_request(self, context="default"):
        return scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_context": context,
                # No wait_for_selector here — we do it ourselves in parse_home
                # so we can detect which layout Reddit is using and debug properly
            },
            callback=self.parse_home,
            errback=self.handle_error,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Scrapy settings
# ──────────────────────────────────────────────────────────────────────────────
SCRAPY_SETTINGS = {
    "DOWNLOAD_HANDLERS": {
        "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "PLAYWRIGHT_BROWSER_TYPE": "chromium",
    "PLAYWRIGHT_LAUNCH_OPTIONS": {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    },
    "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 4,
    "PLAYWRIGHT_CONTEXTS": {
        "default": {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
            "locale":   "en-US",
            "java_script_enabled": True,
        },
        "auth_session": {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
            "locale":   "en-US",
            "java_script_enabled": True,
        },
    },
    "CONCURRENT_REQUESTS":             4,
    "DOWNLOAD_DELAY":                  3,
    "RANDOMIZE_DOWNLOAD_DELAY":        True,
    "AUTOTHROTTLE_ENABLED":            True,
    "AUTOTHROTTLE_START_DELAY":        3,
    "AUTOTHROTTLE_MAX_DELAY":          30,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
    "RETRY_TIMES":                     3,
    "RETRY_HTTP_CODES":                [429, 500, 502, 503, 504],
    "ROBOTSTXT_OBEY":                  False,
    "COOKIES_ENABLED":                 True,
    "LOG_LEVEL":                       "DEBUG",
    "FEEDS":                           {},
}


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Long-running Reddit crawler (24 hr, nohup-friendly).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--target",      default=None,  help="Subreddit (no r/ prefix). Omit for home feed.")
    p.add_argument("--posts",       type=int,   default=500,  help="Max posts to collect (default 500)")
    p.add_argument("--hours",       type=float, default=24.0, help="Max run time in hours (default 24)")
    p.add_argument("--username",    default=None,  help="Reddit username (optional)")
    p.add_argument("--password",    default=None,  help="Reddit password (optional)")
    p.add_argument("--cooldown-ms", type=int,   default=2500, help="ms between scrolls (default 2500)")
    p.add_argument("--fetch-delay", type=float, default=4.0,  help="Seconds between post fetches (default 4.0)")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

    args   = parse_args()
    tname  = f"r/{args.target}" if args.target else "home"
    logger = setup_logging(tname)

    store = ProgressStore(tname, logger)

    def _shutdown(signum, frame):
        logger.info(
            f"[SIGNAL] Signal {signum} received. "
            f"Saved so far: {store.saved_count} posts → {store.output_path}"
        )
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    run_until = time.time() + args.hours * 3600
    logger.info(
        f"[START] target={tname}  posts={args.posts}  hours={args.hours}  "
        f"run_until={datetime.fromtimestamp(run_until):%Y-%m-%d %H:%M:%S}  "
        f"already_saved={store.saved_count}"
    )

    if store.saved_count >= args.posts:
        logger.info(f"[DONE] Target already reached from previous run. Output: {store.output_path}")
        return

    settings = get_project_settings()
    settings.setdict(SCRAPY_SETTINGS)

    process = CrawlerProcess(settings)
    crawler = process.create_crawler(HumanRedditSpider)

    # Wire shared state into the spider instance right after it's created,
    # before any requests fire.
    def on_spider_opened(spider):
        spider.store        = store
        spider.app_logger   = logger
        spider.run_until    = run_until
        spider.target_posts = args.posts
        spider.cooldown_ms  = args.cooldown_ms
        spider.fetch_delay  = args.fetch_delay
        logger.info(
            f"[SPIDER] State wired. store={store.output_path}  "
            f"run_until={datetime.fromtimestamp(run_until):%H:%M:%S}"
        )

    crawler.signals.connect(on_spider_opened, signal=signals.spider_opened)

    process.crawl(
        crawler,
        target   = args.target,
        username = args.username,
        password = args.password,
    )

    try:
        process.start()
    except SystemExit:
        pass

    logger.info(
        f"[END] Crawl finished. Total posts saved: {store.saved_count}. "
        f"Output: {store.output_path}"
    )


if __name__ == "__main__":
    main()
