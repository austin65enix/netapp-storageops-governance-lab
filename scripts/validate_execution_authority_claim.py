#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

GATE_PATH = (
    ROOT
    / "scripts"
    / "check_governance_admission.py"
)

MATERIAL_SCHEMA_PATH = (
    ROOT
    / "operational"
    / "contracts"
    / "execution-authority-material.schema.json"
)

CLAIM_SCHEMA_PATH = (
    ROOT
    / "operational"
    / "contracts"
    / "admission-consumption-claim.schema.json"
)


class ValidationFailure(Exception):
    failure_kind = "VALIDATION"


class InputFailure(ValidationFailure):
    failure_kind = "INPUT"


class ByteBindingFailure(ValidationFailure):
    failure_kind = "BYTE_BINDING"


class CrossArtifactBindingFailure(ValidationFailure):
    failure_kind = "BINDING"


class TemporalBindingFailure(ValidationFailure):
    failure_kind = "TEMPORAL"


def load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "storageops_governance_admission_gate",
        GATE_PATH,
    )

    if spec is None or spec.loader is None:
        raise InputFailure(
            "unable to load governance admission gate"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def require_regular_file(
    path: Path,
    label: str,
) -> Path:
    if path.is_symlink():
        raise InputFailure(
            f"{label} must not be a symbolic link"
        )

    if not path.exists():
        raise InputFailure(
            f"{label} does not exist"
        )

    if not path.is_file():
        raise InputFailure(
            f"{label} is not a regular file"
        )

    return path


def absolute_lexical_path(path: Path) -> Path:
    return Path(
        os.path.abspath(
            os.fspath(path)
        )
    )


def resolve_reference(
    *,
    owner_path: Path,
    reference: str,
) -> Path:
    referenced = Path(reference)

    if not referenced.is_absolute():
        referenced = (
            owner_path.parent
            / referenced
        )

    return absolute_lexical_path(
        referenced
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def load_json_object(
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise InputFailure(
            f"{label} is not readable valid JSON"
        ) from exc

    if not isinstance(value, dict):
        raise InputFailure(
            f"{label} must be a JSON object"
        )

    return value


def require_equal(
    label: str,
    *values: Any,
) -> None:
    if not values:
        return

    first = values[0]

    if any(
        value != first
        for value in values[1:]
    ):
        raise CrossArtifactBindingFailure(
            f"{label} mismatch"
        )


def require_digest(
    *,
    label: str,
    actual: str,
    expected: str,
) -> None:
    if actual != expected:
        raise ByteBindingFailure(
            f"{label} sha256 mismatch"
        )


def evaluate(
    *,
    decision_path: Path,
    admission_path: Path,
    material_path: Path,
    claim_path: Path,
) -> dict[str, str]:
    gate = load_gate_module()

    decision_path = require_regular_file(
        decision_path,
        "decision enforcement record",
    )

    admission_path = require_regular_file(
        admission_path,
        "authorization admission record",
    )

    material_path = require_regular_file(
        material_path,
        "execution authority material",
    )

    claim_path = require_regular_file(
        claim_path,
        "admission consumption claim",
    )

    decision_abs = absolute_lexical_path(
        decision_path
    )
    admission_abs = absolute_lexical_path(
        admission_path
    )
    material_abs = absolute_lexical_path(
        material_path
    )

    material = load_json_object(
        material_path,
        "execution authority material",
    )

    claim = load_json_object(
        claim_path,
        "admission consumption claim",
    )

    material_schema = load_json_object(
        MATERIAL_SCHEMA_PATH,
        "execution authority material schema",
    )

    claim_schema = load_json_object(
        CLAIM_SCHEMA_PATH,
        "admission consumption claim schema",
    )

    gate.validate_schema_subset(
        material,
        material_schema,
    )

    gate.validate_schema_subset(
        claim,
        claim_schema,
    )

    decision_reference = (
        material[
            "decision_enforcement_reference"
        ]
    )

    admission_reference = (
        material[
            "authorization_admission_reference"
        ]
    )

    referenced_decision = resolve_reference(
        owner_path=material_path,
        reference=decision_reference[
            "record_file"
        ],
    )

    referenced_admission = resolve_reference(
        owner_path=material_path,
        reference=admission_reference[
            "record_file"
        ],
    )

    referenced_material = resolve_reference(
        owner_path=claim_path,
        reference=claim[
            "authority_material_file"
        ],
    )

    require_equal(
        "decision record path",
        decision_abs,
        referenced_decision,
    )

    require_equal(
        "admission record path",
        admission_abs,
        referenced_admission,
    )

    require_equal(
        "authority material path",
        material_abs,
        referenced_material,
    )

    decision_sha256 = sha256_file(
        decision_path
    )

    admission_sha256 = sha256_file(
        admission_path
    )

    material_sha256 = sha256_file(
        material_path
    )

    require_digest(
        label="decision enforcement",
        actual=decision_sha256,
        expected=decision_reference[
            "sha256"
        ],
    )

    require_digest(
        label="authorization admission",
        actual=admission_sha256,
        expected=admission_reference[
            "sha256"
        ],
    )

    require_digest(
        label="execution authority material",
        actual=material_sha256,
        expected=claim[
            "authority_material_sha256"
        ],
    )

    require_digest(
        label="claim decision enforcement",
        actual=decision_sha256,
        expected=claim[
            "decision_enforcement_sha256"
        ],
    )

    require_digest(
        label="claim authorization admission",
        actual=admission_sha256,
        expected=claim[
            "authorization_admission_sha256"
        ],
    )

    require_equal(
        "decision digest lineage",
        decision_reference["sha256"],
        claim[
            "decision_enforcement_sha256"
        ],
    )

    require_equal(
        "admission digest lineage",
        admission_reference["sha256"],
        claim[
            "authorization_admission_sha256"
        ],
    )

    context = material[
        "expected_context"
    ]

    claimed_at = gate.parse_datetime(
        claim["claimed_at"],
        "$.claim.claimed_at",
    )

    gate_result = (
        gate.evaluate_pre_execution_admission(
            decision_path=decision_path,
            admission_path=admission_path,
            expected_enforcement_id=(
                context["enforcement_id"]
            ),
            expected_admission_id=(
                context["admission_id"]
            ),
            expected_execution_request_id=(
                context[
                    "execution_request_id"
                ]
            ),
            expected_certification_id=(
                context["certification_id"]
            ),
            expected_lineage_id=(
                context["lineage_id"]
            ),
            expected_subject_identity=(
                context[
                    "subject_identity"
                ]
            ),
            expected_action=(
                context["action"]
            ),
            expected_runtime_target=(
                context["runtime_target"]
            ),
            expected_scope=(
                context["scope"]
            ),
            evaluation_time=claimed_at,
        )
    )

    require_equal(
        "authority material identity",
        material[
            "authority_material_id"
        ],
        claim[
            "authority_material_id"
        ],
    )

    require_equal(
        "execution request identity",
        context[
            "execution_request_id"
        ],
        gate_result[
            "execution_request_id"
        ],
        claim[
            "execution_request_id"
        ],
    )

    require_equal(
        "admission identity",
        context["admission_id"],
        gate_result["admission_id"],
        claim["admission_id"],
    )

    require_equal(
        "decision enforcement identity",
        context["enforcement_id"],
        gate_result[
            "decision_enforcement_id"
        ],
        claim[
            "decision_enforcement_id"
        ],
    )

    require_equal(
        "certification identity",
        context["certification_id"],
        gate_result[
            "certification_id"
        ],
        claim["certification_id"],
    )

    require_equal(
        "lineage identity",
        context["lineage_id"],
        gate_result["lineage_id"],
        claim["lineage_id"],
    )

    require_equal(
        "subject identity",
        context["subject_identity"],
        gate_result[
            "subject_identity"
        ],
        claim[
            "subject_identity"
        ],
    )

    require_equal(
        "action identity",
        context["action"],
        gate_result["action"],
        claim["action"],
    )

    require_equal(
        "scope",
        context["scope"],
        claim["scope"],
    )

    require_equal(
        "runtime target",
        context["runtime_target"],
        gate_result[
            "runtime_target"
        ],
        claim["runtime_target"],
    )

    admission = load_json_object(
        admission_path,
        "authorization admission record",
    )

    admission_created = (
        gate.parse_datetime(
            admission["created_at"],
            "$.admission.created_at",
        )
    )

    admission_expires = (
        gate.parse_datetime(
            admission["expires_at"],
            "$.admission.expires_at",
        )
    )

    material_issued = (
        gate.parse_datetime(
            material["issued_at"],
            "$.material.issued_at",
        )
    )

    if material_issued < admission_created:
        raise TemporalBindingFailure(
            "authority material predates admission"
        )

    if material_issued > claimed_at:
        raise TemporalBindingFailure(
            "claim predates authority material"
        )

    if material_issued > admission_expires:
        raise TemporalBindingFailure(
            "authority material was issued "
            "after admission expiry"
        )

    if claimed_at > admission_expires:
        raise TemporalBindingFailure(
            "claim occurred after admission expiry"
        )

    return {
        "authority_material_id": (
            material[
                "authority_material_id"
            ]
        ),
        "claim_id": claim["claim_id"],
        "execution_request_id": (
            claim[
                "execution_request_id"
            ]
        ),
        "admission_id": (
            claim["admission_id"]
        ),
        "decision_enforcement_id": (
            claim[
                "decision_enforcement_id"
            ]
        ),
        "certification_id": (
            claim["certification_id"]
        ),
        "lineage_id": (
            claim["lineage_id"]
        ),
        "claim_state": (
            claim["claim_state"]
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate StorageOps execution authority "
            "material and an existing admission "
            "consumption claim against exact decision "
            "and admission bytes. This command never "
            "creates claims and never dispatches runtime "
            "execution."
        )
    )

    parser.add_argument(
        "--decision-enforcement",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--authorization-admission",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--execution-authority-material",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--admission-consumption-claim",
        required=True,
        type=Path,
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    gate = None

    try:
        result = evaluate(
            decision_path=(
                args.decision_enforcement
            ),
            admission_path=(
                args.authorization_admission
            ),
            material_path=(
                args.execution_authority_material
            ),
            claim_path=(
                args.admission_consumption_claim
            ),
        )

    except ValidationFailure as exc:
        print("VALIDATION_RESULT=FAIL")
        print(
            "FAILURE_KIND="
            + exc.failure_kind
        )
        print("ERROR=" + str(exc))
        return 1

    except Exception as exc:
        try:
            gate = load_gate_module()
        except Exception:
            gate = None

        if (
            gate is not None
            and isinstance(
                exc,
                gate.SchemaFailure,
            )
        ):
            failure_kind = "SCHEMA"

        elif (
            gate is not None
            and isinstance(
                exc,
                gate.BindingFailure,
            )
        ):
            failure_kind = "BINDING"

        elif (
            gate is not None
            and isinstance(
                exc,
                gate.AdmissionFailure,
            )
        ):
            failure_kind = "ADMISSION"

        else:
            failure_kind = "VALIDATION"

        print("VALIDATION_RESULT=FAIL")
        print(
            "FAILURE_KIND="
            + failure_kind
        )
        print("ERROR=" + str(exc))
        return 1

    print("VALIDATION_RESULT=PASS")
    print("SCHEMA_VALIDATION=PASS")
    print("BYTE_BINDING=PASS")
    print("CROSS_ARTIFACT_BINDING=PASS")
    print("TEMPORAL_BINDING=PASS")

    for key in (
        "authority_material_id",
        "claim_id",
        "execution_request_id",
        "admission_id",
        "decision_enforcement_id",
        "certification_id",
        "lineage_id",
        "claim_state",
    ):
        print(
            key.upper()
            + "="
            + result[key]
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
