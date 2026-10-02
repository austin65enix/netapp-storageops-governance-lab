from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]

VALIDATOR_PATH = (
    ROOT
    / "scripts"
    / "validate_execution_authority_claim.py"
)

DECISION_SCHEMA_PATH = (
    ROOT
    / "operational"
    / "contracts"
    / "decision-enforcement.schema.json"
)

ADMISSION_SCHEMA_PATH = (
    ROOT
    / "operational"
    / "contracts"
    / "authorization-admission.schema.json"
)


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "r38_execution_authority_claim_validator",
        VALIDATOR_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "unable to import R37 validator"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


VALIDATOR = _load_validator()


def _write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _load_schema(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert isinstance(value, dict)
    return value


def _example_from_schema(
    node: dict[str, Any],
    label: str,
) -> Any:
    if "const" in node:
        return copy.deepcopy(
            node["const"]
        )

    enum = node.get("enum")

    if isinstance(enum, list) and enum:
        return copy.deepcopy(enum[0])

    value_type = node.get("type")

    if value_type == "string":
        pattern = node.get("pattern")

        if pattern == "^[0-9a-f]{64}$":
            return "0" * 64

        if node.get("format") == "date-time":
            return "2026-08-28T05:00:00Z"

        return label

    if value_type == "integer":
        return 1

    if value_type == "boolean":
        return False

    if value_type == "array":
        return []

    if value_type == "object":
        properties = node.get(
            "properties",
            {},
        )

        result: dict[str, Any] = {}

        for field in node.get(
            "required",
            [],
        ):
            result[field] = (
                _example_from_schema(
                    properties[field],
                    f"{label}-{field}",
                )
            )

        return result

    raise AssertionError(
        f"unsupported fixture schema node: {node!r}"
    )


def _base_record(
    schema_path: Path,
    label: str,
) -> dict[str, Any]:
    schema = _load_schema(
        schema_path
    )

    value = _example_from_schema(
        schema,
        label,
    )

    assert isinstance(value, dict)
    return value


def _build_valid_chain(
    tmp_path: Path,
) -> dict[str, Any]:
    decision_path = (
        tmp_path / "decision.json"
    )

    admission_path = (
        tmp_path / "admission.json"
    )

    material_path = (
        tmp_path / "authority-material.json"
    )

    claim_path = (
        tmp_path / "claim.json"
    )

    decision = _base_record(
        DECISION_SCHEMA_PATH,
        "R38-DECISION",
    )

    decision.update(
        {
            "schema_version": 1,
            "enforcement_id": "ENF-R38-001",
            "decision_id": "DEC-R38-001",
            "policy_evaluation_id": "POL-R38-001",
            "certification_id": "CERT-R38-001",
            "lineage_id": "LIN-R38-001",
            "subject_identity": "storageops-agent",
            "action": "collect",
            "scope": {
                "target": "netapp-lab",
            },
            "enforcement_state": "ACCEPTED",
            "created_at": (
                "2026-08-28T05:00:00Z"
            ),
        }
    )

    admission = _base_record(
        ADMISSION_SCHEMA_PATH,
        "R38-ADMISSION",
    )

    admission.update(
        {
            "schema_version": 1,
            "admission_id": "ADM-R38-001",
            "execution_request_id": "REQ-R38-001",
            "decision_enforcement_id": "ENF-R38-001",
            "certification_id": "CERT-R38-001",
            "lineage_id": "LIN-R38-001",
            "subject_identity": "storageops-agent",
            "action": "collect",
            "scope": {
                "target": "netapp-lab",
            },
            "runtime_target": "storageops-collect",
            "admission_state": "ADMITTED",
            "created_at": (
                "2026-08-28T05:01:00Z"
            ),
            "expires_at": (
                "2026-08-28T05:10:00Z"
            ),
        }
    )

    _write_json(
        decision_path,
        decision,
    )

    _write_json(
        admission_path,
        admission,
    )

    material = {
        "schema_version": 1,
        "authority_material_id": "AUTH-R38-001",
        "issuer_identity": "authority-issuer-r38",
        "issued_at": "2026-08-28T05:02:00Z",
        "decision_enforcement_reference": {
            "record_file": str(
                decision_path
            ),
            "sha256": _sha256(
                decision_path
            ),
        },
        "authorization_admission_reference": {
            "record_file": str(
                admission_path
            ),
            "sha256": _sha256(
                admission_path
            ),
        },
        "expected_context": {
            "enforcement_id": "ENF-R38-001",
            "admission_id": "ADM-R38-001",
            "execution_request_id": "REQ-R38-001",
            "certification_id": "CERT-R38-001",
            "lineage_id": "LIN-R38-001",
            "subject_identity": "storageops-agent",
            "action": "collect",
            "scope": {
                "target": "netapp-lab",
            },
            "runtime_target": "storageops-collect",
        },
    }

    _write_json(
        material_path,
        material,
    )

    claim = {
        "schema_version": 1,
        "claim_id": "CLAIM-R38-001",
        "authority_material_id": "AUTH-R38-001",
        "authority_material_file": str(
            material_path
        ),
        "authority_material_sha256": _sha256(
            material_path
        ),
        "execution_request_id": "REQ-R38-001",
        "admission_id": "ADM-R38-001",
        "decision_enforcement_id": "ENF-R38-001",
        "certification_id": "CERT-R38-001",
        "lineage_id": "LIN-R38-001",
        "subject_identity": "storageops-agent",
        "action": "collect",
        "scope": {
            "target": "netapp-lab",
        },
        "runtime_target": "storageops-collect",
        "decision_enforcement_sha256": _sha256(
            decision_path
        ),
        "authorization_admission_sha256": _sha256(
            admission_path
        ),
        "claimed_at": "2026-08-28T05:03:00Z",
        "claim_state": "CLAIMED",
    }

    _write_json(
        claim_path,
        claim,
    )

    return {
        "decision_path": decision_path,
        "admission_path": admission_path,
        "material_path": material_path,
        "claim_path": claim_path,
        "decision": decision,
        "admission": admission,
        "material": material,
        "claim": claim,
    }


def _evaluate(
    chain: dict[str, Any],
) -> dict[str, str]:
    return VALIDATOR.evaluate(
        decision_path=chain[
            "decision_path"
        ],
        admission_path=chain[
            "admission_path"
        ],
        material_path=chain[
            "material_path"
        ],
        claim_path=chain[
            "claim_path"
        ],
    )


def _rewrite_claim(
    chain: dict[str, Any],
) -> None:
    _write_json(
        chain["claim_path"],
        chain["claim"],
    )


def _rewrite_material_and_claim(
    chain: dict[str, Any],
) -> None:
    _write_json(
        chain["material_path"],
        chain["material"],
    )

    chain["claim"][
        "authority_material_sha256"
    ] = _sha256(
        chain["material_path"]
    )

    _rewrite_claim(chain)


def _rebind_source_records(
    chain: dict[str, Any],
) -> None:
    _write_json(
        chain["decision_path"],
        chain["decision"],
    )

    _write_json(
        chain["admission_path"],
        chain["admission"],
    )

    decision_sha = _sha256(
        chain["decision_path"]
    )

    admission_sha = _sha256(
        chain["admission_path"]
    )

    chain["material"][
        "decision_enforcement_reference"
    ]["sha256"] = decision_sha

    chain["material"][
        "authorization_admission_reference"
    ]["sha256"] = admission_sha

    chain["claim"][
        "decision_enforcement_sha256"
    ] = decision_sha

    chain["claim"][
        "authorization_admission_sha256"
    ] = admission_sha

    _rewrite_material_and_claim(chain)


def _cli_args(
    chain: dict[str, Any],
) -> list[str]:
    return [
        str(VALIDATOR_PATH),
        "--decision-enforcement",
        str(chain["decision_path"]),
        "--authorization-admission",
        str(chain["admission_path"]),
        "--execution-authority-material",
        str(chain["material_path"]),
        "--admission-consumption-claim",
        str(chain["claim_path"]),
    ]


def test_valid_exact_chain_passes(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    before = {
        path.name
        for path in tmp_path.iterdir()
    }

    result = _evaluate(chain)

    after = {
        path.name
        for path in tmp_path.iterdir()
    }

    assert before == after

    assert result[
        "authority_material_id"
    ] == "AUTH-R38-001"

    assert result[
        "claim_id"
    ] == "CLAIM-R38-001"

    assert result[
        "execution_request_id"
    ] == "REQ-R38-001"

    assert result[
        "claim_state"
    ] == "CLAIMED"


def test_cli_valid_exact_chain_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    monkeypatch.setattr(
        sys,
        "argv",
        _cli_args(chain),
    )

    rc = VALIDATOR.main()

    output = capsys.readouterr().out

    assert rc == 0
    assert "VALIDATION_RESULT=PASS" in output
    assert "SCHEMA_VALIDATION=PASS" in output
    assert "BYTE_BINDING=PASS" in output
    assert (
        "CROSS_ARTIFACT_BINDING=PASS"
        in output
    )
    assert "TEMPORAL_BINDING=PASS" in output


def test_bad_decision_sha_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["material"][
        "decision_enforcement_reference"
    ]["sha256"] = "0" * 64

    _rewrite_material_and_claim(chain)

    with pytest.raises(
        VALIDATOR.ByteBindingFailure,
        match="decision enforcement sha256 mismatch",
    ):
        _evaluate(chain)


def test_bad_admission_sha_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["material"][
        "authorization_admission_reference"
    ]["sha256"] = "0" * 64

    _rewrite_material_and_claim(chain)

    with pytest.raises(
        VALIDATOR.ByteBindingFailure,
        match="authorization admission sha256 mismatch",
    ):
        _evaluate(chain)


def test_bad_authority_material_sha_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "authority_material_sha256"
    ] = "0" * 64

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.ByteBindingFailure,
        match=(
            "execution authority material "
            "sha256 mismatch"
        ),
    ):
        _evaluate(chain)


