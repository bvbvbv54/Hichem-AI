import asyncio
from services.product_scraper.scraper import ProductScraper

async def test():
    scraper = ProductScraper()
    url = "https://detail.1688.com/offer/830041356277.html"
    result = await scraper.scrape_product_images(url, "/tmp/test_1688_output")
    print(f"Scraped {len(result)} images:")
    for r in result:
        print(f"  {r['original_url'][:100]} -> {r['filename']} ({r['file_size']} bytes)")

asyncio.run(test())
