import asyncio, httpx, re, json

async def test():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.1688.com/",
    }
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        # Get homepage cookies
        await c.get("https://www.1688.com/", headers=headers)
        
        # Try mobile page
        mobile_url = "https://m.1688.com/offer/830041356277.html"
        try:
            r1 = await c.get(mobile_url, headers={**headers, "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"})
            print(f"Mobile page: {r1.status_code} Len: {len(r1.text)}")
            imgs = re.findall(r'https?://[^"\'\\s]+?\.(?:jpg|jpeg|png|webp)[^"\'\\s]*', r1.text)
            for u in imgs[:20]:
                print(f"  {u[:250]}")
        except Exception as e:
            print(f"Mobile page error: {e}")
        
        # Try 1688 offer JSON API (used by the mobile app)
        api_url = "https://detail.1688.com/offer/830041356277.html?callback=jsonp"
        try:
            r2 = await c.get(api_url, headers=headers)
            print(f"\nJSONP API: {r2.status_code} Len: {len(r2.text)}")
            print(r2.text[:1000])
        except Exception as e:
            print(f"JSONP API error: {e}")
        
        # Try the ajax API endpoint
        ajax_url = "https://detail.1688.com/offer/830041356277.html?spm=a260k.home2025.recommendpart.11&ajax=1"
        r3 = await c.get(ajax_url, headers=headers)
        print(f"\nAjax API: {r3.status_code} Len: {len(r3.text)}")
        if r3.status_code == 200 and len(r3.text) > 1000:
            imgs = re.findall(r'https?://[^"\'\\s]+?\.(?:jpg|jpeg|png|webp)[^"\'\\s]*', r3.text)
            for u in imgs[:20]:
                print(f"  {u[:250]}")
        
        # Try the offer detail query with headers that bypass security
        query_url = "https://offer.1688.com/offer/offerDetail.htm?offerId=830041356277&userType=0&memberId=b2b-2302089204969"
        r4 = await c.get(query_url, headers=headers)
        print(f"\nOffer query: {r4.status_code} Len: {len(r4.text)}")
        imgs = re.findall(r'https?://[^"\'\\s]+?\.(?:jpg|jpeg|png|webp)[^"\'\\s]*', r4.text)
        for u in imgs[:20]:
            print(f"  {u[:250]}")
        
        # 1688 stores images as: https://cbu01.alicdn.com/img/.../...jpg
        # The offerId maps to image IDs. Try the offer API
        api_url5 = f"https://api.1688.com/offer/queryOfferDetail.json?offerId=830041356277"
        r5 = await c.get(api_url5, headers=headers)
        print(f"\nAPI 1688: {r5.status_code} Len: {len(r5.text)}")
        if r5.status_code == 200:
            print(r5.text[:1500])

asyncio.run(test())
