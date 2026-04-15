#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════════════════════
# benchmark.py  –  YAWC  |  Headless vs Headful Crawler Comparison
# Fixed: Reddit selector, Twitter wait, Quora cookie auth, Windows event loop
# ══════════════════════════════════════════════════════════════════════════════

import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass, field

import psutil
from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext, Page

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_ITEMS  = 50
MAX_SCROLLS   = 15
SCROLL_DELTA  = 2500
SCROLL_PAUSE  = 2500       # ms – Reddit/Quora need time to hydrate
PAGE_TIMEOUT  = 60_000
INITIAL_WAIT  = 4_000      # ms after DOMContentLoaded before we start counting

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Platform definitions ──────────────────────────────────────────────────────

@dataclass
class Platform:
    name:     str
    url:      str
    # JS expression that returns a count integer
    js_count: str
    auth_note: str = "Anonymous"
    cookies:   list = field(default_factory=list)
    pre_scroll_js: str = ""


def _build_targets() -> list[Platform]:
    # ── Twitter cookies ────────────────────────────────────────────────────
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
    ct0_token  = os.getenv("TWITTER_CT0_TOKEN",  "").strip()
    twitter_cookies = []
    if auth_token:
        for domain in [".twitter.com", ".x.com"]:
            twitter_cookies.append({
                "name": "auth_token", "value": auth_token,
                "domain": domain, "path": "/", "secure": True, "httpOnly": True,
                "sameSite": "None",
            })
    if ct0_token:
        for domain in [".twitter.com", ".x.com"]:
            twitter_cookies.append({
                "name": "ct0", "value": ct0_token,
                "domain": domain, "path": "/", "secure": True,
                "sameSite": "None",
            })

    # ── Quora cookie ───────────────────────────────────────────────────────
    # HOW TO GET:
    #   1. Log in to quora.com in Chrome
    #   2. F12 → Application → Cookies → https://www.quora.com
    #   3. Copy the value of the "m-b" cookie
    #   4. Set QUORA_M_B=<value> in your .env
    quora_m_b = os.getenv("QUORA_M_B", "").strip()
    quora_cookies = []
    if quora_m_b:
        quora_cookies.append({
            "name": "m-b", "value": quora_m_b,
            "domain": ".quora.com", "path": "/", "secure": True,
        })

    return [
        # ── Reddit ────────────────────────────────────────────────────────
        # Anonymous scraping works. The selector varies:
        #   - Logged-in new Reddit:  shreddit-post (web component)
        #   - Anonymous new Reddit:  [data-testid="post-container"] or <article>
        # We evaluate JS that tries ALL variants and returns the max.
        Platform(
            name      = "Reddit",
            url       = "https://www.reddit.com/",
            js_count  = """
                (function() {
                    const counts = [
                        document.querySelectorAll('[data-testid="post-container"]').length,
                        document.querySelectorAll('article').length,
                        document.querySelectorAll('shreddit-post').length,
                        document.querySelectorAll('[data-fullname]').length,
                        document.querySelectorAll('div[data-click-id="body"]').length,
                    ];
                    return Math.max(...counts);
                })()
            """,
            auth_note = "Anonymous",
        ),

        # ── Quora ─────────────────────────────────────────────────────────
        # Quora HARD redirects unauthenticated users to the login page.
        # The m-b session cookie is required.
        Platform(
            name      = "Quora",
            url       = "https://www.quora.com/",
            js_count  = """
                (function() {
                    const links = document.querySelectorAll(
                        'a[href*="/What"], a[href*="/How"], a[href*="/Why"], ' +
                        'a[href*="/Is-"], a[href*="/Are-"], a[href*="/Can-"], a[href*="/Should"]'
                    );
                    return Array.from(links).filter(l => {
                        const t = l.textContent.trim();
                        return t.length > 15 && !l.href.includes('#');
                    }).length;
                })()
            """,
            auth_note  = ("Cookie (QUORA_M_B)" if quora_m_b
                          else "⚠ No QUORA_M_B set → will be blocked"),
            cookies    = quora_cookies,
            pre_scroll_js = """
                const closeBtn = document.querySelector(
                    'button[aria-label="Close"], .q_close_button, [class*="modal"] button'
                );
                if (closeBtn) closeBtn.click();
            """,
        ),

        # ── Twitter / X ───────────────────────────────────────────────────
        Platform(
            name      = "Twitter",
            url       = "https://x.com/home",
            js_count  = 'document.querySelectorAll(\'[data-testid="tweet"]\').length',
            auth_note  = ("Cookie (TWITTER_AUTH_TOKEN)" if auth_token
                          else "⚠ No TWITTER_AUTH_TOKEN set → will be blocked"),
            cookies    = twitter_cookies,
        ),
    ]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class BenchResult:
    platform:     str
    mode:         str
    time_sec:     float = 0.0
    mem_delta_mb: float = 0.0
    items_found:  int   = 0
    blocked:      bool  = False
    screenshot:   str   = ""
    error:        str   = ""


