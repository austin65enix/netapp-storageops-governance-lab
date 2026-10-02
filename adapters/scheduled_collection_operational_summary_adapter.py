"""Read-only adapter for scheduled collection operational state.

Runtime JSON describes only observable evidence. In particular, an evidence-write
failure may leave no document, manual and scheduled collection are not
distinguishable, and alternate ``--evidence-dir`` histories are out of scope.
Timer NEXT parsing is intentionally limited to the tested ``LC_ALL=C`` systemd
timestamp form.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from models.operational_summary import ScheduledCollectionOperationalSummary


DEFAULT_EVIDENCE_DIR = Path(
    "/opt/netapp-storageops-lab/evidence/runtime"
)
DEFAULT_TIMER_UNIT = "storageops-collect.timer"
SYSTEMCTL_TIMEOUT_SECONDS = 5
_EVIDENCE_NAME = re.compile(r"collect-.+\.json\Z")
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\Z"
)
_SYSTEMD_NEXT = re.compile(
    r"[A-Z][a-z]{2} \d{4}-\d{2}-\d{2} "
    r"\d{2}:\d{2}:\d{2} UTC\Z"
)
_NON_ENABLED_STATES = {
    "disabled",
    "masked",
    "masked-runtime",
    "static",
    "indirect",
    "generated",
    "transient",
    "linked",
    "linked-runtime",
    "alias",
    "bad",
}
_NON_ACTIVE_STATES = {
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "reloading",
    "maintenance",
}
_FALLBACK_NOW = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class EvidenceInput:
    name: str
    content: bytes


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


class EvidenceReader(Protocol):
    def read_documents(self) -> Sequence[EvidenceInput]: ...


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
    ) -> CommandResult: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class FileSystemEvidenceReader:
    """Read existing collect evidence without creating or changing anything."""

    def __init__(self, evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> None:
        self.evidence_dir = Path(evidence_dir)

    def read_documents(self) -> Sequence[EvidenceInput]:
        documents = []
        for path in self.evidence_dir.iterdir():
            if not _EVIDENCE_NAME.fullmatch(path.name):
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"evidence candidate is not a regular file: {path}")
            documents.append(EvidenceInput(path.name, path.read_bytes()))
        return documents


class SubprocessCommandRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
    ) -> CommandResult:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=SYSTEMCTL_TIMEOUT_SECONDS,
        )
        return CommandResult(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Run:
    execution_id: str
    result: str
    started_at: datetime
    completed_at: datetime


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        raise ValueError("timestamp is not strict UTC Z form")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp is not UTC")
    return parsed


def _parse_evidence(item: EvidenceInput) -> _Run:
    try:
        text = item.content.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid evidence document") from exc

    if not isinstance(document, dict):
        raise ValueError("evidence root is not an object")
    schema_version = document.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise ValueError("unsupported schema_version")
    if document.get("command") != "collect":
        raise ValueError("evidence command is not collect")

    execution_id = document.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ValueError("invalid execution identity")
    if item.name != f"{execution_id}.json":
        raise ValueError("filename contradicts execution identity")
    data = document.get("data")
    if not isinstance(data, dict):
        raise ValueError("evidence data is not an object")
    if data.get("execution_id") != execution_id:
        raise ValueError("data contradicts execution identity")

    result = document.get("result")
    exit_code = document.get("exit_code")
    if result not in {"PASS", "FAIL"}:
        raise ValueError("invalid evidence result")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise ValueError("invalid evidence exit_code")
    if (result == "PASS" and exit_code != 0) or (
        result == "FAIL" and exit_code == 0
    ):
        raise ValueError("result and exit_code contradict")

    started_at = _parse_utc(document.get("started_at"))
    completed_at = _parse_utc(document.get("completed_at"))
    if started_at > completed_at:
        raise ValueError("evidence timestamps are reversed")
    for key, authoritative in (
        ("started_at", started_at),
        ("completed_at", completed_at),
    ):
        if key in data and _parse_utc(data[key]) != authoritative:
            raise ValueError(f"data {key} contradicts top-level value")

    return _Run(execution_id, result, started_at, completed_at)


def _evidence_state(reader: EvidenceReader) -> dict[str, object | None]:
    unknown = {
        "latest_run_id": None,
        "latest_run_status": None,
        "latest_run_started_at": None,
        "latest_run_completed_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "consecutive_failures": None,
    }
    try:
        runs = [_parse_evidence(item) for item in reader.read_documents()]
        if not runs:
            return unknown
        runs.sort(key=lambda run: run.completed_at, reverse=True)
        latest_time = runs[0].completed_at
        latest_ids = {
            run.execution_id for run in runs if run.completed_at == latest_time
        }
        if len(latest_ids) != 1:
            return unknown
    except Exception:
        return unknown

    latest = runs[0]
    last_success = next(
        (run.completed_at for run in runs if run.result == "PASS"), None
    )
    last_failure = next(
        (run.completed_at for run in runs if run.result == "FAIL"), None
    )
    failures = 0
    for run in runs:
        if run.result == "PASS":
            break
        failures += 1
    return {
        "latest_run_id": latest.execution_id,
        "latest_run_status": latest.result,
        "latest_run_started_at": latest.started_at,
        "latest_run_completed_at": latest.completed_at,
        "last_success_at": last_success,
        "last_failure_at": last_failure,
        "consecutive_failures": failures,
    }


def _timer_state(
    runner: CommandRunner,
    timer_unit: str,
) -> dict[str, object | None]:
    unknown = {
        "timer_enabled": None,
        "timer_active": None,
        "next_trigger": None,
    }
    argv = (
        "systemctl",
        "show",
        timer_unit,
        "--property=UnitFileState",
        "--property=ActiveState",
        "--property=NextElapseUSecRealtime",
        "--no-pager",
    )
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    try:
        result = runner.run(argv, env=environment)
        if result.returncode != 0:
            return unknown
        properties: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                raise ValueError("malformed systemd property")
            key, value = line.split("=", 1)
            if key in properties:
                raise ValueError("duplicate systemd property")
            properties[key] = value
        required = {
            "UnitFileState",
            "ActiveState",
            "NextElapseUSecRealtime",
        }
        if set(properties) != required:
            return unknown

        unit_state = properties["UnitFileState"]
        active_state = properties["ActiveState"]
        if unit_state == "enabled":
            enabled = True
        elif unit_state in _NON_ENABLED_STATES:
            enabled = False
        else:
            return unknown
        if active_state == "active":
            active = True
        elif active_state in _NON_ACTIVE_STATES:
            active = False
        else:
            return unknown

        next_value = properties["NextElapseUSecRealtime"]
        if not _SYSTEMD_NEXT.fullmatch(next_value):
            return unknown
        next_trigger = datetime.strptime(
            next_value, "%a %Y-%m-%d %H:%M:%S UTC"
        ).replace(tzinfo=timezone.utc)
    except Exception:
        return unknown
    return {
        "timer_enabled": enabled,
        "timer_active": active,
        "next_trigger": next_trigger,
    }


class ScheduledCollectionOperationalSummaryAdapter:
    def __init__(
        self,
        *,
        evidence_reader: EvidenceReader | None = None,
        command_runner: CommandRunner | None = None,
        clock: Clock | None = None,
        timer_unit: str = DEFAULT_TIMER_UNIT,
    ) -> None:
        self.evidence_reader = evidence_reader or FileSystemEvidenceReader()
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.clock = clock or SystemClock()
        self.timer_unit = timer_unit

    def read(self) -> ScheduledCollectionOperationalSummary:
        try:
            now = self.clock.now()
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() is None
            ):
                raise ValueError("clock must return an aware datetime")
        except Exception:
            return ScheduledCollectionOperationalSummary.from_state(
                latest_run_id=None,
                latest_run_status=None,
                latest_run_started_at=None,
                latest_run_completed_at=None,
                last_success_at=None,
                last_failure_at=None,
                consecutive_failures=None,
                timer_enabled=None,
                timer_active=None,
                next_trigger=None,
                now=_FALLBACK_NOW,
            )

        state = _evidence_state(self.evidence_reader)
        state.update(_timer_state(self.command_runner, self.timer_unit))
        return ScheduledCollectionOperationalSummary.from_state(
            **state,
            now=now,
        )
