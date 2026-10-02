from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_governance_lineage.py"


spec = importlib.util.spec_from_file_location(
    "storageops_governance_lineage_validator",
    VALIDATOR_PATH,
)

assert spec is not None
assert spec.loader is not None

validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


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
    return json.loads(path.read_text(encoding="utf-8"))


def mutate(path: Path, function) -> None:
    document = read_json(path)
    function(document)
    write_json(path, document)


def build_valid_chain(tmp_path: Path) -> dict[str, Path]:
    runtime = tmp_path / "collect-r28-valid.json"

    runtime_document = {
        "command": "collect",
        "schema_version": 1,
        "execution_id": "collect-r28-valid",
        "data": {
            "execution_id": "collect-r28-valid",
            "started_at": "2026-08-28T03:02:00Z",
            "completed_at": "2026-08-28T03:03:00Z",
        },
        "result": "PASS",
        "exit_code": 0,
        "errors": [],
        "evidence_file": str(runtime),
    }

    write_json(runtime, runtime_document)

    digest = hashlib.sha256(runtime.read_bytes()).hexdigest()

    decision = tmp_path / "decision.json"

    write_json(
        decision,
        {
            "schema_version": 1,
            "enforcement_id": "ENF-R28-001",
            "decision_id": "DEC-R28-001",
            "policy_evaluation_id": "POL-R28-001",
            "certification_id": "CERT-R28-001",
            "lineage_id": "LIN-R28-001",
            "subject_identity": "storageops-agent",
            "action": "collect",
            "scope": {
                "target": "netapp-lab",
            },
            "enforcement_state": "ACCEPTED",
            "created_at": "2026-08-28T03:00:00Z",
            "evidence_reference": "reference:r28:decision",
        },
    )

    admission = tmp_path / "admission.json"

    write_json(
        admission,
        {
            "schema_version": 1,
            "admission_id": "ADM-R28-001",
            "execution_request_id": "REQ-R28-001",
            "decision_enforcement_id": "ENF-R28-001",
            "certification_id": "CERT-R28-001",
            "lineage_id": "LIN-R28-001",
            "subject_identity": "storageops-agent",
            "action": "collect",
            "scope": {
                "target": "netapp-lab",
            },
            "runtime_target": "storageops-collect",
            "admission_state": "ADMITTED",
            "created_at": "2026-08-28T03:01:00Z",
            "expires_at": "2026-08-28T03:10:00Z",
            "evidence_reference": "reference:r28:admission",
        },
    )

    binding = tmp_path / "binding.json"

    write_json(
        binding,
        {
            "schema_version": 1,
            "binding_id": "BIND-R28-001",
            "certification_id": "CERT-R28-001",
            "lineage_id": "LIN-R28-001",
            "decision_enforcement_id": "ENF-R28-001",
            "admission_id": "ADM-R28-001",
            "subject_identity": "storageops-agent",
            "runtime_adapter_id": "storageops-cli",
            "action": "collect",
            "execution_reference": {
                "execution_id": "collect-r28-valid",
                "evidence_file": str(runtime),
                "evidence_schema_version": 1,
                "sha256": digest,
            },
            "execution_result": "PASS",
            "binding_state": "BOUND",
            "created_at": "2026-08-28T03:04:00Z",
        },
    )

    return {
        "decision": decision,
        "admission": admission,
        "binding": binding,
        "runtime": runtime,
    }


def synchronize_runtime_digest(chain: dict[str, Path]) -> None:
    digest = hashlib.sha256(
        chain["runtime"].read_bytes()
    ).hexdigest()

    binding = read_json(chain["binding"])
    binding["execution_reference"]["sha256"] = digest
    write_json(chain["binding"], binding)


def validate(chain: dict[str, Path]) -> str:
    return validator.validate_governance_lineage(
        chain["decision"],
        chain["admission"],
        chain["binding"],
        chain["runtime"],
    )


def test_valid_chain_passes(tmp_path):
    chain = build_valid_chain(tmp_path)

    assert validate(chain) == "collect-r28-valid"


