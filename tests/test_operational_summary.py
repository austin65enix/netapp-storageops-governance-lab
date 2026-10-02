from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from models.operational_summary import (
    CollectionHealth,
    ScheduledCollectionOperationalSummary,
)


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def summary(**changes):
    state = {
        "latest_run_id": "collect-20260807T115900Z-abcd1234",
        "latest_run_status": "PASS",
        "latest_run_started_at": NOW - timedelta(minutes=1),
        "latest_run_completed_at": NOW - timedelta(seconds=30),
        "last_success_at": NOW - timedelta(seconds=30),
        "last_failure_at": None,
        "consecutive_failures": 0,
        "timer_enabled": True,
        "timer_active": True,
        "next_trigger": NOW + timedelta(minutes=14),
        "now": NOW,
    }
    state.update(changes)
    return ScheduledCollectionOperationalSummary.from_state(**state)


def test_summary_contains_the_complete_contract_and_is_healthy():
    value = summary()

    assert set(asdict(value)) == {
        "latest_run_id",
        "latest_run_status",
        "latest_run_started_at",
        "latest_run_completed_at",
        "last_success_at",
        "last_failure_at",
        "consecutive_failures",
        "timer_enabled",
        "timer_active",
        "next_trigger",
        "collection_health",
    }
    assert value.collection_health is CollectionHealth.HEALTHY


def test_latest_failure_is_degraded_while_timer_continuity_is_intact():
    value = summary(
        latest_run_status="FAIL",
        last_failure_at=NOW - timedelta(seconds=30),
        consecutive_failures=1,
    )

    assert value.collection_health is CollectionHealth.DEGRADED


def test_naive_last_success_at_is_unhealthy():
    value = summary(last_success_at=datetime(2026, 8, 7, 11, 59, 30))

    assert value.collection_health is CollectionHealth.UNHEALTHY


def test_naive_last_failure_at_is_unhealthy():
    value = summary(last_failure_at=datetime(2026, 8, 7, 11, 59, 30))

    assert value.collection_health is CollectionHealth.UNHEALTHY


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timer_enabled", False),
        ("timer_active", False),
        ("next_trigger", NOW),
        ("next_trigger", NOW - timedelta(seconds=1)),
    ],
)
def test_timer_discontinuity_is_unhealthy(field, value):
    assert summary(**{field: value}).collection_health is CollectionHealth.UNHEALTHY


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latest_run_id", None),
        ("latest_run_status", None),
        ("latest_run_status", "UNKNOWN"),
        ("latest_run_started_at", None),
        ("latest_run_completed_at", None),
        ("consecutive_failures", None),
        ("timer_enabled", None),
        ("timer_active", None),
        ("next_trigger", None),
    ],
)
def test_missing_or_ambiguous_mandatory_state_fails_closed(field, value):
    assert summary(**{field: value}).collection_health is CollectionHealth.UNHEALTHY


@pytest.mark.parametrize(
    "changes",
    [
        {"latest_run_started_at": NOW},
        {"latest_run_started_at": datetime(2026, 8, 7, 11, 59)},
        {"next_trigger": datetime(2026, 8, 7, 12, 14)},
        {"consecutive_failures": -1},
        {"consecutive_failures": True},
        {"latest_run_status": "PASS", "consecutive_failures": 1},
        {"latest_run_status": "FAIL", "consecutive_failures": 0},
    ],
)
def test_inconsistent_mandatory_state_fails_closed(changes):
    assert summary(**changes).collection_health is CollectionHealth.UNHEALTHY
