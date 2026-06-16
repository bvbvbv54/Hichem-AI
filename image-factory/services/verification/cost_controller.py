from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from configs.settings import settings


@dataclass
class BudgetLimits:
    max_text_calls: int = 1
    max_image_calls: int = 1
    max_retries: int = 1
    max_total_cost_cents: int = 50  # $0.50 hard cap


class CostController:
    """Enforces hard budget limits during smoke tests."""

    def __init__(self) -> None:
        self.text_calls_used = 0
        self.image_calls_used = 0
        self.retries_used = 0
        self.total_cost_cents = 0
        self.limits = BudgetLimits(
            max_text_calls=int(os.getenv("SMOKE_MAX_TEXT_CALLS", "1")),
            max_image_calls=int(os.getenv("SMOKE_MAX_IMAGE_CALLS", "1")),
            max_retries=int(os.getenv("SMOKE_MAX_RETRIES", "1")),
            max_total_cost_cents=int(os.getenv("SMOKE_MAX_COST_CENTS", "50")),
        )

    def check_text_budget(self) -> None:
        if self.text_calls_used >= self.limits.max_text_calls:
            raise BudgetExceededError(
                f"Text generation budget exhausted: {self.text_calls_used}/{self.limits.max_text_calls} used"
            )

    def check_image_budget(self) -> None:
        if self.image_calls_used >= self.limits.max_image_calls:
            raise BudgetExceededError(
                f"Image generation budget exhausted: {self.image_calls_used}/{self.limits.max_image_calls} used"
            )

    def check_retry_budget(self) -> None:
        if self.retries_used >= self.limits.max_retries:
            raise BudgetExceededError(
                f"Retry budget exhausted: {self.retries_used}/{self.limits.max_retries} used"
            )

    def check_cost_budget(self, additional_cents: int = 0) -> None:
        projected = self.total_cost_cents + additional_cents
        if projected > self.limits.max_total_cost_cents:
            raise BudgetExceededError(
                f"Cost budget would be exceeded: ${projected/100:.2f} > $${self.limits.max_total_cost_cents/100:.2f}"
            )

    def record_text_call(self, cost_cents: int = 1) -> None:
        self.text_calls_used += 1
        self.total_cost_cents += cost_cents
        self.check_cost_budget()

    def record_image_call(self, cost_cents: int = 10) -> None:
        self.image_calls_used += 1
        self.total_cost_cents += cost_cents
        self.check_cost_budget()

    def record_retry(self) -> None:
        self.retries_used += 1

    @property
    def is_exhausted(self) -> bool:
        return (
            self.text_calls_used >= self.limits.max_text_calls
            and self.image_calls_used >= self.limits.max_image_calls
        )

    def summary(self) -> dict:
        return {
            "text_calls_used": self.text_calls_used,
            "text_calls_limit": self.limits.max_text_calls,
            "image_calls_used": self.image_calls_used,
            "image_calls_limit": self.limits.max_image_calls,
            "retries_used": self.retries_used,
            "retries_limit": self.limits.max_retries,
            "total_cost_cents": self.total_cost_cents,
            "cost_limit_cents": self.limits.max_total_cost_cents,
            "budget_exhausted": self.is_exhausted,
        }


class BudgetExceededError(Exception):
    pass
