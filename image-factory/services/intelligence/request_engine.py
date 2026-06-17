from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict
from typing import Any

from configs.settings import settings
from configs.logging import get_logger
from services.intelligence.event_emitter import EventEmitter
from services.intelligence.models import IntelligenceEventType

logger = get_logger(__name__)

MARKETPLACE_RULES: dict[str, dict[str, Any]] = {
    "1688.com": {
        "max_concurrent": 2,
        "delay_min": 4.0,
        "delay_max": 8.0,
        "backoff_strategy": "exponential",
        "backoff_base": 30,
        "max_requests_per_minute": 10,
        "burst_threshold": 3,
    },
    "taobao.com": {
        "max_concurrent": 2,
        "delay_min": 5.0,
        "delay_max": 10.0,
        "backoff_strategy": "exponential",
        "backoff_base": 60,
        "max_requests_per_minute": 6,
        "burst_threshold": 2,
    },
    "tmall.com": {
        "max_concurrent": 2,
        "delay_min": 5.0,
        "delay_max": 10.0,
        "backoff_strategy": "exponential",
        "backoff_base": 60,
        "max_requests_per_minute": 6,
        "burst_threshold": 2,
    },
    "alibaba.com": {
        "max_concurrent": 3,
        "delay_min": 3.0,
        "delay_max": 7.0,
        "backoff_strategy": "exponential",
        "backoff_base": 30,
        "max_requests_per_minute": 12,
        "burst_threshold": 4,
    },
    "aliexpress.com": {
        "max_concurrent": 3,
        "delay_min": 3.0,
        "delay_max": 6.0,
        "backoff_strategy": "exponential",
        "backoff_base": 30,
        "max_requests_per_minute": 15,
        "burst_threshold": 5,
    },
    "jd.com": {
        "max_concurrent": 4,
        "delay_min": 2.0,
        "delay_max": 5.0,
        "backoff_strategy": "linear",
        "backoff_base": 10,
        "max_requests_per_minute": 20,
        "burst_threshold": 6,
    },
    "pinduoduo.com": {
        "max_concurrent": 1,
        "delay_min": 8.0,
        "delay_max": 15.0,
        "backoff_strategy": "exponential",
        "backoff_base": 120,
        "max_requests_per_minute": 4,
        "burst_threshold": 2,
    },
    "default": {
        "max_concurrent": 3,
        "delay_min": 3.0,
        "delay_max": 7.0,
        "backoff_strategy": "linear",
        "backoff_base": 15,
        "max_requests_per_minute": 12,
        "burst_threshold": 5,
    },
}


class AdaptiveRequestEngine:
    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self.emitter = emitter or EventEmitter()
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request_time: dict[str, float] = {}
        self._request_timestamps: dict[str, list[float]] = defaultdict(list)
        self._backoff_until: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._rules: dict[str, dict[str, Any]] = {}

    def get_rules(self, domain: str) -> dict[str, Any]:
        if domain in self._rules:
            return self._rules[domain]
        return MARKETPLACE_RULES.get(domain, MARKETPLACE_RULES["default"])

    def set_rules(self, domain: str, rules: dict[str, Any]) -> None:
        self._rules[domain] = {**MARKETPLACE_RULES.get(domain, MARKETPLACE_RULES["default"]), **rules}

    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        if domain not in self._semaphores:
            rules = self.get_rules(domain)
            self._semaphores[domain] = asyncio.Semaphore(rules["max_concurrent"])
        return self._semaphores[domain]

    async def acquire(self, domain: str) -> float:
        rules = self.get_rules(domain)
        sem = self._get_semaphore(domain)

        await sem.acquire()

        now = time.time()

        if now < self._backoff_until.get(domain, 0):
            wait = self._backoff_until[domain] - now
            logger.info("backoff_wait", domain=domain, wait_seconds=round(wait, 2))
            await asyncio.sleep(wait)

        last_time = self._last_request_time.get(domain, 0)
        delay = random.uniform(rules["delay_min"], rules["delay_max"])
        elapsed = now - last_time
        if elapsed < delay and last_time > 0:
            actual_delay = delay - elapsed
            if actual_delay > 0:
                await asyncio.sleep(actual_delay)

        self._last_request_time[domain] = time.time()
        self._request_timestamps[domain].append(time.time())

        burst_count = self._detect_burst(domain)
        if burst_count > rules["burst_threshold"]:
            extra_delay = random.uniform(5.0, 15.0)
            await self.emitter.emit(IntelligenceEventType.BURST_DETECTED, domain, {
                "burst_count": burst_count,
                "extra_delay": extra_delay,
            })
            await asyncio.sleep(extra_delay)

        return delay

    def release(self, domain: str) -> None:
        sem = self._semaphores.get(domain)
        if sem:
            sem.release()

    def _detect_burst(self, domain: str) -> int:
        now = time.time()
        cutoff = now - 60.0
        timestamps = self._request_timestamps[domain]
        self._request_timestamps[domain] = [t for t in timestamps if t > cutoff]
        return len(self._request_timestamps[domain])

    async def record_failure(self, domain: str) -> None:
        self._consecutive_failures[domain] += 1
        rules = self.get_rules(domain)
        failures = self._consecutive_failures[domain]
        if rules["backoff_strategy"] == "exponential":
            backoff = rules["backoff_base"] * (2 ** (failures - 1))
            backoff = min(backoff, 3600)
        else:
            backoff = rules["backoff_base"] * failures
            backoff = min(backoff, 1800)
        self._backoff_until[domain] = time.time() + backoff
        logger.warning("request_backoff", domain=domain, failures=failures, backoff=backoff)
        await self.emitter.emit(IntelligenceEventType.REQUEST_DELAYED, domain, {
            "consecutive_failures": failures,
            "backoff_seconds": backoff,
            "strategy": rules["backoff_strategy"],
        })

    async def record_success(self, domain: str) -> None:
        if self._consecutive_failures[domain] > 0:
            self._consecutive_failures[domain] = max(0, self._consecutive_failures[domain] - 1)
        if self._consecutive_failures[domain] == 0:
            self._backoff_until[domain] = 0
