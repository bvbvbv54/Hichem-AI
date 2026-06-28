from __future__ import annotations

import asyncio
import hashlib
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter
from sqlalchemy import select

from configs.logging import get_logger
from configs.settings import settings
from database.session import async_session
from database.models.feature_cache import FeatureCache
from database.models.product_link import ProductLink
from database.models.asset import Asset
from database.models.job import Job
from services.translation_service import contains_chinese
from services.weight_learning import resolve_weights, log_correction_events
from database.models.learning_weight import LearningWeight

logger = get_logger(__name__)

# Cap concurrent image analysis to 2 workers (4 vCPU / 8 GB constraint)
_scoring_semaphore = asyncio.Semaphore(2)


def _image_hash(file_path: str) -> str:
    return hashlib.sha256(file_path.encode()).hexdigest()


def _center_score(img: Image.Image) -> float:
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    w, h = img.size
    px = list(edges.getdata())
    total = 0
    cx = cy = 0.0
    for y in range(h):
        row_start = y * w
        for x in range(w):
            val = px[row_start + x]
            if val > 30:
                total += val
                cx += x * val
                cy += y * val
    if total == 0:
        return 0.5
    cx /= total
    cy /= total
    center_x, center_y = w / 2.0, h / 2.0
    max_dist = math.sqrt(center_x ** 2 + center_y ** 2)
    dist = math.sqrt((cx - center_x) ** 2 + (cy - center_y) ** 2)
    return max(0.0, 1.0 - dist / max_dist)


