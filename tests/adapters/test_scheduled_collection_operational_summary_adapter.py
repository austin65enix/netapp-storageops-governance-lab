import json
import subprocess
from datetime import datetime, timezone

import pytest

from adapters.scheduled_collection_operational_summary_adapter import (
    CommandResult,
    EvidenceInput,
    ScheduledCollectionOperationalSummaryAdapter,
    SubprocessCommandRunner,
    SYSTEMCTL_TIMEOUT_SECONDS,
)
from models.operational_summary import CollectionHealth


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


class Reader:
    def __init__(self, documents=(), error=None):
        self.documents = documents
        self.error = error

    def read_documents(self):
        if self.error:
            raise self.error
        return self.documents


class Runner:
    def __init__(self, result=None, error=None):
        self.result = result or CommandResult(0, timer_output())
        self.error = error
        self.calls = []

    def run(self, argv, *, env):
        self.calls.append((tuple(argv), env))
        if self.error:
            raise self.error
        return self.result


class FixedClock:
    def __init__(self, value=NOW, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    def now(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


def timer_output(enabled="enabled", active="active", next_value="Fri 2026-08-07 12:15:00 UTC"):
    return (
        f"UnitFileState={enabled}\n"
        f"ActiveState={active}\n"
        f"NextElapseUSecRealtime={next_value}\n"
    )


def evidence(identity, started, completed, result="PASS", code=0, **changes):
    document = {
        "schema_version": 1,
        "execution_id": identity,
        "command": "collect",
        "started_at": started,
        "completed_at": completed,
        "result": result,
        "exit_code": code,
        "data": {
            "execution_id": identity,
            "started_at": started,
            "completed_at": completed,
        },
    }
    document.update(changes)
    return EvidenceInput(f"{identity}.json", json.dumps(document).encode())


def adapter(documents=(), runner=None, clock=None, reader=None):
    return ScheduledCollectionOperationalSummaryAdapter(
        evidence_reader=reader or Reader(documents),
        command_runner=runner or Runner(),
        clock=clock or FixedClock(),
    )


PASS = evidence(
    "collect-z-pass",
    "2026-08-07T11:58:00.000000Z",
    "2026-08-07T11:59:00.000000Z",
)
FAIL_1 = evidence(
    "collect-y-fail",
    "2026-08-07T11:59:10Z",
    "2026-08-07T11:59:20Z",
    "FAIL",
    40,
)
FAIL_2 = evidence(
    "collect-a-fail",
    "2026-08-07T11:59:30Z",
    "2026-08-07T11:59:40Z",
    "FAIL",
    80,
)


def test_healthy_pass_history_and_fixed_clock():
    clock = FixedClock()
    summary = adapter([PASS], clock=clock).read()
    assert summary.collection_health is CollectionHealth.HEALTHY
    assert summary.latest_run_id == "collect-z-pass"
    assert summary.last_success_at == summary.latest_run_completed_at
    assert summary.last_failure_at is None
    assert summary.consecutive_failures == 0
    assert clock.calls == 1


def test_degraded_consecutive_failures_and_history_derivation():
    summary = adapter([FAIL_2, PASS, FAIL_1]).read()
    assert summary.collection_health is CollectionHealth.DEGRADED
    assert summary.latest_run_id == "collect-a-fail"
    assert summary.consecutive_failures == 2
    assert summary.last_success_at.isoformat() == "2026-08-07T11:59:00+00:00"
    assert summary.last_failure_at.isoformat() == "2026-08-07T11:59:40+00:00"


def test_pass_resets_failure_streak_to_zero():
    later_pass = evidence(
        "collect-later-pass", "2026-08-07T11:59:41Z", "2026-08-07T11:59:50Z"
    )
    assert adapter([FAIL_1, later_pass]).read().consecutive_failures == 0


def test_latest_is_selected_by_completed_at_not_filename():
    summary = adapter([PASS, FAIL_2]).read()
    assert summary.latest_run_id == "collect-a-fail"


@pytest.mark.parametrize(
    "bad",
    [
        EvidenceInput("collect-bad.json", b"{"),
        evidence("collect-id", "2026-08-07T11:00:00Z", "2026-08-07T11:01:00Z", execution_id="different"),
        evidence("collect-schema", "2026-08-07T11:00:00Z", "2026-08-07T11:01:00Z", schema_version=2),
        evidence("collect-bool-schema", "2026-08-07T11:00:00Z", "2026-08-07T11:01:00Z", schema_version=True),
        evidence("collect-pass-nonzero", "2026-08-07T11:00:00Z", "2026-08-07T11:01:00Z", code=40),
        evidence("collect-fail-zero", "2026-08-07T11:00:00Z", "2026-08-07T11:01:00Z", result="FAIL", code=0),
        evidence("collect-naive", "2026-08-07T11:00:00", "2026-08-07T11:01:00Z"),
    ],
)
def test_malformed_candidate_invalidates_all_evidence_state(bad):
    summary = adapter([PASS, bad]).read()
    assert summary.latest_run_id is None
    assert summary.consecutive_failures is None
    assert summary.collection_health is CollectionHealth.UNHEALTHY


def test_missing_data_execution_id_invalidates_all_evidence_state():
    document = json.loads(PASS.content)
    del document["data"]["execution_id"]
    missing_identity = EvidenceInput(PASS.name, json.dumps(document).encode())

    summary = adapter([PASS, missing_identity]).read()

    assert summary.latest_run_id is None
    assert summary.latest_run_status is None
    assert summary.latest_run_started_at is None
    assert summary.latest_run_completed_at is None
    assert summary.last_success_at is None
    assert summary.last_failure_at is None
    assert summary.consecutive_failures is None
    assert summary.collection_health is CollectionHealth.UNHEALTHY


def test_ambiguous_equal_latest_completion_times_fail_closed():
    other = evidence(
        "collect-other", "2026-08-07T11:58:30Z", "2026-08-07T11:59:00.000000Z"
    )
    assert adapter([PASS, other]).read().latest_run_id is None


@pytest.mark.parametrize("reader", [Reader(), Reader(error=OSError("unreadable"))])
def test_empty_or_failed_evidence_history_is_unknown(reader):
    summary = adapter(reader=reader).read()
    assert summary.latest_run_id is None
    assert summary.consecutive_failures is None


@pytest.mark.parametrize(
    "output,expected_enabled,expected_active",
    [
        (timer_output(), True, True),
        (timer_output(enabled="disabled"), False, True),
        (timer_output(active="inactive"), True, False),
    ],
)
def test_timer_normalization(output, expected_enabled, expected_active):
    summary = adapter([PASS], runner=Runner(CommandResult(0, output))).read()
    assert summary.timer_enabled is expected_enabled
    assert summary.timer_active is expected_active
    assert summary.next_trigger.tzinfo is timezone.utc


@pytest.mark.parametrize(
    "runner",
    [
        Runner(CommandResult(0, timer_output() + "ActiveState=active\n")),
        Runner(CommandResult(0, "UnitFileState=enabled\nActiveState=active\n")),
        Runner(CommandResult(0, timer_output(next_value="n/a"))),
        Runner(CommandResult(1, "", "failed")),
        Runner(error=OSError("systemctl missing")),
        Runner(error=subprocess.TimeoutExpired(("systemctl", "show"), 5)),
    ],
)
def test_timer_failure_invalidates_entire_timer_state(runner):
    summary = adapter([PASS], runner=runner).read()
    assert summary.timer_enabled is None
    assert summary.timer_active is None
    assert summary.next_trigger is None
    assert summary.collection_health is CollectionHealth.UNHEALTHY


@pytest.mark.parametrize(
    "clock",
    [
        FixedClock(datetime(2026, 8, 7, 12, 0)),
        FixedClock(error=RuntimeError("clock failed")),
    ],
)
def test_invalid_clock_returns_fully_unknown_unhealthy_summary(clock):
    runner = Runner()
    summary = adapter([PASS], runner=runner, clock=clock).read()
    assert summary.collection_health is CollectionHealth.UNHEALTHY
    assert summary.latest_run_id is None
    assert summary.timer_enabled is None
    assert runner.calls == []
    assert clock.calls == 1


def test_systemctl_invocation_is_single_read_only_non_shell_command():
    runner = Runner()
    adapter([PASS], runner=runner).read()
    assert len(runner.calls) == 1
    argv, environment = runner.calls[0]
    assert argv == (
        "systemctl",
        "show",
        "storageops-collect.timer",
        "--property=UnitFileState",
        "--property=ActiveState",
        "--property=NextElapseUSecRealtime",
        "--no-pager",
    )
    assert environment["LC_ALL"] == "C"
    assert not ({"start", "stop", "enable", "disable", "restart", "daemon-reload"} & set(argv))


def test_subprocess_command_runner_bounds_non_shell_execution(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, timer_output(), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter([PASS], runner=SubprocessCommandRunner()).read()

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        "systemctl",
        "show",
        "storageops-collect.timer",
        "--property=UnitFileState",
        "--property=ActiveState",
        "--property=NextElapseUSecRealtime",
        "--no-pager",
    ]
    assert kwargs["env"]["LC_ALL"] == "C"
    assert kwargs["timeout"] == SYSTEMCTL_TIMEOUT_SECONDS
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert "shell" not in kwargs
