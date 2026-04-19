"""
Reddit Long-Running Crawler — 24 hr capable, nohup-friendly
============================================================
Run anonymously (no credentials needed):
    nohup python reddit_crawler.py --target python --posts 500 > logs/crawler.log 2>&1 &

Run authenticated:
    nohup python reddit_crawler.py --target python --posts 500 \
        --username myuser --password mypass > logs/crawler.log 2>&1 &

Stop & resume: Ctrl+C or kill the process. Output is saved incrementally to
output/<target>_posts.jsonl — resume is automatic on next run.

Full options: python reddit_crawler.py --help
"""

import asyncio
import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
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
# Logging setup  (file + stdout)
# ──────────────────────────────────────────────────────────────────────────────
def setup_logging(target_name: str) -> logging.Logger:
    safe = target_name.replace("/", "_")
    log_file = LOG_DIR / f"crawler_{safe}_{datetime.now():%Y%m%d_%H%M%S}.log"

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("reddit_crawler")
    logger.info(f"Logging to: {log_file}")
    return logger


# ──────────────────────────────────────────────────────────────────────────────
# Progress / resume store
# ──────────────────────────────────────────────────────────────────────────────
class ProgressStore:
    """Append-only JSONL writer with resume support."""

    def __init__(self, target_name: str, logger: logging.Logger):
        safe = target_name.replace("/", "_")
        self.output_path = OUTPUT_DIR / f"{safe}_posts.jsonl"
        self.seen_urls: set[str] = set()
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
            self.logger.info(
                f"[RESUME] Found {count} previously saved posts in {self.output_path}"
            )

    @property
    def saved_count(self) -> int:
        return len(self.seen_urls)

    def is_seen(self, url: str) -> bool:
        return url in self.seen_urls

    def save(self, data: dict):
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

    # Injected by the runner
    store: ProgressStore = None
    app_logger: logging.Logger = None
    run_until: float = 0          # epoch seconds
    target_posts: int = 500
    cooldown_min: float = 2.5     # seconds between scroll steps
    cooldown_max: float = 5.0     # seconds between post fetches

    def __init__(self, target=None, username=None, password=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username
        self.password = password

        if target:
            self.start_url  = f"https://www.reddit.com/r/{target}/"
            self.target_name = f"r/{target}"
        else:
            self.start_url  = "https://www.reddit.com/"
            self.target_name = "Home Feed"

        self._stats_interval = 60   # log stats every N seconds
        self._last_stats_log = time.time()
        self._posts_saved = 0

    # ── entry point ──────────────────────────────────────────────────────────
    def start_requests(self):
        if self._time_exceeded():
            self.app_logger.info("[TIME] 24 hr window already elapsed — exiting.")
            return

        if self.username and self.password:
            self.app_logger.info(f"[AUTH] Logging in as {self.username} …")
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
            self.app_logger.info(
                f"[ANON] No credentials — scraping {self.target_name} anonymously."
            )
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
            self.app_logger.info("[AUTH] Login successful.")
            await page.close()
            yield self._build_feed_request(context="auth_session")
        except Exception as exc:
            self.app_logger.error(f"[AUTH] Login failed: {exc}")
            await page.close()

    # ── scroll & collect links ────────────────────────────────────────────────
    async def parse_home(self, response):
        page = response.meta.get("playwright_page")
        if not page:
            return

        context = response.meta.get("playwright_context", "default")
        all_links: set[str] = set()
        scroll_no = 0

        self.app_logger.info(f"[SCROLL] Starting feed scroll on {self.target_name} …")

        while True:
            # Time-budget check
            if self._time_exceeded():
                self.app_logger.info("[TIME] 24 hr budget exhausted — stopping scroll.")
                break

            # Posts-budget check  (account for already saved posts)
            already = self.store.saved_count
            needed  = self.target_posts - already
            if needed <= 0 or len(all_links) >= needed:
                self.app_logger.info(
                    f"[SCROLL] Collected enough links ({len(all_links)}) — moving to scrape."
                )
                break

            await page.evaluate("window.scrollBy(0, 1500)")
            await page.wait_for_timeout(int(self.cooldown_min * 1000))

            raw = await page.evaluate("""
                () => {
                    const posts = document.querySelectorAll('shreddit-post');
                    return Array.from(posts)
                        .map(p => p.getAttribute('permalink'))
                        .filter(l => l);
                }
            """)

            new_in_batch = 0
            for link in raw:
                if link not in all_links and not self.store.is_seen(
                    response.urljoin(link)
                ):
                    all_links.add(link)
                    new_in_batch += 1

            scroll_no += 1
            self._maybe_log_stats(extra=f"scroll={scroll_no} new_links={new_in_batch} total_links={len(all_links)}")

        self.app_logger.info(
            f"[SCROLL] Done. Queueing {len(all_links)} post detail requests."
        )

        for link in list(all_links):
            if self._time_exceeded():
                break
            full_url = response.urljoin(link)
            if self.store.is_seen(full_url):
                continue
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": context,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "shreddit-comment", timeout=15000),
                    ],
                    "download_delay": self.cooldown_max,
                },
                callback=self.parse_post,
                errback=self.handle_error,
            )

        await page.close()

    # ── parse individual post ────────────────────────────────────────────────
    async def parse_post(self, response):
        page = response.meta.get("playwright_page")

        data = {
            "url":        response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "title":      response.css("h1::text").get(default="").strip(),
            "body":       (
                response.css("shreddit-post [slot='text-body'] p::text").getall()
                or response.css("div[id$='-post-rtjson-content'] p::text").getall()
            ),
            "comments": response.css(
                "shreddit-comment div[slot='comment'] p::text"
            ).getall(),
        }

        saved = self.store.save(data)
        if saved:
            self._posts_saved += 1
            self._maybe_log_stats()

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield data

    # ── error handler ────────────────────────────────────────────────────────
    async def handle_error(self, failure):
        self.app_logger.warning(f"[ERR] {failure.request.url} — {failure.value}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass

    # ── helpers ───────────────────────────────────────────────────────────────
    def _build_feed_request(self, context="default"):
        return scrapy.Request(
            url=self.start_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_context": context,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "shreddit-post", timeout=20000),
                ],
            },
            callback=self.parse_home,
            errback=self.handle_error,
        )

    def _time_exceeded(self) -> bool:
        return time.time() >= self.run_until

    def _maybe_log_stats(self, extra: str = ""):
        now = time.time()
        if now - self._last_stats_log >= self._stats_interval:
            elapsed_min = (now - (self.run_until - 24 * 3600)) / 60
            remaining_hr = max(0, (self.run_until - now) / 3600)
            total_saved = self.store.saved_count
            self.app_logger.info(
                f"[STATS] elapsed={elapsed_min:.1f}m  remaining={remaining_hr:.2f}h  "
                f"saved_total={total_saved}  saved_this_run={self._posts_saved}  {extra}"
            )
            self._last_stats_log = now


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
            "locale": "en-US",
        },
        "auth_session": {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        },
    },
    "CONCURRENT_REQUESTS":            4,
    "DOWNLOAD_DELAY":                 3,
    "RANDOMIZE_DOWNLOAD_DELAY":       True,
    "AUTOTHROTTLE_ENABLED":           True,
    "AUTOTHROTTLE_START_DELAY":       3,
    "AUTOTHROTTLE_MAX_DELAY":         30,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
    "RETRY_TIMES":                    3,
    "RETRY_HTTP_CODES":               [429, 500, 502, 503, 504],
    "ROBOTSTXT_OBEY":                 False,
    "COOKIES_ENABLED":                True,
    "LOG_LEVEL":                      "WARNING",   # suppress scrapy noise; our logger handles info
    "FEEDS": {},                                   # we write output ourselves
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
    p.add_argument("--target",   default=None,
                   help="Subreddit name without r/ prefix (omit for home feed)")
    p.add_argument("--posts",    type=int, default=500,
                   help="Max posts to collect (default 500)")
    p.add_argument("--hours",    type=float, default=24.0,
                   help="Max run time in hours (default 24)")
    p.add_argument("--username", default=None, help="Reddit username (optional)")
    p.add_argument("--password", default=None, help="Reddit password (optional)")
    p.add_argument("--cooldown-min", type=float, default=2.5,
                   help="Min seconds to wait between scrolls (default 2.5)")
    p.add_argument("--cooldown-max", type=float, default=5.0,
                   help="Delay added between post fetches (default 5.0)")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # Windows async fix
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

    args   = parse_args()
    tname  = f"r/{args.target}" if args.target else "home"
    logger = setup_logging(tname)

    store = ProgressStore(tname, logger)

    # ── graceful shutdown ────────────────────────────────────────────────────
    def _shutdown(signum, frame):
        logger.info(
            f"[SIGNAL] Received signal {signum}. "
            f"Progress saved: {store.saved_count} posts in {store.output_path}"
        )
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    run_until = time.time() + args.hours * 3600
    end_time  = datetime.fromtimestamp(run_until)
    logger.info(
        f"[START] target={tname}  posts={args.posts}  "
        f"run_until={end_time:%Y-%m-%d %H:%M:%S}  "
        f"already_saved={store.saved_count}"
    )

    if store.saved_count >= args.posts:
        logger.info(
            f"[DONE] Target of {args.posts} posts already reached from previous run. "
            f"Output: {store.output_path}"
        )
        return

    # ── configure & run spider ───────────────────────────────────────────────
    settings = get_project_settings()
    settings.setdict(SCRAPY_SETTINGS)

    process = CrawlerProcess(settings)
    crawler = process.create_crawler(HumanRedditSpider)

    # Inject shared state into spider before crawl starts
    def spider_opened(spider):
        spider.store        = store
        spider.app_logger   = logger
        spider.run_until    = run_until
        spider.target_posts = args.posts
        spider.cooldown_min = args.cooldown_min
        spider.cooldown_max = args.cooldown_max

    crawler.signals.connect(spider_opened, signal=signals.spider_opened)

    process.crawl(
        crawler,
        target   = args.target,
        username = args.username,
        password = args.password,
    )
    process.start()

    logger.info(
        f"[END] Crawl finished. Total posts saved: {store.saved_count}. "
        f"Output: {store.output_path}"
    )


if __name__ == "__main__":
    main()