def test_cli_valid_chain_returns_zero(tmp_path, monkeypatch, capsys):
    chain = build_valid_chain(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(VALIDATOR_PATH),
            "--decision-enforcement",
            str(chain["decision"]),
            "--authorization-admission",
            str(chain["admission"]),
            "--execution-evidence-binding",
            str(chain["binding"]),
            "--runtime-evidence",
            str(chain["runtime"]),
        ],
    )

    assert validator.main() == 0

    output = capsys.readouterr().out

    assert "VALIDATION_RESULT=PASS" in output
    assert "SCHEMA_VALIDATION=PASS" in output
    assert "CROSS_ARTIFACT_BINDING=PASS" in output
    assert "RUNTIME_EVIDENCE_BINDING=PASS" in output


def test_cli_bad_sha_returns_evidence_failure(
    tmp_path,
    monkeypatch,
    capsys,
):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["binding"],
        lambda document: document["execution_reference"].update(
            {"sha256": "0" * 64}
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(VALIDATOR_PATH),
            "--decision-enforcement",
            str(chain["decision"]),
            "--authorization-admission",
            str(chain["admission"]),
            "--execution-evidence-binding",
            str(chain["binding"]),
            "--runtime-evidence",
            str(chain["runtime"]),
        ],
    )

    assert validator.main() == 1

    output = capsys.readouterr().out

    assert "VALIDATION_RESULT=FAIL" in output
    assert "FAILURE_KIND=EVIDENCE" in output
    assert "runtime evidence sha256 mismatch" in output


@pytest.mark.parametrize(
    ("mutation", "expected_text"),
    [
        (
            lambda document: document.pop("decision_id"),
            "$.decision_id is required",
        ),
        (
            lambda document: document.update(
                {"unexpected_field": "not-allowed"}
            ),
            "$ has unknown field",
        ),
        (
            lambda document: document.update(
                {"schema_version": 2}
            ),
            "$.schema_version does not match const",
        ),
    ],
)
def test_decision_schema_failures_fail_closed(
    tmp_path,
    mutation,
    expected_text,
):
    chain = build_valid_chain(tmp_path)

    mutate(chain["decision"], mutation)

    with pytest.raises(
        validator.SchemaValidationFailure,
        match=expected_text.replace("$", r"\$"),
    ):
        validate(chain)


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        (
            "decision",
            "enforcement_state",
            "HOLD",
            "decision enforcement is not ACCEPTED",
        ),
        (
            "admission",
            "admission_state",
            "PENDING",
            "authorization admission is not ADMITTED",
        ),
    ],
)
def test_non_executable_states_fail_closed(
    tmp_path,
    target,
    field,
    value,
    message,
):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain[target],
        lambda document: document.update({field: value}),
    )

    with pytest.raises(
        validator.BindingValidationFailure,
        match=message,
    ):
        validate(chain)


@pytest.mark.parametrize(
    ("target", "mutation", "message"),
    [
        (
            "admission",
            lambda document: document.update(
                {"decision_enforcement_id": "ENF-OTHER"}
            ),
            "decision enforcement identity mismatch",
        ),
        (
            "binding",
            lambda document: document.update(
                {"admission_id": "ADM-OTHER"}
            ),
            "admission identity mismatch",
        ),
        (
            "admission",
            lambda document: document.update(
                {"certification_id": "CERT-OTHER"}
            ),
            "certification identity mismatch",
        ),
        (
            "admission",
            lambda document: document.update(
                {"lineage_id": "LIN-OTHER"}
            ),
            "lineage identity mismatch",
        ),
        (
            "admission",
            lambda document: document.update(
                {"subject_identity": "other-agent"}
            ),
            "subject identity mismatch",
        ),
        (
            "admission",
            lambda document: document.update(
                {"action": "capacity"}
            ),
            "action identity mismatch",
        ),
        (
            "admission",
            lambda document: document.update(
                {
                    "scope": {
                        "target": "other-target",
                    }
                }
            ),
            "execution scope mismatch",
        ),
    ],
)
def test_cross_artifact_identity_mismatch_fails_closed(
    tmp_path,
    target,
    mutation,
    message,
):
    chain = build_valid_chain(tmp_path)

    mutate(chain[target], mutation)

    with pytest.raises(
        validator.BindingValidationFailure,
        match=message,
    ):
        validate(chain)


