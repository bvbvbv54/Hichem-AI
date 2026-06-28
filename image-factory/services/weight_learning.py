from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, update

from configs.logging import get_logger
from database.session import async_session
from database.models.correction_event import CorrectionEvent
from database.models.learning_weight import LearningWeight
from database.models.feature_cache import FeatureCache
from database.models.asset import Asset

logger = get_logger(__name__)

FEATURE_KEYS = ["center", "chinese", "quality", "detail"]
DEFAULT_WEIGHTS = {"center": 0.30, "chinese": 0.30, "detail": 0.20, "quality": 0.20}
ADJUSTMENT_RATE = 0.02
MIN_WEIGHT = 0.01
SCOPE_THRESHOLD = 3


async def _get_image_features(asset_id: str) -> dict[str, float] | None:
    async with async_session() as session:
        result = await session.execute(
            select(FeatureCache).where(FeatureCache.image_hash == asset_id)
        )
        cached = result.scalar_one_or_none()
        if cached:
            return {
                "center": cached.center_score or 0.0,
                "chinese": cached.chinese_score or 0.0,
                "quality": cached.quality_score or 0.0,
                "detail": cached.detail_score or 0.0,
            }
    # Fallback: try looking up by asset id
    async with async_session() as session:
        from database.models.asset import Asset
        import hashlib
        from pathlib import Path
        aresult = await session.execute(select(Asset).where(Asset.id == asset_id))
        asset = aresult.scalar_one_or_none()
        if asset and asset.file_path:
            fp_hash = hashlib.sha256(asset.file_path.encode()).hexdigest()
            r2 = await session.execute(select(FeatureCache).where(FeatureCache.image_hash == fp_hash))
            c2 = r2.scalar_one_or_none()
            if c2:
                return {
                    "center": c2.center_score or 0.0,
                    "chinese": c2.chinese_score or 0.0,
                    "quality": c2.quality_score or 0.0,
                    "detail": c2.detail_score or 0.0,
                }
    return None


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in weights.items()}


def _clamp_all(weights: dict[str, float]) -> dict[str, float]:
    return {k: max(MIN_WEIGHT, v) for k, v in weights.items()}


async def log_correction_events(
    product_id: str,
    selected_asset_ids: list[str],
    auto_select_suggested_ids: list[str],
    user_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    selected_set = set(selected_asset_ids)
    suggested_set = set(auto_select_suggested_ids)

    added = selected_set - suggested_set
    removed = suggested_set - selected_set

    all_affected = added | removed
    if not all_affected:
        logger.info("no_corrections", product_id=product_id)
        return {"events_logged": 0}

    events: list[CorrectionEvent] = []
    feature_cache_updates: dict[str, bool] = {}

    for asset_id in all_affected:
        features = await _get_image_features(asset_id)
        if features is None:
            logger.warning("correction_no_features", asset_id=asset_id)
            continue
        is_selected = asset_id in selected_set
        events.append(CorrectionEvent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            product_id=product_id,
            asset_id=asset_id,
            image_hash="",
            center_score=features["center"],
            chinese_score=features["chinese"],
            quality_score=features["quality"],
            detail_score=features["detail"],
            selected=is_selected,
            created_at=datetime.utcnow(),
        ))
        # Track which image_hash to update FeatureCache for
        async with async_session() as session:
            r = await session.execute(
                select(FeatureCache).where(
                    FeatureCache.center_score == features["center"],
                    FeatureCache.chinese_score == features["chinese"],
                )
            )
            match = r.scalar_one_or_none()
            if match:
                feature_cache_updates[match.image_hash] = is_selected

    if not events:
        return {"events_logged": 0}

    async with async_session() as session:
        for e in events:
            session.add(e)
        await session.commit()

    # Update FeatureCache selectedCount/rejectedCount
    async with async_session() as session:
        for img_hash, was_selected in feature_cache_updates.items():
            await session.execute(
                update(FeatureCache)
                .where(FeatureCache.image_hash == img_hash)
                .values(
                    selected_count=FeatureCache.selected_count + (1 if was_selected else 0),
                    rejected_count=FeatureCache.rejected_count + (0 if was_selected else 1),
                )
            )
        await session.commit()

    # Determine scope and update weights
    scope_id, scope_type = await _resolve_scope_for_update(user_id, project_id)
    await _adjust_weights(scope_id, scope_type, events)

    logger.info("corrections_logged", product_id=product_id, total=len(events),
                added=len(added), removed=len(removed), scope=f"{scope_type}:{scope_id}")

    return {
        "events_logged": len(events),
        "added": len(added),
        "removed": len(removed),
        "scope_type": scope_type,
        "scope_id": scope_id,
    }