def _chinese_score(img: Image.Image, alt_text: str = "") -> tuple[float, bool]:
    meta_score = 0.5 if contains_chinese(alt_text) else 0.0
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    w, h = img.size
    grid_size = 6
    bw = max(1, w // grid_size)
    bh = max(1, h // grid_size)
    dense_count = 0
    total_cells = grid_size * grid_size
    for r in range(grid_size):
        for c in range(grid_size):
            block = edges.crop((c * bw, r * bh, (c + 1) * bw, (r + 1) * bh))
            bp = list(block.getdata())
            edge_ratio = sum(1 for p in bp if p > 80) / len(bp) if bp else 0
            if edge_ratio > 0.08:
                dense_count += 1
    image_score = min(1.0, dense_count / total_cells * 2.0)
    score = max(meta_score, image_score)
    ocr_detected = score > 0.5
    return score, ocr_detected


def _quality_score(img: Image.Image) -> float:
    w, h = img.size
    res = math.sqrt(w * h)
    res_score = min(1.0, res / 1500.0)
    gray = img.convert("L")
    lap = gray.filter(
        ImageFilter.Kernel((3, 3), [0, -1, 0, -1, 4, -1, 0, -1, 0], scale=1)
    )
    lap_px = list(lap.getdata())
    if not lap_px:
        return 0.5
    mean = sum(lap_px) / len(lap_px)
    variance = sum((p - mean) ** 2 for p in lap_px) / len(lap_px)
    sharpness_score = min(1.0, variance / 2000.0)
    return 0.4 * res_score + 0.6 * sharpness_score


def _detail_score(img: Image.Image) -> float:
    gray = img.convert("L")
    w, h = img.size
    margin_x = max(1, int(w * 0.2))
    margin_y = max(1, int(h * 0.2))
    center_crop = gray.crop((margin_x, margin_y, w - margin_x, h - margin_y))
    edges = center_crop.filter(ImageFilter.FIND_EDGES)
    epx = list(edges.getdata())
    total = len(epx)
    if total == 0:
        return 0.0
    detail_pixels = sum(1 for p in epx if p > 50)
    density = detail_pixels / total
    mean = sum(epx) / total
    variance = sum((p - mean) ** 2 for p in epx) / total
    detail_density = min(1.0, density * 3.0)
    texture_richness = min(1.0, variance / 3000.0)
    return 0.5 * detail_density + 0.5 * texture_richness


async def _load_or_compute_features(
    asset_id: str, file_path: str, alt_text: str
) -> dict[str, Any] | None:
    img_hash = _image_hash(file_path)
    path = Path(file_path)
    if not path.exists():
        alt_path = Path(settings.storage_path) / file_path
        if alt_path.exists():
            path = alt_path
        else:
            logger.warning("feature_image_not_found", asset_id=asset_id, path=file_path)
            return None

    async with async_session() as session:
        existing = await session.execute(
            select(FeatureCache).where(FeatureCache.image_hash == img_hash)
        )
        cached = existing.scalar_one_or_none()
        if cached:
            logger.info("feature_cache_hit", asset_id=asset_id, hash=img_hash[:12])
            return {
                "center_score": cached.center_score or 0.0,
                "chinese_score": cached.chinese_score or 0.0,
                "quality_score": cached.quality_score or 0.0,
                "detail_score": cached.detail_score or 0.0,
                "ocr_detected": cached.ocr_detected or False,
            }

    logger.info("computing_features", asset_id=asset_id, hash=img_hash[:12])
    t0 = time.monotonic()
    try:
        with Image.open(str(path)) as img:
            # Downscale to 800px longest side for memory-bound analysis
            if max(img.width, img.height) > 800:
                ratio = 800.0 / max(img.width, img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            cs = _center_score(img)
            chs, ocr = _chinese_score(img, alt_text)
            qs = _quality_score(img)
            ds = _detail_score(img)
    except Exception as e:
        logger.warning("feature_compute_failed", asset_id=asset_id, error=str(e))
        return None

    elapsed = time.monotonic() - t0
    logger.info("features_computed", asset_id=asset_id, elapsed_ms=round(elapsed * 1000, 1),
                center=round(cs, 3), chinese=round(chs, 3),
                quality=round(qs, 3), detail=round(ds, 3))

    import uuid
    async with async_session() as session:
        fc = FeatureCache(
            id=str(uuid.uuid4()),
            image_hash=img_hash,
            center_score=cs,
            chinese_score=chs,
            quality_score=qs,
            detail_score=ds,
            ocr_detected=ocr,
        )
        session.add(fc)
        await session.commit()

    return {
        "center_score": cs,
        "chinese_score": chs,
        "quality_score": qs,
        "detail_score": ds,
        "ocr_detected": ocr,
    }


async def score_product_images(
    product_id: str, reference_count: int = 3,
    user_id: str = "", project_id: str = "",
) -> dict[str, Any]:
    reference_count = max(3, min(5, reference_count))

    async with async_session() as session:
        result = await session.execute(
            select(ProductLink).where(ProductLink.id == product_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            return {"error": "Product not found"}

        jobs_result = await session.execute(
            select(Job).where(Job.meta["url"].as_string() == link.url).order_by(Job.created_at.desc())
        )
        all_jobs = list(jobs_result.scalars().all())

        if link.job_id:
            direct = await session.execute(select(Job).where(Job.id == link.job_id))
            dj = direct.scalar_one_or_none()
            if dj and dj.id not in {j.id for j in all_jobs}:
                all_jobs.append(dj)

        seen_paths: set[str] = set()
        assets_for_scoring: list[dict] = []

        for job in all_jobs:
            assets_result = await session.execute(
                select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
            )
            for asset in assets_result.scalars().all():
                fp = asset.file_path or ""
                if fp in seen_paths:
                    continue
                seen_paths.add(fp)
                meta = asset.meta or {}
                is_scraped = meta.get("type") == "scraped" or "scraped" in (asset.filename or "")
                if is_scraped:
                    assets_for_scoring.append({
                        "asset_id": asset.id,
                        "file_path": fp,
                        "filename": asset.filename,
                        "alt_text": asset.alt_text or "",
                        "width": asset.width or 0,
                        "height": asset.height or 0,
                    })

            job_meta = job.meta or {}
            saved = job_meta.get("saved_assets", [])
            for sp in saved:
                if sp in seen_paths:
                    continue
                seen_paths.add(sp)
                assets_for_scoring.append({
                    "asset_id": hashlib.sha256(sp.encode()).hexdigest()[:12],
                    "file_path": sp,
                    "filename": Path(sp).name,
                    "alt_text": "",
                    "width": 0,
                    "height": 0,
                })

    weights = await resolve_weights(user_id=user_id, project_id=project_id)

    scored: list[dict] = []
    async with _scoring_semaphore:
        for item in assets_for_scoring:
            features = await _load_or_compute_features(
                item["asset_id"], item["file_path"], item["alt_text"]
            )
            if features is None:
                continue
            image_score = (
                weights["center"] * features["center_score"]
                + weights["chinese"] * features["chinese_score"]
                + weights["quality"] * features["quality_score"]
                + weights["detail"] * features["detail_score"]
            )
            scored.append({
                "asset_id": item["asset_id"],
                "filename": item["filename"],
                "file_path": item["file_path"],
                "width": item["width"],
                "height": item["height"],
                "scores": {
                    "center": round(features["center_score"], 4),
                    "chinese": round(features["chinese_score"], 4),
                    "quality": round(features["quality_score"], 4),
                    "detail": round(features["detail_score"], 4),
                },
                "image_score": round(image_score, 4),
            })

    scored.sort(key=lambda x: x["image_score"], reverse=True)

    # Confidence: score separation between Nth and (N+1)th candidate
    if len(scored) > reference_count:
        min_gap = scored[reference_count - 1]["image_score"] - scored[reference_count]["image_score"]
    else:
        min_gap = 0.5
    gap_confidence = max(0.0, min(100.0, min_gap * 200.0))

    # History boost: event count from active LearningWeight scope
    history_boost = 0.0
    try:
        async with async_session() as session:
            for sid, stype in [
                (user_id, "user") if user_id else None,
                (project_id, "project") if project_id else None,
                ("global", "global"),
            ]:
                if sid is None:
                    continue
                r = await session.execute(
                    select(LearningWeight).where(
                        LearningWeight.scope_id == sid,
                        LearningWeight.scope_type == stype,
                    )
                )
                lw = r.scalar_one_or_none()
                if lw and (lw.event_count or 0) >= 3:
                    ec = lw.event_count or 0
                    history_boost = min(10.0, ec * 0.5)
                    break
    except Exception:
        pass

    confidence = min(100.0, gap_confidence + history_boost)

    selected_ids = {s["asset_id"] for s in scored[:reference_count]}
    for s in scored:
        s["auto_selected"] = s["asset_id"] in selected_ids

    return {
        "product_id": product_id,
        "product_name": link.product_name or "",
        "reference_count": reference_count,
        "images": scored,
        "weights": weights,
        "confidence": round(confidence, 1),
        "auto_select_ids": [s["asset_id"] for s in scored[:reference_count]],
    }


async def save_reference_selection(
    product_id: str,
    selected_asset_ids: list[str],
    auto_select_suggested_ids: list[str],
    user_id: str = "",
    project_id: str = "",
    approved: bool = False,
) -> dict[str, Any]:
    logger.info("saving_reference_selection", product_id=product_id,
                selected=len(selected_asset_ids), auto_suggested=len(auto_select_suggested_ids),
                approved=approved)
    async with async_session() as session:
        result = await session.execute(
            select(ProductLink).where(ProductLink.id == product_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            return {"error": "Product not found"}

        meta = dict(link.meta or {})
        meta["reference_selected_ids"] = selected_asset_ids
        meta["reference_auto_suggested_ids"] = auto_select_suggested_ids
        meta["reference_updated_at"] = datetime.utcnow().isoformat()
        if approved:
            meta["reference_approved"] = True
            meta["reference_approved_at"] = datetime.utcnow().isoformat()
            meta["reference_locked"] = True
        link.meta = meta
        await session.commit()

    correction_result = await log_correction_events(
        product_id=product_id,
        selected_asset_ids=selected_asset_ids,
        auto_select_suggested_ids=auto_select_suggested_ids,
        user_id=user_id,
        project_id=project_id,
    )

    return {
        "status": "saved",
        "product_id": product_id,
        "selected_count": len(selected_asset_ids),
        "approved": approved,
        "corrections": correction_result,
    }
