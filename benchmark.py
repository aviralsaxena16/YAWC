import asyncio
import time
import psutil
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

TARGET_ITEMS = 50 # Reduced to 30 to avoid instant IP-bans during testing

TARGETS = [
    {
        "platform": "Reddit", 
        "url": "https://www.reddit.com/search/?q=best+mechanical+keyboard&type=link&sort=relevance", 
        "selector": "shreddit-post"
    },
    {
        "platform": "Quora", 
        "url": "https://www.quora.com/search?q=how+to+learn+python", 
        "selector": "div.q-box.qu-pt--medium, a.q_link"
    },
    {
        "platform": "Twitter", 
        "url": "https://twitter.com/search?q=Artificial+Intelligence&src=typed_query", 
        "selector": "[data-testid='tweet']"
    }
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

async def measure_scrape(playwright, target, is_headless):
    browser = await playwright.chromium.launch(
        headless=is_headless,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080}
    )
    
    # ── TWITTER AUTH ONLY ──
    if target["platform"] == "Twitter":
        auth_token = os.getenv("TWITTER_AUTH_TOKEN")
        if not auth_token:
            await browser.close()
            return {"time_sec": 0, "mem_mb": 0, "success": False, "items": 0, "blocked": True, "note": "No TWITTER_AUTH_TOKEN in .env"}
        
        await context.add_cookies([{
            "name": "auth_token", "value": auth_token, "domain": ".twitter.com", "path": "/", "secure": True
        }])

    page = await context.new_page()
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 * 1024)
    
    start_time = time.time()
    items_found = 0
    block_detected = False
    
    try:
        await page.goto(target["url"], timeout=20000, wait_until="domcontentloaded")
        
        # Check for CAPTCHAs
        page_title = await page.title()
        if "Just a moment" in page_title or "Attention Required" in page_title:
            block_detected = True
        else:
            await page.wait_for_timeout(3000)
            
            scroll_attempts = 0
            while items_found < TARGET_ITEMS and scroll_attempts < 10:
                
                # ── QUORA MODAL ASSASSIN ──
                # If Quora throws that login wall from your screenshot, this deletes it from the DOM
                if target["platform"] == "Quora":
                    await page.evaluate("""
                        const wall = document.querySelector('div[class*="signup_wall"]');
                        if (wall) wall.remove();
                        document.body.style.overflow = 'auto';
                    """)

                items_found = await page.locator(target["selector"]).count()
                
                if items_found >= TARGET_ITEMS:
                    break
                    
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1500)
                scroll_attempts += 1
                
    except Exception as e:
        pass 
        
    end_time = time.time()
    
    # Debug screenshots if it failed
    if items_found == 0 and not block_detected:
        mode_str = "Headless" if is_headless else "Headful"
        await page.screenshot(path=f"debug_{target['platform']}_{mode_str}.png")
        note = "See screenshot"
    else:
        note = ""
    
    mem_after = process.memory_info().rss / (1024 * 1024)
    mem_used = max(0, mem_after - mem_before)
    await browser.close()
    
    return {
        "time_sec": round(end_time - start_time, 2),
        "mem_mb": round(mem_used, 1),
        "success": items_found > 0 and not block_detected,
        "items": items_found,
        "blocked": block_detected,
        "note": note
    }

async def run_benchmark():
    print(f"\n{'='*90}")
    print(f"{'YAWC STRESS TEST: HEADLESS VS HEADFUL':^90}")
    print(f"{'='*90}")
    print(f"{'Platform':<10} | {'Mode':<10} | {'Time (s)':<8} | {'RAM Spike':<10} | {'Items':<6} | {'Status'}")
    print("-" * 90)
    
    async with async_playwright() as p:
        for target in TARGETS:
            for is_headless in [True, False]:
                mode_str = "Headless" if is_headless else "Headful"
                res = await measure_scrape(p, target, is_headless)
                
                if res["blocked"]:
                    status = "BLOCKED ❌"
                elif res["success"]:
                    status = "SUCCESS ✅"
                else:
                    status = f"FAILED ⚠️ {res['note']}"
                    
                print(f"{target['platform']:<10} | {mode_str:<10} | {res['time_sec']:<8} | +{res['mem_mb']:<6} MB | {res['items']:<6} | {status}")
                await asyncio.sleep(2)
    print(f"{'='*90}\n")

if __name__ == "__main__":
    asyncio.run(run_benchmark())