from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_record_and_estimate_stage():
    from services.time_estimator import TimeEstimator
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        json.dumps({"job_id": "j1", "duration": 10.0, "ts": "2024-01-01T00:00:00"}),
        json.dumps({"job_id": "j2", "duration": 20.0, "ts": "2024-01-01T00:01:00"}),
    ])
    estimator = TimeEstimator(redis)
    await estimator.record_stage("j3", "test_stage", 15.0)
    redis.lpush.assert_called_once()
    redis.ltrim.assert_called_once()
    redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_estimated_stage_duration_average():
    from services.time_estimator import TimeEstimator
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        json.dumps({"job_id": "j1", "duration": 10.0}),
        json.dumps({"job_id": "j2", "duration": 20.0}),
        json.dumps({"job_id": "j3", "duration": 30.0}),
    ])
    estimator = TimeEstimator(redis)
    avg = await estimator.estimated_stage_duration("acquisition")
    assert avg == 20.0


@pytest.mark.asyncio
async def test_estimated_stage_duration_no_data():
    from services.time_estimator import TimeEstimator
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    estimator = TimeEstimator(redis)
    avg = await estimator.estimated_stage_duration("unknown")
    assert avg == 0.0


@pytest.mark.asyncio
async def test_estimated_total_remaining():
    from services.time_estimator import TimeEstimator
    redis = AsyncMock()

    def lrange_side(key, *a):
        data = {
            "time_estimator:durations:acquisition": [json.dumps({"duration": 15.0})],
            "time_estimator:durations:generation": [json.dumps({"duration": 45.0})],
        }
        return data.get(key, [])

    redis.lrange = AsyncMock(side_effect=lrange_side)
    estimator = TimeEstimator(redis)
    total = await estimator.estimated_total_remaining(["acquisition", "generation"])
    assert total == 60.0


@pytest.mark.asyncio
async def test_estimated_stage_duration_ceil():
    from services.time_estimator import TimeEstimator
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        json.dumps({"duration": 10.2}),
        json.dumps({"duration": 10.3}),
    ])
    estimator = TimeEstimator(redis)
    avg = await estimator.estimated_stage_duration("precise")
    assert avg == 11.0
