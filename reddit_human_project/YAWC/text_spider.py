"""
YAWC Text Spider v1 — Multi-Platform Text Research Spider
Searches Reddit (primary), StackOverflow (code/tech queries), and Quora (opinion queries).

Platform selection is query-driven:
  - Contains code keywords → StackOverflow
  - Contains opinion/experience keywords → Quora added to mix
  - Default → Reddit only

This is the evolved version of the original reddit_spider.py.
All existing Reddit scraping logic is preserved.

Output fields per item (unified across platforms):
  url        — canonical post URL
  title      — post/question title
  body       — text content (post body, answer snippet, etc.)
  subreddit  — subreddit name (Reddit) or platform name (SO/Quora)
  score      — upvotes / vote count (as string)
  platform   — "Reddit" | "StackOverflow" | "Quora"
"""

import asyncio
import scrapy
import os
import json
from scrapy_playwright.page import PageMethod
from dotenv import load_dotenv

load_dotenv()

# ─── LLM Setup for Query Refinement ───────────────────────────────────────────
GEMINI_KEY    = os.getenv("GEMINI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER  = os.getenv("LLM_PROVIDER", "gemini").lower()

if LLM_PROVIDER == "gemini" and GEMINI_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    _gemini_model = genai.GenerativeModel("gemini-2.5-flash")

elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
    import anthropic as _anthropic
    _anthropic_client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def _refine_search_query_blocking(query: str, platform: str) -> str:
    """
    Use LLM to refine search query for better results on specific platforms.
    """
    platform_prompts = {
        "reddit": f"""Given this user query: "{query}"
        
        Generate a better search query optimized for Reddit. Reddit works best with:
        - Specific keywords and phrases
        - Common abbreviations and slang
        - Question format or problem statements
        - Remove unnecessary words, focus on core issue
        
        Return ONLY the refined search query, no explanation.""",
        
        "stackoverflow": f"""Given this user query: "{query}"
        
        Generate a better search query optimized for Stack Overflow. Stack Overflow works best with:
        - Technical error messages
        - Specific technology names and versions
        - Exact code snippets or function names
        - Programming language + framework + error
        
        Return ONLY the refined search query, no explanation.""",
        
        "quora": f"""Given this user query: "{query}"
        
        Generate a better search query optimized for Quora. Quora works best with:
        - Complete questions starting with What/How/Why/Is/Are
        - Personal experience and advice seeking
        - Career and opinion-based questions
        
        Return ONLY the refined search query, no explanation."""
    }
    
    prompt = platform_prompts.get(platform, platform_prompts["reddit"])
    
    try:
        if LLM_PROVIDER == "gemini" and GEMINI_KEY:
            response = _gemini_model.generate_content(prompt)
            refined = response.text.strip()
        elif LLM_PROVIDER == "anthropic" and ANTHROPIC_KEY:
            message = _anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            refined = message.content[0].text.strip()
        else:
            return query  # Fallback to original query
        
        # Clean up the response
        refined = refined.strip('"').strip("'")
        return refined if refined else query
        
    except Exception as e:
        print(f"[YAWC-TEXT] Query refinement failed: {e}. Using original query.")
        return query


async def refine_search_query(query: str, platform: str) -> str:
    """Async wrapper for query refinement."""
    from concurrent.futures import ThreadPoolExecutor
    import asyncio
    
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    
    refined = await loop.run_in_executor(
        executor, _refine_search_query_blocking, query, platform
    )
    
    print(f"[YAWC-TEXT] Refined '{query}' → '{refined}' for {platform}")
    return refined


CODE_KEYWORDS = {
    "python", "javascript", "typescript", "rust", "go", "golang", "java",
    "c++", "cpp", "c#", "csharp", "swift", "kotlin", "react", "vue",
    "angular", "node", "nodejs", "django", "fastapi", "flask", "rails",
    "docker", "kubernetes", "k8s", "sql", "postgres", "mysql", "mongodb",
    "redis", "aws", "gcp", "azure", "git", "github", "api", "rest",
    "graphql", "css", "html", "bash", "shell", "linux", "error",
    "exception", "bug", "debug", "fix", "code", "function", "class",
    "algorithm", "recursion", "regex", "import", "install", "npm", "pip",
}

OPINION_KEYWORDS = {
    "should i", "is it worth", "experience with", "thoughts on",
    "recommend", "advice", "career", "salary", "interview", "better",
    "vs", "versus", "difference between", "best way to", "how do people",
}


def _is_code_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in CODE_KEYWORDS)


def _is_opinion_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in OPINION_KEYWORDS)


def should_abort_request(req):
    """Block non-essential resources. Allow images only for SO/Quora avatars (not needed)."""
    return req.resource_type in {
        "image", "media", "font", "stylesheet",
        "websocket", "eventsource", "manifest",
    }