def test_authority_material_id_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "authority_material_id"
    ] = "AUTH-OTHER"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="authority material identity mismatch",
    ):
        _evaluate(chain)


def test_execution_request_id_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "execution_request_id"
    ] = "REQ-OTHER"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="execution request identity mismatch",
    ):
        _evaluate(chain)


def test_admission_id_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "admission_id"
    ] = "ADM-OTHER"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="admission identity mismatch",
    ):
        _evaluate(chain)


def test_lineage_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "lineage_id"
    ] = "LIN-OTHER"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="lineage identity mismatch",
    ):
        _evaluate(chain)


def test_scope_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"]["scope"] = {
        "target": "other-target",
    }

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="scope mismatch",
    ):
        _evaluate(chain)


def test_runtime_target_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "runtime_target"
    ] = "other-runtime"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="runtime target mismatch",
    ):
        _evaluate(chain)


def test_decision_path_substitution_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["material"][
        "decision_enforcement_reference"
    ]["record_file"] = str(
        tmp_path / "substituted-decision.json"
    )

    _rewrite_material_and_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="decision record path mismatch",
    ):
        _evaluate(chain)


def test_authority_material_path_substitution_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "authority_material_file"
    ] = str(
        tmp_path / "substituted-material.json"
    )

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.CrossArtifactBindingFailure,
        match="authority material path mismatch",
    ):
        _evaluate(chain)


