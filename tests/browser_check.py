"""Headless browser check: loads the app, plays key stages, saves screenshots, fails on JS errors.
    python3 tests/browser_check.py [base_url]
"""
import sys, asyncio, pathlib
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
OUT = pathlib.Path(__file__).resolve().parent / "shots"; OUT.mkdir(exist_ok=True)

async def main():
    errs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        await pg.goto(BASE); await pg.wait_for_timeout(6500)
        await pg.screenshot(path=OUT / "01_open.png")
        await pg.evaluate("setK(0)"); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=OUT / "02_day1.png")
        await pg.evaluate("setK(2)"); await pg.click("#layers button[data-layer=persist]"); await pg.wait_for_timeout(2000)
        await pg.screenshot(path=OUT / "03_persist.png")
        await pg.click("#layers button[data-layer=persist]"); await pg.click(".tab[data-tab=evidence]"); await pg.wait_for_timeout(800)
        await pg.screenshot(path=OUT / "04_evidence.png")
        await pg.click("#layers button[data-layer=swipe]"); await pg.wait_for_timeout(3500)
        await pg.screenshot(path=OUT / "05_swipe.png")
        await pg.click("#layers button[data-layer=swipe]"); await pg.wait_for_timeout(500)
        await pg.fill("#askInput", "أي المستودعات المرهونة بقيت تحت الماء أكثر من ٥ أيام؟"); await pg.press("#askInput", "Enter")
        await pg.wait_for_timeout(4500)
        await pg.screenshot(path=OUT / "06_ask_ar.png")
        await pg.click(".tab[data-tab=impact]"); rows = await pg.query_selector_all("#queue .row")
        if rows:
            await rows[0].click(); await pg.wait_for_timeout(2500)
            await pg.screenshot(path=OUT / "07_loan.png")
            await pg.keyboard.press("Escape")
        await pg.click("#storyBtn"); await pg.wait_for_timeout(3000)
        await pg.screenshot(path=OUT / "08_story_alert.png")
        await pg.wait_for_timeout(9000)
        await pg.screenshot(path=OUT / "09_story_storm.png")
        await pg.click("#storyBtn"); await pg.close()
        mob = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mob.on("pageerror", lambda e: errs.append("mobile: " + str(e)))
        await mob.goto(BASE); await mob.wait_for_timeout(5000); await mob.screenshot(path=OUT / "10_mobile.png")
        await b.close()
    errs = [e for e in errs if "ERR_TUNNEL" not in e and "ERR_NAME" not in e and "ERR_INTERNET" not in e]  # offline sandbox: ion/fonts blocked
    print("JS errors:", errs or "none")
    sys.exit(1 if errs else 0)

asyncio.run(main())
