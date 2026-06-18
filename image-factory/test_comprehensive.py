import asyncio
import time
import json
from pathlib import Path
from urllib.parse import urlparse

from configs.logging import get_logger
from configs.settings import settings
from services.acquisition.pipeline import AcquisitionPipeline
from services.acquisition.models import AcquisitionJob

logger = get_logger("test_comprehensive")

# test URLs
URLS = [
    ("Temu", "https://www.temu.com/uk/20000mah-portable-solar-power-bank-portable-solar-mobile-phone-charger-camping-external-battery-charger-for-mobile-phones-2-usb-led-flashlights-with-compass-for-outdoor-activities-g-601100567187506.html?_oak_mp_inf=ELKgoI6q1ogBGiA4ZTdiMmQwMzM3OWI0Y2NkYTVjYmVlNzM5MDI5MmM3NCCjkNza7TM%3D&top_gallery_url=https%3A%2F%2Fimg.kwcdn.com%2Fproduct%2Fopen%2F3a20592f819a414f864c4fd0cc8fd158-goods.jpeg&spec_gallery_id=111578&refer_page_sn=10005&freesia_scene=1&_oak_freesia_scene=1&_oak_rec_ext_1=NDg5&_oak_gallery_order=931406589%2C469943681%2C387088334%2C676242769%2C1840534481&refer_page_el_sn=200024&ab_scene=1&enable_vqr=1&_x_sessn_id=14zwdrg3wc&refer_page_name=home&refer_page_id=10005_1781796373278_lv2b3ybhp3"),
    ("Taobao", "https://item.taobao.com/item.htm?spm=a21bo.jianhua%2Fa.201876.d8.5af92a89zEDjTA&id=1054156675589&scm=1007.40986.420852.528214_527788_537217_521582_526067_533297_528940_530923_532805_528109_545020_537488_546628_537987_547838_538037&pvid=b7f62c7a-08b7-4b39-95f0-3ed0246227f8&xxc=home_recommend&skuId=6096023388253&mi_id=aIpDnTOC-wlQlGeTZfxbkwuyl33fkjdF0XOm5_WQ5vVvAAtqBmLLIkCTzdsyK9je-i-Ql51KjRhx7niKvrZxGg&utparam=%7B%22abid%22%3A%22528214_527788_537217_521582_526067_533297_528940_530923_532805_528109_545020_537488_546628_537987_547838_538037%22%2C%22item_ctr%22%3A0%2C%22x_object_type%22%3A%22item%22%2C%22pc_pvid%22%3A%22b7f62c7a-08b7-4b39-95f0-3ed0246227f8%22%2C%22item_cvr%22%3A0%2C%22mix_group%22%3A%22%22%2C%22pc_scene%22%3A%2220001%22%2C%22item_ecpm%22%3A0%2C%22aplus_abtest%22%3A%22917c7d26f499d79fff22b52dccbcdd24%22%2C%22tpp_buckets%22%3A%2230986%23420852%23module%22%2C%22x_object_id%22%3A1054156675589%2C%22ab_info%22%3A%2230986%23420852%23-1%23%22%7D"),
    ("JD", "https://item.jd.com/100168336594.html?bbtf=1&spmTag=YTAxNzMuQmFiZWxfMDE5NjU3ODguQmFiZWwzXzIzNjQzMTA5MF8wLjMlNDAxNzgxNzk2ODU3NzUwJTIzMTc4MTc4ODc5MzgxMjE4ODczODYyODUlMjMxODcxMTgwNTIx"),
    ("Made-in-China", "https://xyfzgroup.en.made-in-china.com/product/YRHpqTXWachU/China-High-Quality-48V-Electric-Folding-Bicycle-350W-Motor-15-Climbing-40km-Range-for-Urban-Commute-and-Leisure.html"),
    ("DHgate", "https://www.dhgate.com/product/2026-spring-summer-new-design-men-business/1109528939.html?dspm=pcen.drt-4803.topdeal_fd-floor_1781774472829.3.HK21xfGHdzFlkIpPDTKk&resource_id=1109528939&d1_click_type="),
    ("Alibaba", "https://www.alibaba.com/product-detail/Personalized-LED-TV-Assembly-Conveyor-Line_60607930952.html?spm=a27aq.27095423.1978240560.3.78372277NDdjSm"),
    ("AliExpress", "https://ar.aliexpress.com/item/1005007357456579.html?spm=a2g0o.tm1000015517.d0.1.8b772ea6KP36jK&pvid=cfa0a64a-f566-46e2-aa19-ca79d4046a99&pdp_ext_f=%7B%22ship_from%22%3A%22CN%22%2C%22sku_id%22%3A%2212000058057798900%22%7D&scm=1007.39065.404442.0&scm-url=1007.39065.404442.0&scm_id=1007.39065.404442.0&pdp_npi=6%40dis%21TND%21TND+288.09%21TND+138.28%21%21%21663.64%21318.55%21%40210141f717817969446146228e5155%2112000058057798900%21gdf%21TN%21%21X%211%210%21n_tag%3A-29910%3Bd%3A1c5c2093%3Bm03_new_user%3A-29895&aecmd=true"),
    ("1688", "https://detail.1688.com/offer/807193010092.html?offerId=807193010092&spm=a260k.home2025.recommendpart.137"),
    ("Amazon", "https://www.amazon.com/Charging-Accessories-Compatible-Connections-Replacement-PC/dp/B0D7S7JTFR/ref=pd_sim_d_sccl_1_3/136-1464810-8380758?pd_rd_w=H4yWd&content-id=amzn1.sym.7c24b67e-6f48-4291-a1d6-24d3e6952d7a&pf_rd_p=7c24b67e-6f48-4291-a1d6-24d3e6952d7a&pf_rd_r=9M93CG8C136B30KN0FX4&pd_rd_wg=MdWsZ&pd_rd_r=37d377cd-b364-4c19-af38-f623391599d1&pd_rd_i=B0D7S7JTFR&th=1"),
]

