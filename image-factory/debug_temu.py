import asyncio
from playwright.async_api import async_playwright


async def main():
    url = "https://www.temu.com/uk/20000mah-portable-solar-power-bank-portable-solar-mobile-phone-charger-camping-external-battery-charger-for-mobile-phones-2-usb-led-flashlights-with-compass-for-outdoor-activities-g-601100567187506.html"
    ap = await async_playwright().__aenter__()
    b = await ap.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = await b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0")
    p = await ctx.new_page()

    api_calls = []
    async def log_req(req):
        u = req.url
        if "api" in u or "json" in u or "goods" in u:
            api_calls.append(u[:400])
    p.on("request", log_req)

    api_responses = []
    async def log_resp(resp):
        u = resp.url
        if "api" in u and resp.ok:
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    data = await resp.json()
                    api_responses.append((u[:300], json.dumps(data)[:500]))
            except:
                pass
    p.on("response", log_resp)

    await p.goto(url, wait_until="domcontentloaded", timeout=30000)
    await p.wait_for_timeout(15000)

    print("=== API CALLS ===")
    for u in api_calls:
        print(f"  {u}")

    print(f"\n=== API RESPONSES ({len(api_responses)}) ===")
    for u, d in api_responses:
        print(f"  {u}")
        print(f"  DATA: {d[:300]}")
        print()

    imgs = await p.evaluate(
        "() => Array.from(document.querySelectorAll('img')).map(i => ({src: i.src, w: i.naturalWidth, h: i.naturalHeight}))"
    )
    print(f"\n=== IMAGES (>100px) ===")
    for i in imgs:
        if i["w"] > 100 and i["h"] > 100:
            print(f'  {i["w"]}x{i["h"]} {i["src"][:200]}')

    # also look for gallery containers
    gallery = await p.evaluate(
        "() => Array.from(document.querySelectorAll('[class*=gallery], [class*=preview], [class*=swiper]')).map(el => el.className)"
    )
    print(f"\n=== GALLERY CONTAINERS ===")
    for g in gallery[:20]:
        print(f"  {g}")

    await ctx.close()
    await b.close()
    await ap.__aexit__(None, None, None)


if __name__ == "__main__":
    import json
    asyncio.run(main())
