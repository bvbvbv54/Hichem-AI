import asyncio
import json
import re
from services.acquisition.browser_client import BrowserClient
from services.acquisition.image_extractor import extract_image_urls


async def main():
    url = "https://www.temu.com/uk/20000mah-portable-solar-power-bank-portable-solar-mobile-phone-charger-camping-external-battery-charger-for-mobile-phones-2-usb-led-flashlights-with-compass-for-outdoor-activities-g-601100567187506.html"

    bc = BrowserClient()
    html, api_images = await bc.fetch_page_with_api(url)
    print(f"HTML length: {len(html) if html else 0}")
    print(f"API images captured: {len(api_images)}")
    for u in api_images:
        print(f"  {u[:200]}")

    if html:
        # Check for window.__NUXT__ or similar
        for pat_name, pat in [
            ("window.__NUXT__", r"window\.__NUXT__\s*=\s*({.*?});"),
            ("window.__INITIAL_STATE__", r"window\.__INITIAL_STATE__\s*=\s*({.*?});"),
            ("window.__PRELOADED_STATE__", r"window\.__PRELOADED_STATE__\s*=\s*({.*?});"),
            ("window.goodsData", r"window\.goodsData\s*=\s*({.*?});"),
            ("window.productData", r"window\.productData\s*=\s*({.*?});"),
            ("window.INITIAL_STATE", r"window\.INITIAL_STATE\s*=\s*({.*?});"),
            ("window.__DATA__", r"window\.__DATA__\s*=\s*({.*?});"),
            ('"goods"', r'"goods"\s*:\s*({.*?})\s*[,}]'),
            ('"gallery"', r'"gallery"\s*:\s*(\[.*?\])\s*[,}]'),
            ('"images"', r'"images"\s*:\s*(\[.*?\])\s*[,}]'),
            ('"imageList"', r'"imageList"\s*:\s*(\[.*?\])\s*[,}]'),
            ('"itemImages"', r'"itemImages"\s*:\s*(\[.*?\])\s*[,}]'),
            ("hd_thumb", r'"hd_thumb_url"\s*:\s*"([^"]+)"'),
            ("galleryImgs", r'"galleryImgs"\s*:\s*(\[.*?\])\s*[,}]'),
        ]:
            m = re.search(pat, html, re.DOTALL)
            if m:
                try:
                    data = m.group(1)
                    print(f"\n=== {pat_name} FOUND ===")
                    print(f"  {data[:500]}")
                except Exception as e:
                    print(f"\n=== {pat_name} error: {e} ===")

        # Check images in gallery divs
        import re as re2
        kwcdn_urls = re2.findall(r'https?://[^"\'\\\s>]*kwcdn[^"\'\\\s>]*\.(?:jpg|jpeg|png|webp|avif)', html)
        if kwcdn_urls:
            print(f"\n=== KWCNDN URLs ({len(kwcdn_urls)}) ===")
            for u in set(kwcdn_urls):
                print(f"  {u}")

    await bc.close()


if __name__ == "__main__":
    asyncio.run(main())