async def _resolve_scope_for_update(user_id: str, project_id: str) -> tuple[str, str]:
    if user_id:
        async with async_session() as session:
            cnt = await session.scalar(
                select(func.count(CorrectionEvent.id)).where(CorrectionEvent.user_id == user_id)
            )
            if cnt is not None and cnt >= SCOPE_THRESHOLD:
                return user_id, "user"
    if project_id:
        async with async_session() as session:
            cnt = await session.scalar(
                select(func.count(CorrectionEvent.id)).where(CorrectionEvent.project_id == project_id)
            )
            if cnt is not None and cnt >= SCOPE_THRESHOLD:
                return project_id, "project"
    return "global", "global"


async def resolve_weights(
    user_id: str = "",
    project_id: str = "",
) -> dict[str, float]:
    scope_chain = [
        (user_id, "user") if user_id else None,
        (project_id, "project") if project_id else None,
        ("global", "global"),
    ]

    async with async_session() as session:
        for pair in scope_chain:
            if pair is None:
                continue
            sid, stype = pair
            if sid == "global" and stype == "global":
                result = await session.execute(
                    select(LearningWeight).where(
                        LearningWeight.scope_id == "global",
                        LearningWeight.scope_type == "global",
                    )
                )
            else:
                cnt = await session.scalar(
                    select(func.count(CorrectionEvent.id))
                    .where(
                        CorrectionEvent.user_id == sid if stype == "user"
                        else CorrectionEvent.project_id == sid
                    )
                )
                if cnt is None or cnt < SCOPE_THRESHOLD:
                    continue
                result = await session.execute(
                    select(LearningWeight).where(
                        LearningWeight.scope_id == sid,
                        LearningWeight.scope_type == stype,
                    )
                )
            row = result.scalar_one_or_none()
            if row:
                logger.info("weights_used", scope_type=stype, scope_id=sid,
                            center=round(row.center_weight, 3),
                            chinese=round(row.chinese_weight, 3),
                            quality=round(row.quality_weight, 3),
                            detail=round(row.detail_weight, 3))
                return {
                    "center": row.center_weight,
                    "chinese": row.chinese_weight,
                    "quality": row.quality_weight,
                    "detail": row.detail_weight,
                }

    logger.info("weights_default", scope="global")
    return dict(DEFAULT_WEIGHTS)


async def _adjust_weights(scope_id: str, scope_type: str, events: list[CorrectionEvent]) -> None:
    pos_features: list[dict[str, float]] = []
    neg_features: list[dict[str, float]] = []

    for e in events:
        feat = {
            "center": e.center_score,
            "chinese": e.chinese_score,
            "quality": e.quality_score,
            "detail": e.detail_score,
        }
        if e.selected:
            pos_features.append(feat)
        else:
            neg_features.append(feat)

    if not pos_features or not neg_features:
        logger.info("adjust_skipped_one_sided", scope=f"{scope_type}:{scope_id}")
        return

    pos_avg = {k: sum(f[k] for f in pos_features) / len(pos_features) for k in FEATURE_KEYS}
    neg_avg = {k: sum(f[k] for f in neg_features) / len(neg_features) for k in FEATURE_KEYS}

    # Difference: features that are higher in selected images get positive nudge
    diffs = {k: pos_avg[k] - neg_avg[k] for k in FEATURE_KEYS}

    async with async_session() as session:
        result = await session.execute(
            select(LearningWeight).where(
                LearningWeight.scope_id == scope_id,
                LearningWeight.scope_type == scope_type,
            )
        )
        lw = result.scalar_one_or_none()

        if not lw:
            lw = LearningWeight(
                id=str(uuid.uuid4()),
                scope_id=scope_id,
                scope_type=scope_type,
                **DEFAULT_WEIGHTS,
                event_count=0,
            )
            session.add(lw)

        old_weights = {
            "center": lw.center_weight,
            "chinese": lw.chinese_weight,
            "quality": lw.quality_weight,
            "detail": lw.detail_weight,
        }

        new_weights = dict(old_weights)
        for k in FEATURE_KEYS:
            if diffs[k] > 0:
                new_weights[k] += ADJUSTMENT_RATE
            elif diffs[k] < 0:
                new_weights[k] -= ADJUSTMENT_RATE

        new_weights = _clamp_all(new_weights)
        new_weights = _normalize(new_weights)

        lw.center_weight = new_weights["center"]
        lw.chinese_weight = new_weights["chinese"]
        lw.quality_weight = new_weights["quality"]
        lw.detail_weight = new_weights["detail"]
        lw.event_count = (lw.event_count or 0) + len(events)
        lw.last_updated = datetime.utcnow()
        await session.commit()

        logger.info("weights_adjusted", scope=f"{scope_type}:{scope_id}",
                    old=old_weights, new=new_weights, diffs=diffs)
