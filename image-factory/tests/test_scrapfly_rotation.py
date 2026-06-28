"""Tests for the Scrapfly key rotation system."""
from __future__ import annotations

import json
import time
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from services.scrapfly_rotation import (
    COST_HISTORY_KEY,
    DEFAULT_AVG_COST,
    DEFAULT_CREDITS,
    RESERVATION_KEY,
    STATE_KEY,
    WORKER_ID,
    CreditEstimator,
    KeyState,
    KeyStateManager,
    RecoveryScheduler,
)


@pytest.fixture
def redis_mock():
    r = AsyncMock()
    r.hgetall.return_value = {}
    r.hget.return_value = None
    r.get.return_value = None
    r.lrange.return_value = []
    r.set.return_value = True
    r.setex.return_value = True
    r.delete.return_value = True
    r.expire.return_value = True
    r.hset.return_value = True
    r.hincrby.return_value = 1
    r.lpush.return_value = 1
    r.ltrim.return_value = True
    r.scan.return_value = (0, [])
    r.ttl.return_value = -1
    r.ping.return_value = True
    return r


@pytest.fixture
def keys():
    return [
        "scp-live-key1aaaaaaaaaaaaaaaaaaa",
        "scp-live-key2bbbbbbbbbbbbbbbbbbb",
        "scp-live-key3ccccccccccccccccccc",
    ]


@pytest.fixture
def reset_dates():
    return {
        "scp-live-key1aaaaaaaaaaaaaaaaaaa": "2026-07-17",
        "scp-live-key2bbbbbbbbbbbbbbbbbbb": "2026-07-17",
        "scp-live-key3ccccccccccccccccccc": "2026-07-27",
    }


_TEST_KEY = "scp-live-key-xxxxxxxxx-test0"


def _ks(k: str) -> str:
    return k[:20]


class TestKeyState:
    def test_is_available_active_no_cooldown(self):
        state = KeyState(key="test", status="ACTIVE", estimated_credits_remaining=500)
        assert state.is_available is True

    def test_is_available_not_active(self):
        state = KeyState(key="test", status="COOLDOWN")
        assert state.is_available is False

    def test_is_available_exhausted_credits(self):
        state = KeyState(key="test", status="ACTIVE", estimated_credits_remaining=0)
        assert state.is_available is False

    def test_is_available_in_cooldown(self):
        state = KeyState(key="test", status="ACTIVE", estimated_credits_remaining=500, cooldown_until=time.time() + 100)
        assert state.is_available is False

    def test_is_available_suspect(self):
        state = KeyState(key="test", status="SUSPECT", estimated_credits_remaining=500)
        assert state.is_available is True

    def test_is_available_draining(self):
        state = KeyState(key="test", status="DRAINING", estimated_credits_remaining=500)
        assert state.is_available is True

    def test_weight_higher_for_more_credits(self):
        high = KeyState(key="high", status="ACTIVE", estimated_credits_remaining=800, requests_made=0)
        low = KeyState(key="low", status="ACTIVE", estimated_credits_remaining=200, requests_made=0)
        assert high.weight > low.weight

    def test_weight_penalty_for_recent_failure(self):
        recent_fail = KeyState(key="fail", status="ACTIVE", estimated_credits_remaining=500,
                               last_success=time.time() - 100, last_failure=time.time() - 10, requests_made=5)
        recent_success = KeyState(key="ok", status="ACTIVE", estimated_credits_remaining=500,
                                   last_success=time.time() - 10, last_failure=time.time() - 100, requests_made=5)
        assert recent_success.weight > recent_fail.weight

    def test_weight_draining_penalty(self):
        normal = KeyState(key="a", status="ACTIVE", estimated_credits_remaining=500, requests_made=10)
        draining = KeyState(key="b", status="ACTIVE", estimated_credits_remaining=500, requests_made=10, draining=True)
        assert normal.weight > draining.weight


class TestCreditEstimator:
    async def test_record_and_get_stats(self, redis_mock):
        estimator = CreditEstimator(redis_mock)
        await estimator.record_cost("key1", 12)
        redis_mock.lpush.assert_called_once_with(f"{COST_HISTORY_KEY}key1", 12)
        redis_mock.ltrim.assert_called_once()
        redis_mock.expire.assert_called_once()

    async def test_get_stats_default_when_empty(self, redis_mock):
        estimator = CreditEstimator(redis_mock)
        redis_mock.lrange.return_value = []
        stats = await estimator.get_stats("key1")
        assert stats["avg"] == DEFAULT_AVG_COST
        assert stats["count"] == 0

    async def test_get_stats_with_data(self, redis_mock):
        estimator = CreditEstimator(redis_mock)
        redis_mock.lrange.return_value = [b"8", b"12", b"15", b"10", b"9"]
        stats = await estimator.get_stats("key1")
        assert stats["count"] == 5
        assert stats["p50"] == 10.0
        assert stats["avg"] == 10.8


