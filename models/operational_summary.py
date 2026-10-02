from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CollectionHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def evaluate_collection_health(
    *,
    latest_run_id: str | None,
    latest_run_status: str | None,
    latest_run_started_at: datetime | None,
    latest_run_completed_at: datetime | None,
    last_success_at: datetime | None,
    last_failure_at: datetime | None,
    consecutive_failures: int | None,
    timer_enabled: bool | None,
    timer_active: bool | None,
    next_trigger: datetime | None,
    now: datetime,
) -> CollectionHealth:
    """Derive collection health without reading or changing external state."""
    timestamps = (
        latest_run_started_at,
        latest_run_completed_at,
        next_trigger,
        now,
    )
    historical_timestamps = (last_success_at, last_failure_at)
    mandatory_state_is_valid = (
        isinstance(latest_run_id, str)
        and bool(latest_run_id.strip())
        and latest_run_status in {"PASS", "FAIL"}
        and all(_is_aware(value) for value in timestamps)
        and all(
            value is None or _is_aware(value)
            for value in historical_timestamps
        )
        and latest_run_started_at <= latest_run_completed_at
        and isinstance(consecutive_failures, int)
        and not isinstance(consecutive_failures, bool)
        and consecutive_failures >= 0
        and isinstance(timer_enabled, bool)
        and isinstance(timer_active, bool)
    )

    if not mandatory_state_is_valid:
        return CollectionHealth.UNHEALTHY

    run_state_is_consistent = (
        latest_run_status == "PASS" and consecutive_failures == 0
    ) or (
        latest_run_status == "FAIL" and consecutive_failures > 0
    )
    timer_continuity_is_intact = (
        timer_enabled
        and timer_active
        and next_trigger > now
    )

    if not run_state_is_consistent or not timer_continuity_is_intact:
        return CollectionHealth.UNHEALTHY
    if latest_run_status == "PASS":
        return CollectionHealth.HEALTHY
    return CollectionHealth.DEGRADED


@dataclass(frozen=True)
class ScheduledCollectionOperationalSummary:
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_started_at: datetime | None
    latest_run_completed_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int | None
    timer_enabled: bool | None
    timer_active: bool | None
    next_trigger: datetime | None
    collection_health: CollectionHealth

    @classmethod
    def from_state(
        cls,
        *,
        latest_run_id: str | None,
        latest_run_status: str | None,
        latest_run_started_at: datetime | None,
        latest_run_completed_at: datetime | None,
        last_success_at: datetime | None,
        last_failure_at: datetime | None,
        consecutive_failures: int | None,
        timer_enabled: bool | None,
        timer_active: bool | None,
        next_trigger: datetime | None,
        now: datetime,
    ) -> ScheduledCollectionOperationalSummary:
        health = evaluate_collection_health(
            latest_run_id=latest_run_id,
            latest_run_status=latest_run_status,
            latest_run_started_at=latest_run_started_at,
            latest_run_completed_at=latest_run_completed_at,
            last_success_at=last_success_at,
            last_failure_at=last_failure_at,
            consecutive_failures=consecutive_failures,
            timer_enabled=timer_enabled,
            timer_active=timer_active,
            next_trigger=next_trigger,
            now=now,
        )
        return cls(
            latest_run_id=latest_run_id,
            latest_run_status=latest_run_status,
            latest_run_started_at=latest_run_started_at,
            latest_run_completed_at=latest_run_completed_at,
            last_success_at=last_success_at,
            last_failure_at=last_failure_at,
            consecutive_failures=consecutive_failures,
            timer_enabled=timer_enabled,
            timer_active=timer_active,
            next_trigger=next_trigger,
            collection_health=health,
        )