# ── Core scrape ───────────────────────────────────────────────────────────────

async def run_scrape(platform: Platform, headless: bool) -> BenchResult:
    mode   = "Headless" if headless else "Headful"
    result = BenchResult(platform=platform.name, mode=mode)
    items_found = 0

    proc       = psutil.Process(os.getpid())
    mem_before = proc.memory_info().rss / (1024 * 1024)
    t_start    = time.perf_counter()

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                ],
            )

            ctx_opts: dict = {
                "user_agent": USER_AGENT,
                "viewport":   {"width": 1280, "height": 900},
                "locale":     "en-US",
                "timezone_id":"America/New_York",
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                    "DNT": "1",
                },
            }

            if platform.cookies:
                ctx_opts["storage_state"] = {
                    "cookies": platform.cookies,
                    "origins": [],
                }

            ctx: BrowserContext = await browser.new_context(**ctx_opts)

            # Strip WebDriver fingerprint
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
                window.chrome = { runtime: {} };
            """)

            page: Page = await ctx.new_page()

            async def _goto(url: str):
                try:
                    return await page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
                except Exception:
                    await page.wait_for_timeout(1_000)
                    return await page.goto(url, timeout=PAGE_TIMEOUT * 2, wait_until="domcontentloaded")

            try:
                if platform.name == "Twitter":
                    await _goto("https://x.com/home")
                    await page.wait_for_timeout(5_000)
                    try:
                        await page.mouse.move(100, 100)
                        await page.mouse.wheel(0, 500)
                    except Exception:
                        pass
                    if platform.url != "https://x.com/home":
                        await _goto(platform.url)
                else:
                    await _goto(platform.url)

                # ── Block / login-wall detection ──────────────────────────
                title       = (await page.title()).lower()
                current_url = page.url.lower()

                is_blocked = (
                    any(t in title for t in ["just a moment", "attention required", "captcha"])
                    or ("login" in current_url and platform.name != "Twitter")
                    or ("signin" in current_url)
                    or (platform.name == "Quora" and "/search" not in current_url)
                )

                if is_blocked:
                    result.blocked = True
                    result.error   = f"Login wall detected. URL: {page.url}"
                else:
                    await page.wait_for_timeout(INITIAL_WAIT)

                    # Pre-scroll action (modal dismiss etc.)
                    if platform.pre_scroll_js:
                        try:
                            await page.evaluate(platform.pre_scroll_js)
                            await page.wait_for_timeout(500)
                        except Exception:
                            pass

                    # Platform-specific waits
                    if platform.name == "Twitter":
                        try:
                            await page.wait_for_selector(
                                "[data-testid='tweet'], article",
                                timeout=40_000,
                                state="attached",
                            )
                        except Exception:
                            pass

                    elif platform.name == "Reddit":
                        await page.wait_for_selector(
                            "[data-testid='post-container'], article, shreddit-post",
                            timeout=10_000,
                            state="attached",
                        )

                    # ── Prevent Reddit auto-navigation during scrolling ──────
                    if platform.name == "Reddit":
                        try:
                            await page.evaluate("""
                                window.history.pushState = () => {};
                                window.location.assign = () => {};
                            """)
                        except Exception:
                            pass

                    await page.wait_for_timeout(2_000 + int(2_000 * random.random()))

                    async def _safe_evaluate(js_expr: str):
                        try:
                            return await page.evaluate(js_expr)
                        except Exception:
                            await page.wait_for_timeout(2_000)
                            try:
                                return await page.evaluate(js_expr)
                            except Exception:
                                return None

                    # ── Scroll loop ───────────────────────────────────────
                    prev_count  = 0
                    stall_count = 0

                    for _ in range(MAX_SCROLLS):
                        items_found = int(await _safe_evaluate(platform.js_count) or 0)

                        if items_found >= TARGET_ITEMS:
                            break

                        if items_found == prev_count:
                            stall_count += 1
                            if stall_count >= 4:
                                break
                        else:
                            stall_count = 0

                        prev_count = items_found
                        await page.mouse.wheel(0, SCROLL_DELTA)
                        await page.wait_for_timeout(SCROLL_PAUSE)

                    # Final read
                    items_found = int(await _safe_evaluate(platform.js_count) or 0)

            except Exception as exc:
                result.error = str(exc)[:150]

            # Debug screenshot
            if items_found == 0:
                path = f"debug_{platform.name}_{mode}.png"
                try:
                    await page.screenshot(path=path, full_page=False)
                    result.screenshot = path
                except Exception:
                    pass

            await browser.close()

    except Exception as exc:
        result.error = f"Launch error: {str(exc)[:100]}"

    t_end = time.perf_counter()
    result.time_sec     = round(t_end - t_start, 2)
    result.mem_delta_mb = round(max(0.0, proc.memory_info().rss / (1024 * 1024) - mem_before), 1)
    result.items_found  = items_found
    return result


# ── Status formatter ──────────────────────────────────────────────────────────

def _status(r: BenchResult) -> str:
    if r.blocked:
        return f"BLOCKED  ❌  {r.error}"
    if r.items_found > 0:
        return "SUCCESS  ✅"
    note = f"  [see {r.screenshot}]" if r.screenshot else ""
    err  = f"  {r.error}"           if r.error      else ""
    return f"FAILED   ⚠{note}{err}"


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_benchmark() -> None:
    targets = _build_targets()
    results: list[BenchResult] = []
    W = 115

    print()
    print("=" * W)
    print(f"{'YAWC BENCHMARK  ·  HEADLESS vs HEADFUL  ·  TARGET: ' + str(TARGET_ITEMS) + ' ITEMS':^{W}}")
    print("=" * W)
    print(f"  {'Platform':<10}  {'Mode':<10}  {'Auth':<40}  {'Time':>8}  {'RAM Δ':>9}  {'Items':>6}  Status")
    print("-" * W)

    for target in targets:
        for headless in [True, False]:
            mode = "Headless" if headless else "Headful"
            print(f"  → {target.name} [{mode}] running …", end="", flush=True)
            res = await run_scrape(target, headless)
            results.append(res)
            print(
                f"\r  {target.name:<10}  {mode:<10}  {target.auth_note:<40}  "
                f"{res.time_sec:>7.1f}s  +{res.mem_delta_mb:>5.1f}MB  "
                f"{res.items_found:>6}  {_status(res)}"
            )
            await asyncio.sleep(3)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * W)
    print(f"{'COMPARISON SUMMARY':^{W}}")
    print("=" * W)
    print(f"  {'Platform':<10}  {'HL Items':>9}  {'HF Items':>9}  {'HL Time':>9}  {'HF Time':>9}  {'HL RAM':>8}  {'HF RAM':>8}  Notes")
    print("-" * W)

    for pname in [t.name for t in targets]:
        hl = next((r for r in results if r.platform == pname and r.mode == "Headless"), None)
        hf = next((r for r in results if r.platform == pname and r.mode == "Headful"),  None)

        fi = lambda r: str(r.items_found) if r else "–"
        ft = lambda r: f"{r.time_sec:.1f}s" if r else "–"
        fm = lambda r: f"+{r.mem_delta_mb:.1f}MB" if r else "–"

        notes = []
        if hl and hf:
            if   hl.items_found > hf.items_found: notes.append("Headless collected more")
            elif hf.items_found > hl.items_found: notes.append("Headful collected more")
            else:                                  notes.append("Equal items")
            if   hl.time_sec < hf.time_sec:       notes.append("Headless faster")
            elif hf.time_sec < hl.time_sec:       notes.append("Headful faster")
            if   hl.mem_delta_mb < hf.mem_delta_mb: notes.append("Headless lighter RAM")
            elif hf.mem_delta_mb < hl.mem_delta_mb: notes.append("Headful lighter RAM")
        if hl and hl.blocked: notes.append("⚠ HL login-walled")
        if hf and hf.blocked: notes.append("⚠ HF login-walled")

        print(
            f"  {pname:<10}  {fi(hl):>9}  {fi(hf):>9}  {ft(hl):>9}  {ft(hf):>9}  "
            f"{fm(hl):>8}  {fm(hf):>8}  {' · '.join(notes)}"
        )

    print("=" * W)
    print()
    print("  ┌─ HOW TO FIX 0-ITEM FAILURES ──────────────────────────────────────────────────┐")
    print("  │                                                                                │")
    print("  │  REDDIT   Works anonymously. If 0 items, check the debug PNG screenshot.      │")
    print("  │                                                                                │")
    print("  │  TWITTER  1. Log into twitter.com/x.com in Chrome                             │")
    print("  │           2. F12 → Application → Cookies → .twitter.com                       │")
    print("  │           3. Copy 'auth_token' value → TWITTER_AUTH_TOKEN=... in .env         │")
    print("  │           4. Copy 'ct0' value        → TWITTER_CT0_TOKEN=...  in .env         │")
    print("  │                                                                                │")
    print("  │  QUORA    1. Log into quora.com in Chrome                                     │")
    print("  │           2. F12 → Application → Cookies → .quora.com                        │")
    print("  │           3. Copy 'm-b' cookie value → QUORA_M_B=... in .env                 │")
    print("  │                                                                                │")
    print("  └────────────────────────────────────────────────────────────────────────────────┘")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_benchmark())