OUTPUT_BASE = Path("/app/outputs/test_batch")
MAX_IMAGES = 5


async def test_single(pipeline: AcquisitionPipeline, name: str, url: str) -> dict:
    job = AcquisitionJob(
        job_id=f"test-{name.lower().replace(' ', '-')}-{int(time.time())}",
        url=url,
        max_images=MAX_IMAGES,
    )
    logger.info("=" * 60)
    logger.info("TESTING", name=name, url=url[:120])
    start = time.monotonic()
    result = await pipeline.run(job)
    elapsed = time.monotonic() - start
    logger.info("RESULT", name=name, success=result.success, images=len(result.image_paths), duration_ms=f"{elapsed*1000:.0f}")
    if result.success:
        for p in result.image_paths:
            logger.info("  IMAGE", path=p)
    else:
        logger.warning("  FAILURE", failure_type=str(result.failure_type), detail=result.failure_detail)
    logger.info("=" * 60)
    return {
        "name": name,
        "success": result.success,
        "images": len(result.image_paths),
        "image_paths": result.image_paths,
        "duration_ms": elapsed * 1000,
        "used_browser": result.required_browser,
        "failure_type": str(result.failure_type) if result.failure_type else None,
        "failure_detail": result.failure_detail,
        "page_title": result.page_title,
        "was_cached": result.was_cached,
    }


async def main():
    logger.info("COMPREHENSIVE TEST START", urls=len(URLS))
    pipeline = AcquisitionPipeline()
    results = []
    for name, url in URLS:
        try:
            r = await test_single(pipeline, name, url)
            results.append(r)
        except Exception as e:
            logger.error("TEST_CRASHED", name=name, error=str(e))
            results.append({"name": name, "success": False, "error": str(e), "images": 0})
    await pipeline.close()

    # summary
    passed = sum(1 for r in results if r["success"] and r["images"] > 0)
    total = len(results)
    logger.info("=" * 60)
    logger.info("SUMMARY", passed=f"{passed}/{total}")
    for r in results:
        status = "PASS" if r["success"] and r["images"] > 0 else "FAIL"
        img_count = r.get("images", 0) or 0
        dur = f"{r.get('duration_ms', 0):.0f}ms" if r.get("duration_ms") else "N/A"
        logger.info(f"  [{status}] {r['name']}: {img_count} images ({dur})")
    logger.info("=" * 60)

    # save results
    out = OUTPUT_BASE / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    logger.info("results_saved", path=str(out))


if __name__ == "__main__":
    asyncio.run(main())
