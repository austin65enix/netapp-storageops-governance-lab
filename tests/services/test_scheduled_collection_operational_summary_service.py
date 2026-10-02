from datetime import datetime, timezone

import pytest

from models.operational_summary import (
    CollectionHealth,
    ScheduledCollectionOperationalSummary,
)
from services import scheduled_collection_operational_summary_service as service


def summary() -> ScheduledCollectionOperationalSummary:
    started_at = datetime(2026, 8, 10, 11, 58, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 10, 11, 59, tzinfo=timezone.utc)
    return ScheduledCollectionOperationalSummary(
        latest_run_id="collect-unhealthy",
        latest_run_status="FAIL",
        latest_run_started_at=started_at,
        latest_run_completed_at=completed_at,
        last_success_at=None,
        last_failure_at=completed_at,
        consecutive_failures=1,
        timer_enabled=False,
        timer_active=False,
        next_trigger=None,
        collection_health=CollectionHealth.UNHEALTHY,
    )


class Reader:
    def __init__(self, result: ScheduledCollectionOperationalSummary) -> None:
        self.result = result
        self.calls = 0

    def read(self) -> ScheduledCollectionOperationalSummary:
        self.calls += 1
        return self.result


def test_injected_reader_is_called_exactly_once_and_result_is_unchanged():
    expected = summary()
    reader = Reader(expected)

    actual = service.read_scheduled_collection_operational_summary(reader)

    assert reader.calls == 1
    assert actual is expected
    assert actual.collection_health is CollectionHealth.UNHEALTHY


def test_injected_exception_propagates_unchanged():
    expected = RuntimeError("reader failed")

    class FailingReader:
        def read(self) -> ScheduledCollectionOperationalSummary:
            raise expected

    with pytest.raises(RuntimeError) as raised:
        service.read_scheduled_collection_operational_summary(FailingReader())

    assert raised.value is expected


def test_no_argument_path_constructs_and_invokes_default_adapter(monkeypatch):
    expected = summary()
    adapter = Reader(expected)
    constructions = 0

    def construct_adapter():
        nonlocal constructions
        constructions += 1
        return adapter

    monkeypatch.setattr(
        service,
        "ScheduledCollectionOperationalSummaryAdapter",
        construct_adapter,
    )

    actual = service.read_scheduled_collection_operational_summary()

    assert constructions == 1
    assert adapter.calls == 1
    assert actual is expected