@pytest.mark.parametrize(
    ("mutation_target", "mutation", "failure_type", "message"),
    [
        (
            "runtime",
            lambda document: document.update(
                {"execution_id": "collect-other"}
            ),
            validator.BindingValidationFailure,
            "runtime execution identity mismatch",
        ),
        (
            "runtime",
            lambda document: document.update(
                {"schema_version": 2}
            ),
            validator.BindingValidationFailure,
            "runtime evidence schema version mismatch",
        ),
        (
            "binding",
            lambda document: document.update(
                {"execution_result": "FAIL"}
            ),
            validator.BindingValidationFailure,
            "execution result mismatch",
        ),
        (
            "binding",
            lambda document: document["execution_reference"].update(
                {"evidence_file": "/tmp/not-the-runtime-evidence.json"}
            ),
            validator.EvidenceValidationFailure,
            "binding evidence path mismatch",
        ),
        (
            "binding",
            lambda document: document["execution_reference"].update(
                {"sha256": "0" * 64}
            ),
            validator.EvidenceValidationFailure,
            "runtime evidence sha256 mismatch",
        ),
    ],
)
def test_runtime_evidence_binding_failures_fail_closed(
    tmp_path,
    mutation_target,
    mutation,
    failure_type,
    message,
):
    chain = build_valid_chain(tmp_path)

    mutate(chain[mutation_target], mutation)

    with pytest.raises(
        failure_type,
        match=message,
    ):
        validate(chain)


def test_admission_before_decision_fails_closed(tmp_path):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["admission"],
        lambda document: document.update(
            {"created_at": "2026-08-28T02:59:00Z"}
        ),
    )

    with pytest.raises(
        validator.BindingValidationFailure,
        match="admission predates decision enforcement",
    ):
        validate(chain)


def test_execution_before_admission_fails_closed(tmp_path):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["runtime"],
        lambda document: document["data"].update(
            {
                "started_at": "2026-08-28T03:00:30Z",
                "completed_at": "2026-08-28T03:03:00Z",
            }
        ),
    )

    synchronize_runtime_digest(chain)

    with pytest.raises(
        validator.BindingValidationFailure,
        match="execution predates admission",
    ):
        validate(chain)


def test_execution_after_admission_expiry_fails_closed(
    tmp_path,
):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["runtime"],
        lambda document: document["data"].update(
            {
                "started_at": "2026-08-28T03:11:00Z",
                "completed_at": "2026-08-28T03:12:00Z",
            }
        ),
    )

    synchronize_runtime_digest(chain)

    with pytest.raises(
        validator.BindingValidationFailure,
        match="execution started after admission expiry",
    ):
        validate(chain)


def test_reversed_runtime_timestamp_fails_closed(tmp_path):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["runtime"],
        lambda document: document["data"].update(
            {
                "started_at": "2026-08-28T03:05:00Z",
                "completed_at": "2026-08-28T03:04:00Z",
            }
        ),
    )

    synchronize_runtime_digest(chain)

    with pytest.raises(
        validator.EvidenceValidationFailure,
        match="runtime timestamps are reversed",
    ):
        validate(chain)


def test_binding_before_execution_completion_fails_closed(
    tmp_path,
):
    chain = build_valid_chain(tmp_path)

    mutate(
        chain["binding"],
        lambda document: document.update(
            {"created_at": "2026-08-28T03:02:30Z"}
        ),
    )

    with pytest.raises(
        validator.BindingValidationFailure,
        match="evidence binding predates execution completion",
    ):
        validate(chain)
