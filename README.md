# Yet Another Social Crawler

![License](https://img.shields.io/badge/license--blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)

## Description

# Reddit Human Scraper (Scrapy + Playwright)

A robust, human-like asynchronous web scraper built with Scrapy and Playwright.  
This tool is designed to mimic real user behavior (smooth scrolling, waiting for content hydration) to scrape deep Reddit data, including post content and nested comments, without triggering immediate bot detection.

---

## 🚀 Features

- Human-Like Scrolling: Automatically scrolls through feeds to collect a target number of posts before scraping details.
- Shadow DOM Penetration: Uses Playwright's execution context to extract data from Reddit's modern shreddit elements.
- Dual Mode: Supports both Anonymous scraping and Authenticated scraping (Login support).
- Flexible Targeting: Can scrape the Home Feed, a specific Subreddit, or a User's post history.
- Persistent Context: Maintains session cookies/local storage during the crawl to access personalized feeds.

---

## 🛠 Installation & Setup

### 1. Prerequisites

Ensure you have Python 3.8+ installed.

### 2. Install Dependencies

Install Scrapy, the Playwright integration, and the Playwright browser binaries:

pip install scrapy scrapy-playwright
playwright install chromium

### 3. Project Configuration

Ensure your settings.py includes the following Playwright configurations:

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": False}

Set headless to True if you want background execution.

---

## 🏃 Usage Guide

Run the spider using the scrapy crawl command.  
You can control the behavior using arguments (-a flag=value).

---

### 1. Anonymous Scraping (No Login)

Scrape the global Home feed:

scrapy crawl reddit_human -o home_feed.json

Scrape a specific subreddit (e.g., r/developersIndia):

scrapy crawl reddit_human -a target=developersIndia -o dev_india.json

Scrape a specific number of posts (e.g., 100 posts):

scrapy crawl reddit_human -a target=python -a k=100 -o python_100.json

---

### 2. Authenticated Scraping (With Login)

Note:  
Use a burner account without 2FA for best results.

Scrape your personalized Home Feed:

scrapy crawl reddit_human -a username="YOUR_USER" -a password="YOUR_PASSWORD" -o my_feed.json

Scrape a specific Subreddit as a logged-in user:

scrapy crawl reddit_human -a target=developersIndia -a username="YOUR_USER" -a password="YOUR_PASSWORD" -o auth_dev_india.json

---

## ⚙ Arguments Reference

Argument    | Description                                                        | Default
----------- | ------------------------------------------------------------------ | ----------------
target      | The subreddit name (without r/) or leave empty for Home Feed      | None (Home Feed)
k           | Number of posts to scroll and collect before scraping details     | 50
username    | Reddit username for authentication                                 | None
password    | Reddit password for authentication                                 | None

---

## 📂 Output Structure

The scraper exports data to JSON with the following structure:

[
    {
        "url": "https://www.reddit.com/r/example/comments/...",
        "title": "Example Post Title",
        "body": [
            "This is the content of the post...",
            "More paragraphs..."
        ],
        "comments": [
            "First comment",
            "Second comment",
            "Reply to comment..."
        ]
    }
]

---

## ⚠ Troubleshooting

### 1. "Connection closed while reading from driver"

Cause:  
The browser was closed manually or crashed due to memory issues.

Fix:

- Ensure try/except blocks are around await page.close()
- Reduce concurrency in settings.py:

CONCURRENT_REQUESTS = 1

---

### 2. "ReactorNotRestartable" or Asyncio Errors

Cause:  
Windows-specific event loop issue.

Fix:  
Ensure this code block is at the top of your reddit_spider.py:

import asyncio
try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    pass

---

### 3. Login Fails

Cause:  
Reddit triggered CAPTCHA or 2FA request.

Fix:

- The script cannot bypass CAPTCHA
- Use an account that doesn’t trigger it
- Or switch to Anonymous mode

---

## ⚖ Disclaimer

- This tool is for educational and research purposes only.
- Respect Reddit's robots.txt (enable ROBOTSTXT_OBEY = True if required).
- Do not use this tool to spam or harass users.
- Be mindful of Reddit's Terms of Service.

---

## Table of Contents

- Installation
- Usage
- Contributing
- License
- Contact

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project  
2. Create your feature branch (git checkout -b feature/AmazingFeature)  
3. Commit your changes (git commit -m 'Add some AmazingFeature')  
4. Push to the branch (git push origin feature/AmazingFeature)  
5. Open a Pull Request  

---

## License

This project is licensed under the MIT License.  
See the LICENSE file for details.

---

## Contact

Aviral Saxena  

Project Link:  
https://github.com/aviralsaxena16/YARS.git
