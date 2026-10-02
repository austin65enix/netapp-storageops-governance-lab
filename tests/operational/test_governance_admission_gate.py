from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

GATE_PATH = (
    REPO_ROOT
    / "scripts"
    / "check_governance_admission.py"
)

spec = importlib.util.spec_from_file_location(
    "storageops_governance_admission_gate",
    GATE_PATH,
)

assert spec is not None
assert spec.loader is not None

gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


FIXED_NOW = datetime(
    2026,
    8,
    28,
    4,
    0,
    0,
    tzinfo=timezone.utc,
)


def utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def write_json(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def mutate(path: Path, function) -> None:
    document = read_json(path)
    function(document)
    write_json(path, document)


def build_chain(
    tmp_path: Path,
    *,
    now: datetime = FIXED_NOW,
) -> dict[str, Path]:
    decision_path = tmp_path / "decision.json"
    admission_path = tmp_path / "admission.json"

    decision = {
        "schema_version": 1,
        "enforcement_id": "ENF-R31-001",
        "decision_id": "DEC-R31-001",
        "policy_evaluation_id": "POL-R31-001",
        "certification_id": "CERT-R31-001",
        "lineage_id": "LIN-R31-001",
        "subject_identity": "storageops-agent",
        "action": "collect",
        "scope": {
            "target": "netapp-lab",
        },
        "enforcement_state": "ACCEPTED",
        "created_at": utc_text(
            now - timedelta(minutes=10)
        ),
        "evidence_reference": "reference:r31:decision",
    }

    admission = {
        "schema_version": 1,
        "admission_id": "ADM-R31-001",
        "execution_request_id": "REQ-R31-001",
        "decision_enforcement_id": "ENF-R31-001",
        "certification_id": "CERT-R31-001",
        "lineage_id": "LIN-R31-001",
        "subject_identity": "storageops-agent",
        "action": "collect",
        "scope": {
            "target": "netapp-lab",
        },
        "runtime_target": "storageops-collect",
        "admission_state": "ADMITTED",
        "created_at": utc_text(
            now - timedelta(minutes=5)
        ),
        "expires_at": utc_text(
            now + timedelta(minutes=10)
        ),
        "evidence_reference": "reference:r31:admission",
    }

    write_json(decision_path, decision)
    write_json(admission_path, admission)

    return {
        "decision": decision_path,
        "admission": admission_path,
    }


def expected_context() -> dict:
    return {
        "expected_enforcement_id": "ENF-R31-001",
        "expected_admission_id": "ADM-R31-001",
        "expected_execution_request_id": "REQ-R31-001",
        "expected_certification_id": "CERT-R31-001",
        "expected_lineage_id": "LIN-R31-001",
        "expected_subject_identity": "storageops-agent",
        "expected_action": "collect",
        "expected_runtime_target": "storageops-collect",
        "expected_scope": {
            "target": "netapp-lab",
        },
    }


def evaluate(
    chain: dict[str, Path],
    *,
    evaluation_time: datetime = FIXED_NOW,
    **overrides,
):
    context = expected_context()
    context.update(overrides)

    return gate.evaluate_pre_execution_admission(
        decision_path=chain["decision"],
        admission_path=chain["admission"],
        evaluation_time=evaluation_time,
        **context,
    )


def build_current_chain(
    tmp_path: Path,
) -> dict[str, Path]:
    now = datetime.now(timezone.utc)
    return build_chain(tmp_path, now=now)


def cli_argv(
    chain: dict[str, Path],
    *,
    expected_scope_json: str = '{"target":"netapp-lab"}',
) -> list[str]:
    return [
        str(GATE_PATH),
        "--decision-enforcement",
        str(chain["decision"]),
        "--authorization-admission",
        str(chain["admission"]),
        "--expected-enforcement-id",
        "ENF-R31-001",
        "--expected-admission-id",
        "ADM-R31-001",
        "--expected-execution-request-id",
        "REQ-R31-001",
        "--expected-certification-id",
        "CERT-R31-001",
        "--expected-lineage-id",
        "LIN-R31-001",
        "--expected-subject-identity",
        "storageops-agent",
        "--expected-action",
        "collect",
        "--expected-runtime-target",
        "storageops-collect",
        "--expected-scope-json",
        expected_scope_json,
    ]


def test_valid_exact_context_allows(tmp_path):
    chain = build_chain(tmp_path)

    result = evaluate(chain)

    assert result["decision_enforcement_id"] == "ENF-R31-001"
    assert result["admission_id"] == "ADM-R31-001"
    assert result["execution_request_id"] == "REQ-R31-001"
    assert result["lineage_id"] == "LIN-R31-001"
    assert result["action"] == "collect"
    assert result["runtime_target"] == "storageops-collect"


def test_cli_valid_exact_context_allows(
    tmp_path,
    monkeypatch,
    capsys,
):
    chain = build_current_chain(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        cli_argv(chain),
    )

    assert gate.main() == 0

    output = capsys.readouterr().out

    assert "PRE_DISPATCH_RESULT=ALLOW" in output
    assert "SCHEMA_VALIDATION=PASS" in output
    assert "DECISION_ENFORCEMENT_VALIDATION=PASS" in output
    assert "AUTHORIZATION_ADMISSION_VALIDATION=PASS" in output
    assert "EXPECTED_CONTEXT_BINDING=PASS" in output
    assert "TEMPORAL_VALIDITY=PASS" in output


def test_decision_not_accepted_denies(tmp_path):
    chain = build_chain(tmp_path)

    mutate(
        chain["decision"],
        lambda document: document.update(
            {"enforcement_state": "HOLD"}
        ),
    )

    with pytest.raises(
        gate.AdmissionFailure,
        match="decision enforcement is not ACCEPTED",
    ):
        evaluate(chain)


@pytest.mark.parametrize(
    ("state", "extra"),
    [
        ("PENDING", {}),
        (
            "DENIED",
            {
                "reason_code": "POLICY_VIOLATION",
            },
        ),
    ],
)
def test_non_admitted_states_deny(
    tmp_path,
    state,
    extra,
):
    chain = build_chain(tmp_path)

    def change(document):
        document["admission_state"] = state
        document.update(extra)

    mutate(chain["admission"], change)

    with pytest.raises(
        gate.AdmissionFailure,
        match="authorization admission is not ADMITTED",
    ):
        evaluate(chain)


@pytest.mark.parametrize(
    ("decision_delta", "admission_delta", "expiry_delta", "message"),
    [
        (
            timedelta(minutes=-10),
            timedelta(minutes=-8),
            timedelta(minutes=-1),
            "admission has expired",
        ),
        (
            timedelta(minutes=-10),
            timedelta(minutes=1),
            timedelta(minutes=10),
            "admission is not yet effective",
        ),
        (
            timedelta(minutes=-4),
            timedelta(minutes=-5),
            timedelta(minutes=10),
            "admission predates decision enforcement",
        ),
        (
            timedelta(minutes=-10),
            timedelta(minutes=-5),
            timedelta(minutes=-6),
            "admission expires before it is created",
        ),
    ],
)
def test_temporal_admission_failures_deny(
    tmp_path,
    decision_delta,
    admission_delta,
    expiry_delta,
    message,
):
    chain = build_chain(tmp_path)

    mutate(
        chain["decision"],
        lambda document: document.update(
            {
                "created_at": utc_text(
                    FIXED_NOW + decision_delta
                )
            }
        ),
    )

    mutate(
        chain["admission"],
        lambda document: document.update(
            {
                "created_at": utc_text(
                    FIXED_NOW + admission_delta
                ),
                "expires_at": utc_text(
                    FIXED_NOW + expiry_delta
                ),
            }
        ),
    )

    with pytest.raises(
        gate.AdmissionFailure,
        match=message,
    ):
        evaluate(chain)


@pytest.mark.parametrize(
    ("override", "value", "message"),
    [
        (
            "expected_enforcement_id",
            "ENF-OTHER",
            "decision enforcement identity mismatch",
        ),
        (
            "expected_admission_id",
            "ADM-OTHER",
            "admission identity mismatch",
        ),
        (
            "expected_execution_request_id",
            "REQ-OTHER",
            "execution request identity mismatch",
        ),
        (
            "expected_certification_id",
            "CERT-OTHER",
            "certification identity mismatch",
        ),
        (
            "expected_lineage_id",
            "LIN-OTHER",
            "lineage identity mismatch",
        ),
        (
            "expected_subject_identity",
            "other-agent",
            "subject identity mismatch",
        ),
        (
            "expected_action",
            "capacity",
            "action identity mismatch",
        ),
        (
            "expected_scope",
            {"target": "other-target"},
            "scope mismatch",
        ),
        (
            "expected_runtime_target",
            "other-runtime",
            "runtime target mismatch",
        ),
    ],
)
def test_expected_context_mismatch_denies(
    tmp_path,
    override,
    value,
    message,
):
    chain = build_chain(tmp_path)

    with pytest.raises(
        gate.BindingFailure,
        match=message,
    ):
        evaluate(
            chain,
            **{
                override: value,
            },
        )


@pytest.mark.parametrize(
    ("target", "field", "message"),
    [
        (
            "decision",
            "decision_id",
            r"\$\.decision_id is required",
        ),
        (
            "admission",
            "admission_id",
            r"\$\.admission_id is required",
        ),
    ],
)
def test_malformed_governance_artifact_denies(
    tmp_path,
    target,
    field,
    message,
):
    chain = build_chain(tmp_path)

    mutate(
        chain[target],
        lambda document: document.pop(field),
    )

    with pytest.raises(
        gate.SchemaFailure,
        match=message,
    ):
        evaluate(chain)


def test_cli_invalid_expected_scope_fails_closed(
    tmp_path,
    monkeypatch,
    capsys,
):
    chain = build_current_chain(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        cli_argv(
            chain,
            expected_scope_json="not-json",
        ),
    )

    assert gate.main() == 1

    output = capsys.readouterr().out

    assert "PRE_DISPATCH_RESULT=DENY" in output
    assert "FAILURE_KIND=ADMISSION" in output
    assert "ERROR=expected scope is not valid JSON" in output