class TestKeyStateManager:
    async def test_load_all_states_creates_unknown(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        states = await mgr.load_all_states(keys, reset_dates)
        assert len(states) == 3
        assert all(s.status == "UNKNOWN" for s in states)
        assert all(s.reset_date is not None for s in states)

    async def test_select_best_key_returns_highest_weight(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        await mgr.load_all_states(keys, reset_dates)
        for state in mgr._local_states.values():
            state.status = "ACTIVE"
        mgr._local_states[_ks(keys[0])].estimated_credits_remaining = 900
        mgr._local_states[_ks(keys[1])].estimated_credits_remaining = 500
        mgr._local_states[_ks(keys[2])].estimated_credits_remaining = 100

        best = await mgr.select_best_key(keys)
        assert best == keys[0]

    async def test_select_best_key_returns_none_when_all_exhausted(self, redis_mock, keys):
        mgr = KeyStateManager(redis_mock)
        for k in keys:
            mgr._local_states[_ks(k)] = KeyState(key=_ks(k), status="ACTIVE", estimated_credits_remaining=0)
        best = await mgr.select_best_key(keys)
        assert best is None

    async def test_select_best_key_skips_non_active(self, redis_mock, keys):
        mgr = KeyStateManager(redis_mock)
        mgr._local_states[_ks(keys[0])] = KeyState(key=_ks(keys[0]), status="COOLDOWN", estimated_credits_remaining=500)
        mgr._local_states[_ks(keys[1])] = KeyState(key=_ks(keys[1]), status="EXHAUSTED", estimated_credits_remaining=500)
        mgr._local_states[_ks(keys[2])] = KeyState(key=_ks(keys[2]), status="ACTIVE", estimated_credits_remaining=500)
        best = await mgr.select_best_key(keys)
        assert best == keys[2]

    async def test_record_success_updates_state(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = "scp-live-test-key-1234567890123456"
        key_short = _ks(key)
        mgr._local_states[key_short] = KeyState(key=key_short, status="UNKNOWN")
        await mgr.record_success(key, cost=12, remaining=988, remaining_project=5000)
        assert mgr._local_states[key_short].status == "ACTIVE"
        assert mgr._local_states[key_short].consecutive_failures == 0
        assert mgr._local_states[key_short].requests_made == 1
        assert mgr._local_states[key_short].estimated_credits_remaining == 988
        assert mgr._local_states[key_short].suspect_failures == 0
        redis_mock.hset.assert_called()

    async def test_record_failure_401_disables_key(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = _TEST_KEY + "z" * 10
        ks = _ks(key)
        mgr._local_states[ks] = KeyState(key=ks, status="ACTIVE")
        await mgr.record_failure(key, status_code=401)
        assert mgr._local_states[ks].status == "DISABLED"

    async def test_record_failure_429_exhausted(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = _TEST_KEY + "z" * 10
        ks = _ks(key)
        mgr._local_states[ks] = KeyState(key=ks, status="ACTIVE", estimated_credits_remaining=0)
        await mgr.record_failure(key, status_code=429, error="quota reached")
        assert mgr._local_states[ks].status == "EXHAUSTED"

    async def test_record_failure_429_rate_limit(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = _TEST_KEY + "z" * 10
        ks = _ks(key)
        mgr._local_states[ks] = KeyState(key=ks, status="ACTIVE", estimated_credits_remaining=500)
        await mgr.record_failure(key, status_code=429)
        assert mgr._local_states[ks].status == "COOLDOWN"

    async def test_consecutive_failures_triggers_suspect_then_cooldown(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = _TEST_KEY + "z" * 10
        ks = _ks(key)
        state = KeyState(key=ks, status="ACTIVE")
        mgr._local_states[ks] = state

        # First 3 failures → SUSPECT (via suspect_failures >= 3)
        for i in range(3):
            await mgr.record_failure(key, status_code=500)

        assert state.suspect_failures == 3
        assert state.status == "SUSPECT"

        for i in range(2):
            await mgr.record_failure(key, status_code=500)

        assert state.status == "COOLDOWN"

    async def test_reserve_key_acquires_lock(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        redis_mock.set.return_value = True
        result = await mgr.reserve_key("scp-live-test-key")
        assert result is True
        redis_mock.set.assert_called_once()

    async def test_reserve_key_fails_when_locked(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        redis_mock.set.return_value = None
        result = await mgr.reserve_key("scp-live-test-key")
        assert result is False

    async def test_release_key_respects_owner(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        lock_name = f"{RESERVATION_KEY}scp-live-test-key"
        redis_mock.get.return_value = WORKER_ID.encode()
        await mgr.release_key("scp-live-test-key")
        redis_mock.delete.assert_called_once_with(lock_name)

    async def test_release_key_ignores_wrong_owner(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        redis_mock.get.return_value = b"other-worker"
        await mgr.release_key("scp-live-test-key")
        redis_mock.delete.assert_not_called()

    async def test_renew_lease_succeeds_for_owner(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        lock_name = f"{RESERVATION_KEY}scp-live-test-key"
        redis_mock.get.return_value = WORKER_ID.encode()
        result = await mgr.renew_lease("scp-live-test-key")
        assert result is True
        redis_mock.expire.assert_called_once_with(lock_name, 120)

    async def test_renew_lease_fails_for_wrong_owner(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        redis_mock.get.return_value = b"other-worker"
        result = await mgr.renew_lease("scp-live-test-key")
        assert result is False

    async def test_update_metrics(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        states = [
            KeyState(key="k1", status="ACTIVE", estimated_credits_remaining=500, average_cost=10, requests_made=5, success_rate=0.9),
            KeyState(key="k2", status="ACTIVE", estimated_credits_remaining=300, average_cost=12, requests_made=3, success_rate=0.95),
            KeyState(key="k3", status="SUSPECT", estimated_credits_remaining=800, average_cost=8, requests_made=10, success_rate=0.7),
            KeyState(key="k4", status="COOLDOWN", estimated_credits_remaining=800, average_cost=8, requests_made=10, success_rate=0.6),
            KeyState(key="k5", status="EXHAUSTED", estimated_credits_remaining=0, average_cost=15, requests_made=20, success_rate=0.5),
            KeyState(key="k6", status="DISABLED", estimated_credits_remaining=0, average_cost=12, requests_made=0, success_rate=0.0),
            KeyState(key="k7", status="DRAINING", estimated_credits_remaining=200, average_cost=12, requests_made=50, success_rate=0.8, draining=True),
        ]
        await mgr.update_metrics(states)
        assert redis_mock.hset.called
        call_args = redis_mock.hset.call_args
        assert call_args is not None
        mapping = call_args[1].get("mapping", {})
        assert mapping.get("active_keys") == "2"
        assert mapping.get("suspect_keys") == "1"
        assert mapping.get("draining_keys") == "1"
        assert mapping.get("cooldown_keys") == "1"
        assert mapping.get("exhausted_keys") == "1"
        assert mapping.get("disabled_keys") == "1"
        assert mapping.get("dead_keys_count") == "2"
        assert int(mapping.get("estimated_scrapes_remaining", 0)) > 0


class TestRecoveryScheduler:
    async def test_recover_from_cooldown(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        states = await mgr.load_all_states(keys, reset_dates)
        for s in states:
            s.status = "COOLDOWN"
            s.cooldown_until = time.time() - 1

        revived = await scheduler.run_recovery_cycle(keys, reset_dates)
        assert len(revived) == 3

    async def test_recover_exhausted_after_reset_with_health_check(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        states = await mgr.load_all_states(keys, reset_dates)
        for s in states:
            s.status = "EXHAUSTED"
            s.cooldown_until = time.time() - 1
            s.estimated_credits_remaining = 800

        with (
            patch("services.scrapfly_rotation.datetime") as mock_dt,
            patch.object(scheduler, "health_check_key", AsyncMock(return_value=True)) as mock_health,
        ):
            mock_dt.now.return_value.strftime.return_value = "2026-07-20"
            mock_dt.strptime.return_value.replace.return_value = __import__("datetime").datetime(
                2026, 7, 17, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.now.return_value = __import__("datetime").datetime(
                2026, 7, 20, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.strptime.return_value = __import__("datetime").datetime(2026, 7, 17)

            revived = await scheduler.run_recovery_cycle(keys, reset_dates)
            assert len(revived) >= 1
            assert mock_health.called

    async def test_recover_exhausted_low_credits_not_restored(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        states = await mgr.load_all_states(keys, reset_dates)
        for s in states:
            s.status = "EXHAUSTED"
            s.cooldown_until = time.time() - 1
            s.estimated_credits_remaining = 100  # below MIN_RESTORE_THRESHOLD

        with (
            patch("services.scrapfly_rotation.datetime") as mock_dt,
            patch.object(scheduler, "health_check_key", AsyncMock(return_value=True)) as mock_health,
        ):
            mock_dt.now.return_value.strftime.return_value = "2026-07-20"
            mock_dt.strptime.return_value.replace.return_value = __import__("datetime").datetime(
                2026, 7, 17, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.now.return_value = __import__("datetime").datetime(
                2026, 7, 20, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.strptime.return_value = __import__("datetime").datetime(2026, 7, 17)

            revived = await scheduler.run_recovery_cycle(keys, reset_dates)
            assert len(revived) == 0

    async def test_recover_exhausted_health_check_fails(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        states = await mgr.load_all_states(keys, reset_dates)
        for s in states:
            s.status = "EXHAUSTED"
            s.cooldown_until = time.time() - 1
            s.estimated_credits_remaining = 800

        with (
            patch("services.scrapfly_rotation.datetime") as mock_dt,
            patch.object(scheduler, "health_check_key", AsyncMock(return_value=False)),
        ):
            mock_dt.now.return_value.strftime.return_value = "2026-07-20"
            mock_dt.strptime.return_value.replace.return_value = __import__("datetime").datetime(
                2026, 7, 17, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.now.return_value = __import__("datetime").datetime(
                2026, 7, 20, tzinfo=__import__("datetime").timezone.utc
            )
            mock_dt.strptime.return_value = __import__("datetime").datetime(2026, 7, 17)

            revived = await scheduler.run_recovery_cycle(keys, reset_dates)
            assert len(revived) == 0

    async def test_recover_from_suspect_after_window(self, redis_mock, keys, reset_dates):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        states = await mgr.load_all_states(keys, reset_dates)
        for s in states:
            s.status = "SUSPECT"
            s.suspect_window_start = time.time() - 601
            s.suspect_failures = 3
            s.consecutive_failures = 0

        revived = await scheduler.run_recovery_cycle(keys, reset_dates)
        assert len(revived) == 3

    async def test_health_check_success(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        key = "scp-live-key-1-health-check-x"
        key_short = _ks(key)
        mgr._local_states[key_short] = KeyState(key=key_short, status="UNKNOWN", estimated_credits_remaining=0)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json = MagicMock(return_value={"subscription": {"usage": {"scrape": {"remaining": 850}}}})

            mock_instance = MagicMock()
            mock_instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__.return_value = mock_instance

            healthy = await scheduler.health_check_key(key)
            assert healthy is True
            assert mgr._local_states[key_short].estimated_credits_remaining == 850
            assert mgr._local_states[key_short].status == "ACTIVE"

    async def test_health_check_failure_returns_false(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        scheduler = RecoveryScheduler(redis_mock, mgr)
        key = "scp-live-key-2-health-check-x"
        key_short = _ks(key)
        mgr._local_states[key_short] = KeyState(key=key_short, status="UNKNOWN")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_instance = MagicMock()
            mock_instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__.return_value = mock_instance

            healthy = await scheduler.health_check_key(key)
            assert healthy is False


class TestMultiWorkerConcurrency:
    async def test_same_key_not_allocated_twice(self, redis_mock, keys):
        mgr = KeyStateManager(redis_mock)
        await mgr.load_all_states(keys, {})
        for s in mgr._local_states.values():
            s.status = "ACTIVE"

        best = await mgr.select_best_key(keys)
        assert best is not None

        reserved = await mgr.reserve_key(best)
        assert reserved is True

        redis_mock.set.return_value = None
        reserved2 = await mgr.reserve_key(best)
        assert reserved2 is False

    async def test_all_keys_exhausted_multi_worker(self, redis_mock, keys):
        mgr = KeyStateManager(redis_mock)
        for k in keys:
            mgr._local_states[_ks(k)] = KeyState(key=_ks(k), status="EXHAUSTED", estimated_credits_remaining=0)
        best = await mgr.select_best_key(keys)
        assert best is None


class TestReservationCollision:
    async def test_50_workers_no_duplicates(self, redis_mock, keys):
        """Simulate 50 workers competing for 10 keys. Verify no duplicate reservation."""
        test_keys = [f"scp-live-key-{i}xxxxx" for i in range(10)]
        for k in test_keys:
            redis_mock.get.return_value = None

        async def reserve_once(mgr, key):
            result = await mgr.reserve_key(key)
            if result:
                redis_mock.set.return_value = None
            return result

        mgr = KeyStateManager(redis_mock)

        reservations = []
        for key in test_keys:
            r = await reserve_once(mgr, key)
            if r:
                reservations.append(key)

        lock_keys = [f"{RESERVATION_KEY}{_ks(k)}" for k in test_keys]
        distinct = len(reservations)
        assert distinct <= 10
        assert distinct == len(set(reservations))


class TestVariableScrapeCosts:
    async def test_rolling_average_updates(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key = _TEST_KEY + "z" * 10
        ks = _ks(key)
        mgr._local_states[ks] = KeyState(key=ks, status="ACTIVE", average_cost=12)

        costs = [6, 8, 12, 15, 18]
        for i, c in enumerate(costs):
            stored = [str(x).encode() for x in costs[:i + 1]]
            redis_mock.lrange.return_value = stored
            await mgr.record_success(key, cost=c, remaining=900, remaining_project=5000)

        assert mgr._local_states[ks].average_cost == 11.8

    async def test_estimated_scrapes_uses_rolling_avg(self, redis_mock):
        mgr = KeyStateManager(redis_mock)
        key_short = "test-key"
        mgr._local_states[key_short] = KeyState(key=key_short, status="ACTIVE", estimated_credits_remaining=1000, average_cost=10)
        assert mgr._local_states[key_short].estimated_credits_remaining // DEFAULT_AVG_COST == 83

    async def test_p50_p95_from_cost_history(self, redis_mock):
        estimator = CreditEstimator(redis_mock)
        redis_mock.lrange.return_value = [b"6", b"7", b"8", b"12", b"15", b"18", b"20", b"22", b"25", b"30"]
        stats = await estimator.get_stats("key1")
        assert stats["p50"] == 16.5
        assert stats["count"] == 10


class TestEmergencyCache:
    async def test_fallback_on_redis_failure(self, redis_mock, keys):
        redis_mock.hgetall.side_effect = ConnectionError("Redis down")
        redis_mock.hset.side_effect = ConnectionError("Redis down")
        mgr = KeyStateManager(redis_mock)

        states = await mgr.load_all_states(keys, {})
        assert len(states) == 3
        assert all(s.status == "UNKNOWN" for s in states)
        assert mgr._emergency.is_active

    async def test_emergency_read_on_redis_down(self, redis_mock, keys):
        redis_mock.hgetall.side_effect = ConnectionError("Redis down")
        mgr = KeyStateManager(redis_mock)

        state = KeyState(key=_ks(keys[0]), status="ACTIVE")
        mgr._emergency.set(state)

        loaded = await mgr._load_state(keys[0], None)
        assert loaded.status == "ACTIVE"


class TestIntegrationScrapflyClient:
    @patch("services.acquisition.scrapfly_client.ScrapflyClient._get_keys")
    @patch("services.acquisition.scrapfly_client.ScrapflyClient._get_redis")
    async def test_fetch_page_uses_best_key(self, mock_redis, mock_keys):
        from services.acquisition.scrapfly_client import ScrapflyClient

        redis_mock = AsyncMock()
        redis_mock.hgetall.return_value = {}
        redis_mock.hget.return_value = None
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.setex.return_value = True
        redis_mock.delete.return_value = True
        redis_mock.expire.return_value = True
        redis_mock.hset.return_value = True
        redis_mock.hincrby.return_value = 1
        redis_mock.zremrangebyscore.return_value = True
        redis_mock.zcard.return_value = 0
        redis_mock.zadd.return_value = True
        redis_mock.zrange.return_value = []
        redis_mock.scan.return_value = (0, [])
        redis_mock.lrange.return_value = [b"12"]
        mock_redis.return_value = redis_mock

        test_keys = [
            "scp-live-key1aaaaaaaaaaaaaaaaaaa",
            "scp-live-key2bbbbbbbbbbbbbbbbbbb",
        ]
        mock_keys.return_value = test_keys

        client = ScrapflyClient()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_httpx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {
                "x-scrapfly-api-cost": "12",
                "x-scrapfly-remaining-api-credit": "988",
                "x-scrapfly-project-remaining-api-credit": "5000",
            }
            mock_resp.json = MagicMock(return_value={"result": {"content": "<html>ok</html>"}})
            mock_httpx.get = AsyncMock(return_value=mock_resp)
            mock_get_client.return_value = mock_httpx

            result = await client.fetch_page("https://example.com", render_js=True)

            assert result == "<html>ok</html>"
            mock_httpx.get.assert_called_once()
            call_kwargs = mock_httpx.get.call_args[1]
            params = call_kwargs.get("params", {})
            assert params.get("key") in test_keys

        await client.close()
