from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

from models.operational_summary import (
    CollectionHealth,
    ScheduledCollectionOperationalSummary,
)


CLI_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "storageops-ops"
)


def load_cli_module():
    loader = SourceFileLoader(
        "storageops_ops",
        str(CLI_PATH),
    )

    spec = importlib.util.spec_from_loader(
        loader.name,
        loader,
    )

    assert spec is not None

    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module


def test_version_constant():
    cli = load_cli_module()

    assert cli.VERSION == "0.1.0"


def test_utc_timestamp_format():
    cli = load_cli_module()

    value = cli.utc_timestamp()

    assert len(value) == 16
    assert value.endswith("Z")
    assert "T" in value


def test_status_pass(monkeypatch, capsys):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "service_state",
        lambda name: "active",
    )

    exit_code = cli.command_status("text")
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "COMMAND=status" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_status_service_failure(monkeypatch, capsys):
    cli = load_cli_module()

    def fake_state(name):
        if name == "storageops-api":
            return "inactive"
        return "active"

    monkeypatch.setattr(
        cli,
        "service_state",
        fake_state,
    )

    exit_code = cli.command_status("text")
    output = capsys.readouterr().out

    assert exit_code == 20
    assert "storageops-api=inactive" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=20" in output


def test_health_pass(monkeypatch, capsys):
    cli = load_cli_module()

    responses = {
        cli.API_HEALTH_URL: (
            200,
            {"status": "ok"},
        ),
        cli.ONTAP_CLUSTER_URL: (
            200,
            {"state": "online"},
        ),
    }

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: responses[url],
    )

    exit_code = cli.command_health(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_health_dependency_failure(monkeypatch, capsys):
    cli = load_cli_module()

    responses = {
        cli.API_HEALTH_URL: (
            200,
            {"status": "ok"},
        ),
        cli.ONTAP_CLUSTER_URL: (
            200,
            {"state": "offline"},
        ),
    }

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: responses[url],
    )

    exit_code = cli.command_health(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 40
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=40" in output


def test_json_output_contract(capsys):
    cli = load_cli_module()

    cli.emit_json(
        command="status",
        result="PASS",
        exit_code=0,
        data={"storageops-api": "active"},
        errors=[],
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["command"] == "status"
    assert payload["result"] == "PASS"
    assert payload["exit_code"] == 0
    assert payload["errors"] == []
    assert payload["evidence_file"] is None

def test_collect_pass(monkeypatch, capsys, tmp_path):
    cli = load_cli_module()

    payload = {
        "status": "collected",
        "source": "ONTAP-LAB-01",
        "collected_at": "2026-08-04T07:12:17+00:00",
        "snapshot_file": "/tmp/inventory.json",
        "resource_summary": {
            "volume": 3,
            "lun": 2,
            "snapshot": 3,
        },
        "change_count": 0,
        "changes": [],
        "evidence_file": None,
    }

    monkeypatch.setattr(
        cli,
        "http_post_json",
        lambda url, timeout: (200, payload),
    )

    exit_code = cli.command_collect(
        "text",
        5.0,
        tmp_path,
        True,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "COMMAND=collect" in output
    assert "http_status=200" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_collect_endpoint_failure(monkeypatch, capsys, tmp_path):
    cli = load_cli_module()

    def raise_endpoint_failure(url, timeout):
        raise cli.urllib.error.URLError(
            "connection refused"
        )

    monkeypatch.setattr(
        cli,
        "http_post_json",
        raise_endpoint_failure,
    )

    exit_code = cli.command_collect(
        "text",
        5.0,
        tmp_path,
        True,
    )

    output = capsys.readouterr().out

    assert exit_code == 30
    assert "COMMAND=collect" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=30" in output


def test_collect_invalid_payload(monkeypatch, capsys, tmp_path):
    cli = load_cli_module()

    payload = {
        "status": "failed",
        "snapshot_file": "",
        "resource_summary": None,
        "change_count": -1,
        "changes": None,
    }

    monkeypatch.setattr(
        cli,
        "http_post_json",
        lambda url, timeout: (500, payload),
    )

    exit_code = cli.command_collect(
        "text",
        5.0,
        tmp_path,
        True,
    )

    output = capsys.readouterr().out

    assert exit_code == 40
    assert "http_status=500" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=40" in output


def test_collect_timeout(monkeypatch, capsys, tmp_path):
    cli = load_cli_module()

    def raise_timeout(url, timeout):
        raise TimeoutError(
            "collection deadline exceeded"
        )

    monkeypatch.setattr(
        cli,
        "http_post_json",
        raise_timeout,
    )

    exit_code = cli.command_collect(
        "text",
        0.1,
        tmp_path,
        True,
    )

    output = capsys.readouterr().out

    assert exit_code == 90
    assert "COMMAND=collect" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=90" in output

def valid_capacity_payload():
    return {
        "total_bytes": 1000,
        "used_bytes": 332,
        "available_bytes": 668,
        "utilization_percent": 33.2,
    }


def valid_metric_payload(value="33.203125"):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {},
                    "value": [
                        0,
                        value,
                    ],
                }
            ],
        },
    }


def test_capacity_pass(monkeypatch, capsys):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            valid_capacity_payload(),
        ),
    )

    monkeypatch.setattr(
        cli,
        "prometheus_query",
        lambda expression, timeout: (
            200,
            valid_metric_payload(),
        ),
    )

    exit_code = cli.command_capacity(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "COMMAND=capacity" in output
    assert "metric_http_status=200" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_capacity_invalid_api_payload(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    payload = {
        "total_bytes": 0,
        "used_bytes": -1,
        "available_bytes": -1,
        "utilization_percent": 120,
    }

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (200, payload),
    )

    exit_code = cli.command_capacity(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 40
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=40" in output


def test_capacity_invalid_metric_payload(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            valid_capacity_payload(),
        ),
    )

    monkeypatch.setattr(
        cli,
        "prometheus_query",
        lambda expression, timeout: (
            200,
            {
                "status": "success",
                "data": {
                    "result": [],
                },
            },
        ),
    )

    exit_code = cli.command_capacity(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 50
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=50" in output


def test_capacity_metric_mismatch(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            valid_capacity_payload(),
        ),
    )

    monkeypatch.setattr(
        cli,
        "prometheus_query",
        lambda expression, timeout: (
            200,
            valid_metric_payload("50.0"),
        ),
    )

    exit_code = cli.command_capacity(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 50
    assert "utilization_difference=" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=50" in output

def prometheus_alerts_payload(alerts):
    return {
        "status": "success",
        "data": {
            "alerts": alerts,
        },
    }


def test_alerts_no_active_alerts(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            prometheus_alerts_payload([]),
        ),
    )

    exit_code = cli.command_alerts(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "COMMAND=alerts" in output
    assert "alert_count=0" in output
    assert "pending_count=0" in output
    assert "firing_count=0" in output
    assert "alert_summary=no active alerts" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_alerts_pending(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    alerts = [
        {
            "state": "pending",
            "labels": {
                "alertname": "StorageOpsCapacityHigh",
                "severity": "warning",
            },
            "annotations": {
                "summary": "Capacity is high",
            },
        }
    ]

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            prometheus_alerts_payload(alerts),
        ),
    )

    exit_code = cli.command_alerts(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "alert_count=1" in output
    assert "pending_count=1" in output
    assert "firing_count=0" in output
    assert "alert_summary=pending alerts present" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_alerts_firing(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    alerts = [
        {
            "state": "firing",
            "labels": {
                "alertname": "StorageOpsTargetDown",
                "severity": "critical",
            },
            "annotations": {
                "summary": "StorageOps target is down",
            },
        }
    ]

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            prometheus_alerts_payload(alerts),
        ),
    )

    exit_code = cli.command_alerts(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "alert_count=1" in output
    assert "pending_count=0" in output
    assert "firing_count=1" in output
    assert "alert_summary=firing alerts present" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_alerts_malformed_response(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_json",
        lambda url, timeout: (
            200,
            {
                "status": "success",
                "data": {
                    "alerts": {},
                },
            },
        ),
    )

    exit_code = cli.command_alerts(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 60
    assert "COMMAND=alerts" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=60" in output

def verify_payload(
    command,
    result="PASS",
    exit_code=0,
):
    return {
        "command": command,
        "result": result,
        "exit_code": exit_code,
        "data": {},
        "errors": [],
    }


def test_verify_all_pass(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    def fake_run_verify_check(command, timeout):
        return 0, verify_payload(command)

    monkeypatch.setattr(
        cli,
        "run_verify_check",
        fake_run_verify_check,
    )

    exit_code = cli.command_verify(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "COMMAND=verify" in output
    assert "completed_count=4" in output
    assert "passed_count=4" in output
    assert "required_count=4" in output
    assert "read_only=True" in output
    assert "RESULT=PASS" in output
    assert "EXIT_CODE=0" in output


def test_verify_status_failure(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    def fake_run_verify_check(command, timeout):
        if command == "status":
            return (
                20,
                verify_payload(
                    command,
                    result="FAIL",
                    exit_code=20,
                ),
            )

        raise AssertionError(
            "verify must stop after status failure"
        )

    monkeypatch.setattr(
        cli,
        "run_verify_check",
        fake_run_verify_check,
    )

    exit_code = cli.command_verify(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 20
    assert "completed_count=1" in output
    assert "passed_count=0" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=20" in output


def test_verify_health_failure(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    def fake_run_verify_check(command, timeout):
        if command == "status":
            return 0, verify_payload(command)

        if command == "health":
            return (
                40,
                verify_payload(
                    command,
                    result="FAIL",
                    exit_code=40,
                ),
            )

        raise AssertionError(
            "verify must stop after health failure"
        )

    monkeypatch.setattr(
        cli,
        "run_verify_check",
        fake_run_verify_check,
    )

    exit_code = cli.command_verify(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 40
    assert "completed_count=2" in output
    assert "passed_count=1" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=40" in output


def test_verify_capacity_failure(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()

    def fake_run_verify_check(command, timeout):
        if command in {
            "status",
            "health",
        }:
            return 0, verify_payload(command)

        if command == "capacity":
            return (
                50,
                verify_payload(
                    command,
                    result="FAIL",
                    exit_code=50,
                ),
            )

        raise AssertionError(
            "verify must stop after capacity failure"
        )

    monkeypatch.setattr(
        cli,
        "run_verify_check",
        fake_run_verify_check,
    )

    exit_code = cli.command_verify(
        "text",
        5.0,
    )

    output = capsys.readouterr().out

    assert exit_code == 50
    assert "completed_count=3" in output
    assert "passed_count=2" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=50" in output

def test_generate_execution_id():
    cli = load_cli_module()

    execution_id = cli.generate_execution_id(
        "collect"
    )

    parts = execution_id.split("-")

    assert parts[0] == "collect"
    assert len(parts) == 3
    assert parts[1].endswith("Z")
    assert len(parts[2]) == 8
    assert parts[2].isalnum()


def test_build_evidence_document():
    cli = load_cli_module()

    document = cli.build_evidence_document(
        execution_id="collect-test-12345678",
        command="collect",
        started_at="2026-08-04T08:20:00Z",
        completed_at="2026-08-04T08:20:01Z",
        result="PASS",
        exit_code=0,
        data={"status": "collected"},
        errors=[],
        evidence_file="/tmp/evidence.json",
    )

    assert document == {
        "schema_version": 1,
        "execution_id": "collect-test-12345678",
        "command": "collect",
        "started_at": "2026-08-04T08:20:00Z",
        "completed_at": "2026-08-04T08:20:01Z",
        "result": "PASS",
        "exit_code": 0,
        "data": {
            "status": "collected",
        },
        "errors": [],
        "evidence_file": "/tmp/evidence.json",
    }


def test_write_evidence_atomic(tmp_path):
    cli = load_cli_module()

    execution_id = (
        "collect-20260804T082000Z-12345678"
    )

    expected_path = (
        tmp_path
        / f"{execution_id}.json"
    )

    document = cli.build_evidence_document(
        execution_id=execution_id,
        command="collect",
        started_at="2026-08-04T08:20:00Z",
        completed_at="2026-08-04T08:20:01Z",
        result="PASS",
        exit_code=0,
        data={"status": "collected"},
        errors=[],
        evidence_file=str(expected_path),
    )

    actual_path = cli.write_evidence_atomic(
        tmp_path,
        execution_id,
        document,
    )

    assert actual_path == expected_path
    assert actual_path.is_file()

    payload = json.loads(
        actual_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload == document

    temporary_files = list(
        tmp_path.glob("*.tmp")
    )

    assert temporary_files == []

def collect_success_payload_for_evidence():
    return {
        "status": "collected",
        "source": "ONTAP-LAB-01",
        "collected_at": "2026-08-04T08:30:00+00:00",
        "snapshot_file": "/tmp/inventory.json",
        "resource_summary": {
            "volume": 3,
            "lun": 2,
            "snapshot": 3,
        },
        "change_count": 0,
        "changes": [],
        "evidence_file": None,
    }


def test_collect_writes_runtime_evidence(
    monkeypatch,
    capsys,
    tmp_path,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_post_json",
        lambda url, timeout: (
            200,
            collect_success_payload_for_evidence(),
        ),
    )

    evidence_dir = (
        tmp_path
        / "custom-runtime-evidence"
    )

    exit_code = cli.command_collect(
        "json",
        5.0,
        evidence_dir,
        False,
    )

    output = capsys.readouterr().out
    response = json.loads(output)

    assert exit_code == 0
    assert response["command"] == "collect"
    assert response["result"] == "PASS"
    assert response["exit_code"] == 0

    evidence_file = response["evidence_file"]

    assert isinstance(evidence_file, str)
    assert evidence_file

    evidence_path = Path(evidence_file)

    assert evidence_path.parent == evidence_dir
    assert evidence_path.is_file()

    document = json.loads(
        evidence_path.read_text(
            encoding="utf-8"
        )
    )

    assert document["schema_version"] == 1
    assert document["command"] == "collect"
    assert document["result"] == "PASS"
    assert document["exit_code"] == 0
    assert document["errors"] == []
    assert document["evidence_file"] == evidence_file

    execution_id = document["execution_id"]

    assert execution_id.startswith("collect-")
    assert evidence_path.name == (
        execution_id + ".json"
    )

    assert document["started_at"]
    assert document["completed_at"]

    assert (
        document["data"]["execution_id"]
        == execution_id
    )

    assert not list(
        evidence_dir.glob("*.tmp")
    )


def test_collect_no_evidence_suppresses_file(
    monkeypatch,
    capsys,
    tmp_path,
):
    cli = load_cli_module()

    monkeypatch.setattr(
        cli,
        "http_post_json",
        lambda url, timeout: (
            200,
            collect_success_payload_for_evidence(),
        ),
    )

    evidence_dir = (
        tmp_path
        / "suppressed-evidence"
    )

    exit_code = cli.command_collect(
        "json",
        5.0,
        evidence_dir,
        True,
    )

    output = capsys.readouterr().out
    response = json.loads(output)

    assert exit_code == 0
    assert response["result"] == "PASS"
    assert response["exit_code"] == 0
    assert response["evidence_file"] is None
    assert not evidence_dir.exists()


def test_collect_evidence_write_failure(
    monkeypatch, capsys, tmp_path,
):
    cli = load_cli_module()
    lock_file = tmp_path / "storageops-collect.lock"
    runtime_evidence = tmp_path / "runtime-evidence"
    runtime_evidence.mkdir()
    existing_evidence = runtime_evidence / "collect-existing.json"
    existing_content = "{\"preserve\": true}\n"
    existing_evidence.write_text(existing_content, encoding="utf-8")
    http_dispatches = []

    def successful_collection(url, timeout):
        http_dispatches.append((url, timeout))
        return 200, collect_success_payload_for_evidence()

    monkeypatch.setattr(cli, "http_post_json", successful_collection)

    def raise_write_failure(evidence_dir, execution_id, document):
        raise PermissionError("evidence directory is read-only")

    monkeypatch.setattr(cli, "write_evidence_atomic", raise_write_failure)
    exit_code = cli.command_collect(
        "text", 5.0, runtime_evidence, False, lock_file
    )
    output = capsys.readouterr().out

    assert exit_code == cli.EXIT_EVIDENCE_WRITE_FAILURE == 70
    assert len(http_dispatches) == 1
    assert "COMMAND=collect" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=70" in output
    assert (
        "ERROR=evidence write failed: evidence directory is read-only"
        in output
    )
    assert existing_evidence.read_text(encoding="utf-8") == existing_content
    assert list(runtime_evidence.iterdir()) == [existing_evidence]

    recovered_handle = cli.acquire_nonblocking_lock(lock_file)
    assert recovered_handle is not None
    cli.release_lock(recovered_handle)

    monkeypatch.undo()
    cli = load_cli_module()
    monkeypatch.setattr(cli, "http_post_json", successful_collection)
    recovery_exit_code = cli.command_collect(
        "text", 5.0, runtime_evidence, False, lock_file
    )
    recovery_output = capsys.readouterr().out
    assert recovery_exit_code == 0
    assert "RESULT=PASS" in recovery_output
    assert "EXIT_CODE=0" in recovery_output
    assert len(http_dispatches) == 2
    assert existing_evidence.read_text(encoding="utf-8") == existing_content


def test_acquire_and_release_collect_lock(
    tmp_path,
):
    cli = load_cli_module()

    lock_file = (
        tmp_path
        / "storageops-collect.lock"
    )

    handle = cli.acquire_nonblocking_lock(
        lock_file
    )

    assert handle is not None
    assert lock_file.is_file()

    content = lock_file.read_text(
        encoding="utf-8"
    )

    assert "pid=" in content
    assert "acquired_at=" in content

    cli.release_lock(handle)

    second_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert second_handle is not None

    cli.release_lock(second_handle)


def test_collect_lock_contention(
    tmp_path,
):
    cli = load_cli_module()

    lock_file = (
        tmp_path
        / "storageops-collect.lock"
    )

    first_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert first_handle is not None

    second_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert second_handle is None

    cli.release_lock(first_handle)

    recovered_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert recovered_handle is not None

    cli.release_lock(recovered_handle)


def test_collect_lock_contention_with_external_holder(
    monkeypatch,
    capsys,
    tmp_path,
):
    cli = load_cli_module()
    lock_file = tmp_path / "storageops-collect.lock"
    holder_source = """
import fcntl
import pathlib
import sys
with pathlib.Path(sys.argv[1]).open("a+") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("READY", flush=True)
    sys.stdin.read()
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", holder_source, str(lock_file)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    def unexpected_collection_request(url, timeout):
        raise AssertionError(
            "http_post_json must be unreachable "
            "during external lock contention"
        )

    monkeypatch.setattr(
        cli,
        "http_post_json",
        unexpected_collection_request,
    )

    try:
        assert process.stdout.readline().strip() == "READY"
        exit_code = cli.command_collect(
            "text", 5.0, tmp_path / "evidence", True, lock_file
        )
    finally:
        process.communicate(timeout=5)

    output = capsys.readouterr().out
    assert exit_code == 80
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=80" in output
    assert "collection lock is already held" in output

    recovered_handle = cli.acquire_nonblocking_lock(lock_file)
    assert recovered_handle is not None
    cli.release_lock(recovered_handle)


def test_collect_command_lock_contention(
    monkeypatch,
    capsys,
    tmp_path,
):
    cli = load_cli_module()

    lock_file = (
        tmp_path
        / "storageops-collect.lock"
    )

    first_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert first_handle is not None

    def unexpected_collection_request(
        url,
        timeout,
    ):
        raise AssertionError(
            "collection request must not be sent "
            "during lock contention"
        )

    monkeypatch.setattr(
        cli,
        "http_post_json",
        unexpected_collection_request,
    )

    try:
        exit_code = cli.command_collect(
            "text",
            5.0,
            tmp_path / "evidence",
            True,
            lock_file,
        )
    finally:
        cli.release_lock(first_handle)

    output = capsys.readouterr().out

    assert exit_code == 80
    assert "COMMAND=collect" in output
    assert "RESULT=FAIL" in output
    assert "EXIT_CODE=80" in output
    assert (
        "ERROR=collection lock is already held:"
        in output
    )


def test_collect_releases_lock_after_failure(
    monkeypatch,
    capsys,
    tmp_path,
):
    cli = load_cli_module()

    lock_file = (
        tmp_path
        / "storageops-collect.lock"
    )

    def raise_endpoint_failure(
        url,
        timeout,
    ):
        raise cli.urllib.error.URLError(
            "connection refused"
        )

    monkeypatch.setattr(
        cli,
        "http_post_json",
        raise_endpoint_failure,
    )

    first_exit_code = cli.command_collect(
        "text",
        5.0,
        tmp_path / "evidence",
        True,
        lock_file,
    )

    capsys.readouterr()

    assert first_exit_code == 30

    recovered_handle = (
        cli.acquire_nonblocking_lock(
            lock_file
        )
    )

    assert recovered_handle is not None

    cli.release_lock(recovered_handle)


def collection_summary(health=CollectionHealth.HEALTHY):
    eastern = timezone(timedelta(hours=-4))
    return ScheduledCollectionOperationalSummary(
        latest_run_id="collect-20260810T115800Z-ab12cd34",
        latest_run_status="PASS",
        latest_run_started_at=datetime(2026, 8, 10, 7, 58, tzinfo=eastern),
        latest_run_completed_at=datetime(2026, 8, 10, 7, 59, tzinfo=eastern),
        last_success_at=datetime(2026, 8, 10, 7, 59, tzinfo=eastern),
        last_failure_at=None,
        consecutive_failures=0,
        timer_enabled=True,
        timer_active=True,
        next_trigger=datetime(2026, 8, 10, 8, 5, tzinfo=eastern),
        collection_health=health,
    )


def test_collection_summary_parser_accepts_command():
    cli = load_cli_module()
    args = cli.build_parser().parse_args(["collection-summary"])
    assert args.command == "collection-summary"


def test_collection_summary_main_dispatches(monkeypatch):
    cli = load_cli_module()
    calls = []
    monkeypatch.setattr(
        cli,
        "command_collection_summary",
        lambda output_format: calls.append(output_format) or 17,
    )
    monkeypatch.setattr(sys, "argv", ["storageops-ops", "collection-summary"])
    assert cli.main() == 17
    assert calls == ["text"]


def test_collection_summary_text_fields_are_ordered(monkeypatch, capsys):
    cli = load_cli_module()
    calls = 0

    def read_summary():
        nonlocal calls
        calls += 1
        return collection_summary()

    monkeypatch.setattr(
        cli,
        "read_scheduled_collection_operational_summary",
        read_summary,
    )
    assert cli.command_collection_summary("text") == 0
    lines = capsys.readouterr().out.splitlines()
    field_names = [line.split("=", 1)[0] for line in lines[2:-2]]
    assert calls == 1
    assert field_names == [
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
    ]
    assert "latest_run_started_at=2026-08-10T11:58:00Z" in lines
    assert "last_failure_at=None" in lines
    assert "timer_enabled=True" in lines
    assert "collection_health=HEALTHY" in lines
    assert lines[-2:] == ["RESULT=PASS", "EXIT_CODE=0"]


def test_collection_summary_json_exact_shape(monkeypatch, capsys):
    cli = load_cli_module()
    monkeypatch.setattr(
        cli,
        "read_scheduled_collection_operational_summary",
        collection_summary,
    )
    assert cli.command_collection_summary("json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "1"
    assert payload["command"] == "collection-summary"
    assert payload["result"] == "PASS"
    assert payload["exit_code"] == 0
    assert payload["errors"] == []
    assert payload["evidence_file"] is None
    assert payload["data"] == {
        "latest_run_id": "collect-20260810T115800Z-ab12cd34",
        "latest_run_status": "PASS",
        "latest_run_started_at": "2026-08-10T11:58:00Z",
        "latest_run_completed_at": "2026-08-10T11:59:00Z",
        "last_success_at": "2026-08-10T11:59:00Z",
        "last_failure_at": None,
        "consecutive_failures": 0,
        "timer_enabled": True,
        "timer_active": True,
        "next_trigger": "2026-08-10T12:05:00Z",
        "collection_health": "HEALTHY",
    }
    assert set(payload["data"]) == {
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


def test_collection_summary_health_states_are_informational(monkeypatch, capsys):
    cli = load_cli_module()
    for health in CollectionHealth:
        monkeypatch.setattr(
            cli,
            "read_scheduled_collection_operational_summary",
            lambda health=health: collection_summary(health),
        )
        assert cli.command_collection_summary("json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["contract_version"] == "1"
        assert payload["result"] == "PASS"
        assert payload["exit_code"] == 0
        assert payload["data"]["collection_health"] == health.value


def test_collection_summary_serialization_failure(monkeypatch, capsys):
    cli = load_cli_module()
    unserializable = replace(collection_summary(), latest_run_id=object())
    monkeypatch.setattr(
        cli,
        "read_scheduled_collection_operational_summary",
        lambda: unserializable,
    )
    assert cli.command_collection_summary("json") == cli.EXIT_UNEXPECTED
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "1"
    assert payload["result"] == "FAIL"
    assert payload["exit_code"] == cli.EXIT_UNEXPECTED
    assert payload["data"] == {}
    assert payload["errors"][0].startswith(
        "operational summary inspection failed: "
    )


def test_collection_summary_unexpected_failure(monkeypatch, capsys):
    cli = load_cli_module()

    def fail():
        raise RuntimeError("reader failed\nwith internal context")

    monkeypatch.setattr(
        cli,
        "read_scheduled_collection_operational_summary",
        fail,
    )
    assert cli.command_collection_summary("json") == cli.EXIT_UNEXPECTED
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "1"
    assert payload["result"] == "FAIL"
    assert payload["exit_code"] == cli.EXIT_UNEXPECTED
    assert payload["data"] == {}
    assert payload["errors"] == [
        "operational summary inspection failed: "
        "reader failed with internal context"
    ]
    assert payload["evidence_file"] is None


def test_collection_summary_does_not_bypass_service_or_write_evidence(
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    source = CLI_PATH.read_text(encoding="utf-8")
    assert "ScheduledCollectionOperationalSummaryAdapter" not in source
    monkeypatch.setattr(
        cli,
        "read_scheduled_collection_operational_summary",
        collection_summary,
    )
    monkeypatch.setattr(
        cli,
        "write_evidence_atomic",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("evidence writer must not be invoked")
        ),
    )
    assert cli.command_collection_summary("json") == 0
    assert json.loads(capsys.readouterr().out)["evidence_file"] is None