class TextSpider(scrapy.Spider):
    name = "text_spider"

    custom_settings = {
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
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ],
        },
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
        "CONCURRENT_REQUESTS": 8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1,
        "AUTOTHROTTLE_MAX_DELAY": 3,
        "RETRY_TIMES": 2,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, query: str = "", k: str = "8", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query     = query
        self.k         = int(k)
        self.is_code   = _is_code_query(query)
        self.is_opinion = _is_opinion_query(query)

        # Refine queries for each platform
        reddit_query = _refine_search_query_blocking(query, "reddit")
        so_query = _refine_search_query_blocking(query, "stackoverflow") if self.is_code else query
        quora_query = _refine_search_query_blocking(query, "quora") if self.is_opinion else query

        # Always scrape Reddit
        self.reddit_url = (
            f"https://www.reddit.com/search/?q={reddit_query.replace(' ', '+')}&type=link&sort=relevance"
        )

        # StackOverflow for code queries
        self.so_url = (
            f"https://stackoverflow.com/search?q={so_query.replace(' ', '+')}&tab=votes"
            if self.is_code else None
        )

        # Quora for opinion queries — not always scraped to avoid rate limits
        self.quora_url = (
            f"https://www.quora.com/search?q={quora_query.replace(' ', '+')}"
            if self.is_opinion and not self.is_code else None
        )

        self.logger.info(
            f"[YAWC-TEXT] Original: '{query}' | Reddit: '{reddit_query}' | SO: '{so_query}' | Quora: '{quora_query}'"
        )

    # ── Step 1: Start all search requests in parallel ─────────────────────────
    def start_requests(self):
        # Always start with Reddit
        yield scrapy.Request(
            url=self.reddit_url,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_timeout", 8000),
                ],
                "source": "reddit",
            },
            callback=self.parse_reddit_search,
            errback=self.handle_error,
        )

        # Add StackOverflow for code queries
        if self.so_url:
            yield scrapy.Request(
                url=self.so_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 6000),
                    ],
                    "source": "stackoverflow",
                },
                callback=self.parse_stackoverflow,
                errback=self.handle_error,
            )

        # Add Quora for opinion queries
        if self.quora_url:
            yield scrapy.Request(
                url=self.quora_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 8000),
                    ],
                    "source": "quora",
                },
                callback=self.parse_quora,
                errback=self.handle_error,
            )

    # ── Reddit: parse search results then fetch posts in parallel ─────────────
    async def parse_reddit_search(self, response):
        page = response.meta.get("playwright_page")

        # Try multiple selector strategies for Reddit
        permalinks = await page.evaluate("""
            () => {
                // Strategy 1: Modern Reddit with shreddit-post
                let posts = Array.from(document.querySelectorAll('shreddit-post'))
                                 .map(p => p.getAttribute('permalink'));
                
                // Strategy 2: Old Reddit or fallback
                if (posts.length === 0) {
                    posts = Array.from(document.querySelectorAll('a[href*="/comments/"], a[href*="/r/"]'))
                                 .map(a => a.getAttribute('href'))
                                 .filter(href => href && (href.includes('/comments/') || href.includes('/r/')))
                                 .filter(href => !href.includes('/comments/') || href.split('/').length >= 6);
                }
                
                // Strategy 3: Search result posts
                if (posts.length === 0) {
                    posts = Array.from(document.querySelectorAll('[data-testid="post-container"] a, .Post a'))
                                 .map(a => a.getAttribute('href'))
                                 .filter(href => href && href.includes('/comments/'));
                }
                
                return [...new Set(posts)].filter(Boolean);
            }
        """)

        await page.close()

        if not permalinks:
            self.logger.warning("[YAWC-TEXT] No Reddit post links found.")
            return

        # Allocate k slots to Reddit — fewer if SO/Quora also requested
        reddit_k = self.k if not (self.so_url or self.quora_url) else max(4, self.k // 2)

        self.logger.info(
            f"[YAWC-TEXT] Found {len(permalinks)} Reddit posts. "
            f"Fetching top {reddit_k} in parallel."
        )

        for link in permalinks[:reddit_k]:
            full_url = response.urljoin(link)
            yield scrapy.Request(
                url=full_url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 5000),
                    ],
                    "source": "reddit",
                },
                callback=self.parse_reddit_post,
                errback=self.handle_error,
            )

    async def parse_reddit_post(self, response):
        page = response.meta.get("playwright_page")

        # Extract data with multiple fallback strategies
        data = await page.evaluate("""
            () => {
                // Strategy 1: Modern Reddit
                let title = document.querySelector('h1, [slot="title"], shreddit-post [slot="title"]')?.textContent?.trim();
                let subreddit = document.querySelector('shreddit-post')?.getAttribute('subreddit-prefixed-name') || 
                               document.querySelector('[data-testid="subreddit-name"], .subreddit-name')?.textContent?.trim();
                let score = document.querySelector('shreddit-post')?.getAttribute('score') || 
                           document.querySelector('[data-testid="upvote-count"], .score')?.textContent?.trim() || '0';
                
                // Strategy 2: Post content
                let bodyParts = [];
                let bodySelectors = [
                    'shreddit-post [slot="text-body"] p',
                    '[data-testid="post-content"] p',
                    '.Post .usertext-body p',
                    '[id$="-post-rtjson-content"] p',
                    '.md p'
                ];
                
                for (let selector of bodySelectors) {
                    let elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        bodyParts = Array.from(elements).map(p => p.textContent?.trim()).filter(Boolean);
                        break;
                    }
                }
                
                return {
                    title: title || 'Untitled',
                    subreddit: subreddit || 'r/unknown',
                    score: score,
                    body: bodyParts.join(' ').trim()
                };
            }
        """)

        if page:
            try:
                await page.close()
            except Exception:
                pass

        yield {
            "url":      response.url,
            "title":    data.get("title", "Untitled"),
            "body":     data.get("body", ""),
            "subreddit": data.get("subreddit", "r/unknown"),
            "score":    data.get("score", "0"),
            "platform": "Reddit",
        }

    # ── StackOverflow: parse search results and top answer snippets ───────────
    async def parse_stackoverflow(self, response):
        page = response.meta.get("playwright_page")

        questions = await page.evaluate(f"""
            () => {{
                const results = [];
                // Multiple selector strategies for SO search results
                const itemSelectors = [
                    '.js-search-results .s-post-summary',
                    '.search-result',
                    '.question-summary',
                    '[data-post-type-id="1"]',
                    '.s-card'
                ];
                
                let items = [];
                for (let selector of itemSelectors) {{
                    items = document.querySelectorAll(selector);
                    if (items.length > 0) break;
                }}
                
                for (const item of items) {{
                    if (results.length >= {max(2, self.k // 3)}) break;

                    // Title and URL
                    const titleEl = item.querySelector('h3 a, .s-link, a.question-hyperlink, .question-title a');
                    const title = titleEl?.textContent?.trim() || '';
                    const href = titleEl?.getAttribute('href') || '';
                    const url = href.startsWith('http') ? href : 'https://stackoverflow.com' + href;

                    // Body/excerpt
                    const excerptEl = item.querySelector('.s-post-summary--content-excerpt, .excerpt, .summary');
                    const body = excerptEl?.textContent?.trim() || '';

                    // Score/votes
                    const voteEl = item.querySelector('.s-post-summary--stats-item__emphasized .s-post-summary--stats-item-number, .vote-count-post, .votes .mini-counts');
                    const score = voteEl?.textContent?.trim() || '0';

                    if (title && url) {{
                        results.push({{ title, url, body, score }});
                    }}
                }}
                return results;
            }}
        """)

        await page.close()

        for q in questions:
            yield {
                "url":      q.get("url", ""),
                "title":    q.get("title", "").strip(),
                "body":     q.get("body", "").strip(),
                "subreddit": "stackoverflow",
                "score":    q.get("score", "0"),
                "platform": "StackOverflow",
            }

    # ── Quora: parse search results for question snippets ─────────────────────
    async def parse_quora(self, response):
        page = response.meta.get("playwright_page")

        questions = await page.evaluate(f"""
            () => {{
                const results = [];
                // Multiple strategies for Quora search results
                const linkSelectors = [
                    'a.q_link',
                    '[class*="question_link"]',
                    'a[href*="/What"]',
                    'a[href*="/How"]', 
                    'a[href*="/Why"]',
                    'a[href*="/Is"]',
                    'a[href*="/Are"]',
                    '[data-testid="search_result"] a',
                    '.question_link'
                ];
                
                const seen = new Set();
                let allLinks = [];
                
                for (let selector of linkSelectors) {{
                    const links = document.querySelectorAll(selector);
                    allLinks.push(...Array.from(links));
                }}
                
                for (const link of allLinks) {{
                    if (results.length >= {max(2, self.k // 4)}) break;

                    const href = link.getAttribute('href') || '';
                    const url = href.startsWith('http') ? href : 'https://www.quora.com' + href;
                    const title = link.textContent?.trim() || '';

                    if (!title || title.length < 10 || seen.has(url)) continue;
                    seen.add(url);

                    // Try to grab associated answer snippet
                    const parent = link.closest('[class*="question"]') || link.closest('[data-testid*="result"]') || link.parentElement;
                    const snippetSelectors = [
                        '[class*="answer"]',
                        '[class*="excerpt"]', 
                        '[class*="content"]',
                        '.ExpandedAnswer'
                    ];
                    
                    let body = '';
                    for (let sel of snippetSelectors) {{
                        const snippet = parent?.querySelector(sel);
                        if (snippet) {{
                            body = snippet.textContent?.trim() || '';
                            if (body.length > 20) break;
                        }}
                    }}

                    results.push({{ title, url, body }});
                }}
                return results;
            }}
        """)

        await page.close()

        for q in questions:
            yield {
                "url":      q.get("url", ""),
                "title":    q.get("title", "").strip(),
                "body":     q.get("body", "").strip(),
                "subreddit": "quora",
                "score":    "0",
                "platform": "Quora",
            }

    async def handle_error(self, failure):
        self.logger.warning(f"[YAWC-TEXT] ✗ Failed: {failure.request.url}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass
