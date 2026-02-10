# settings.py

BOT_NAME = "reddit_human_project"

SPIDER_MODULES = ["reddit_human_project.spiders"]
NEWSPIDER_MODULE = "reddit_human_project.spiders"

# --- PLAYWRIGHT SETUP ---

# 1. Register Download Handlers
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# 2. Force Asyncio Reactor (Critical for Windows)
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# 3. Add Playwright Middleware
DOWNLOADER_MIDDLEWARES = {
    "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler": 543,
}

# 4. Browser Options
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": False,  # Keep False so you can see if it's actually loading
    "timeout": 60000,   # Increase to 60s for slow connections
}

# --- HUMAN BEHAVIOR & STEALTH ---

# Set a very common User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

# Reddit's robots.txt DISALLOWS /r/ paths for crawlers. Setting this to False is mandatory.
ROBOTSTXT_OBEY = False 

# Very conservative concurrency to avoid instant IP bans
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 5
RANDOMIZE_DOWNLOAD_DELAY = True

# --- LOGGING & EXPORT ---
LOG_LEVEL = "INFO"  # Change to "DEBUG" if it still closes instantly to see the exact error
FEED_EXPORT_ENCODING = "utf-8"
COOKIES_ENABLED = True

# --- AUTOTHROTTLE ---
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0