def test_material_before_admission_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["material"][
        "issued_at"
    ] = "2026-08-28T05:00:30Z"

    _rewrite_material_and_claim(chain)

    with pytest.raises(
        VALIDATOR.TemporalBindingFailure,
        match="authority material predates admission",
    ):
        _evaluate(chain)


def test_claim_before_material_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "claimed_at"
    ] = "2026-08-28T05:01:30Z"

    _rewrite_claim(chain)

    with pytest.raises(
        VALIDATOR.TemporalBindingFailure,
        match="claim predates authority material",
    ):
        _evaluate(chain)


def test_claim_after_admission_expiry_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["claim"][
        "claimed_at"
    ] = "2026-08-28T05:11:00Z"

    _rewrite_claim(chain)

    with pytest.raises(
        Exception,
        match="admission has expired",
    ):
        _evaluate(chain)


def test_malformed_material_schema_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    del chain["material"][
        "issuer_identity"
    ]

    _write_json(
        chain["material_path"],
        chain["material"],
    )

    with pytest.raises(Exception):
        _evaluate(chain)


def test_malformed_claim_schema_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    del chain["claim"][
        "execution_request_id"
    ]

    _rewrite_claim(chain)

    with pytest.raises(Exception):
        _evaluate(chain)


def test_decision_not_accepted_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["decision"][
        "enforcement_state"
    ] = "HOLD"

    _rebind_source_records(chain)

    with pytest.raises(
        Exception,
        match=(
            "decision enforcement "
            "is not ACCEPTED"
        ),
    ):
        _evaluate(chain)


def test_admission_not_admitted_fails_closed(
    tmp_path: Path,
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["admission"][
        "admission_state"
    ] = "PENDING"

    _rebind_source_records(chain)

    with pytest.raises(
        Exception,
        match=(
            "authorization admission "
            "is not ADMITTED"
        ),
    ):
        _evaluate(chain)


def test_cli_admission_failure_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chain = _build_valid_chain(
        tmp_path
    )

    chain["admission"][
        "admission_state"
    ] = "PENDING"

    _rebind_source_records(chain)

    monkeypatch.setattr(
        sys,
        "argv",
        _cli_args(chain),
    )

    rc = VALIDATOR.main()

    output = capsys.readouterr().out

    assert rc == 1
    assert "VALIDATION_RESULT=FAIL" in output
    assert (
        "authorization admission is not ADMITTED"
        in output
    )
