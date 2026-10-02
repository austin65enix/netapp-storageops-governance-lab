#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_PATHS = {
    "decision_enforcement": (
        REPO_ROOT
        / "operational"
        / "contracts"
        / "decision-enforcement.schema.json"
    ),
    "authorization_admission": (
        REPO_ROOT
        / "operational"
        / "contracts"
        / "authorization-admission.schema.json"
    ),
    "execution_evidence_binding": (
        REPO_ROOT
        / "operational"
        / "contracts"
        / "execution-evidence-binding.schema.json"
    ),
}


class ValidationFailure(Exception):
    kind = "VALIDATION"


class SchemaValidationFailure(ValidationFailure):
    kind = "SCHEMA"


class BindingValidationFailure(ValidationFailure):
    kind = "BINDING"


class EvidenceValidationFailure(ValidationFailure):
    kind = "EVIDENCE"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise EvidenceValidationFailure(
            f"{label} does not exist"
        )

    if not path.is_file():
        raise EvidenceValidationFailure(
            f"{label} is not a regular file"
        )

    if path.is_symlink():
        raise EvidenceValidationFailure(
            f"{label} must not be a symbolic link"
        )

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationFailure(
            f"{label} is not valid JSON"
        ) from exc

    if not isinstance(value, dict):
        raise EvidenceValidationFailure(
            f"{label} root must be an object"
        )

    return value


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)

    if expected == "string":
        return isinstance(value, str)

    if expected == "integer":
        return type(value) is int

    if expected == "boolean":
        return type(value) is bool

    if expected == "null":
        return value is None

    return False


def _parse_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise SchemaValidationFailure(
            f"{label} is not a valid date-time"
        ) from exc

    if parsed.tzinfo is None:
        raise SchemaValidationFailure(
            f"{label} must include a timezone"
        )

    return parsed


def _validate_schema_subset(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    expected_type = schema.get("type")

    if expected_type is not None:
        if not _json_type_matches(value, expected_type):
            raise SchemaValidationFailure(
                f"{path} has invalid type"
            )

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationFailure(
            f"{path} does not match const"
        )

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationFailure(
            f"{path} is not an allowed value"
        )

    if isinstance(value, str):
        min_length = schema.get("minLength")

        if (
            min_length is not None
            and len(value) < min_length
        ):
            raise SchemaValidationFailure(
                f"{path} is too short"
            )

        pattern = schema.get("pattern")

        if (
            pattern is not None
            and re.search(pattern, value) is None
        ):
            raise SchemaValidationFailure(
                f"{path} does not match required pattern"
            )

        if schema.get("format") == "date-time":
            _parse_datetime(value, path)

    if isinstance(value, dict):
        required = schema.get("required", [])

        for field in required:
            if field not in value:
                raise SchemaValidationFailure(
                    f"{path}.{field} is required"
                )

        properties = schema.get("properties", {})

        if schema.get("additionalProperties") is False:
            unknown = sorted(
                set(value) - set(properties)
            )

            if unknown:
                raise SchemaValidationFailure(
                    f"{path} has unknown field: {unknown[0]}"
                )

        for field, child_schema in properties.items():
            if field in value:
                _validate_schema_subset(
                    value[field],
                    child_schema,
                    f"{path}.{field}",
                )

    for rule in schema.get("allOf", []):
        if "if" in rule:
            try:
                _validate_schema_subset(
                    value,
                    rule["if"],
                    path,
                )
                matched = True
            except SchemaValidationFailure:
                matched = False

            if matched and "then" in rule:
                _validate_schema_subset(
                    value,
                    rule["then"],
                    path,
                )

            if not matched and "else" in rule:
                _validate_schema_subset(
                    value,
                    rule["else"],
                    path,
                )
        else:
            _validate_schema_subset(
                value,
                rule,
                path,
            )


def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_PATHS[name]

    try:
        schema = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaValidationFailure(
            f"{name} schema cannot be loaded"
        ) from exc

    if not isinstance(schema, dict):
        raise SchemaValidationFailure(
            f"{name} schema root is invalid"
        )

    if (
        schema.get("$schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        raise SchemaValidationFailure(
            f"{name} schema draft is unexpected"
        )

    return schema


def _require_equal(
    label: str,
    *values: Any,
) -> None:
    if not values:
        return

    first = values[0]

    if any(value != first for value in values[1:]):
        raise BindingValidationFailure(
            f"{label} mismatch"
        )


def _normalized_path(path: Path) -> str:
    return str(
        path.expanduser().resolve(strict=False)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    try:
        with path.open("rb") as handle:
            for chunk in iter(
                lambda: handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceValidationFailure(
            "runtime evidence cannot be hashed"
        ) from exc

    return digest.hexdigest()


def validate_governance_lineage(
    decision_path: Path,
    admission_path: Path,
    binding_path: Path,
    runtime_evidence_path: Path,
) -> str:
    decision = _load_json(
        decision_path,
        "decision enforcement record",
    )
    admission = _load_json(
        admission_path,
        "authorization admission record",
    )
    binding = _load_json(
        binding_path,
        "execution evidence binding record",
    )
    runtime = _load_json(
        runtime_evidence_path,
        "runtime evidence",
    )

    _validate_schema_subset(
        decision,
        _load_schema("decision_enforcement"),
    )

    _validate_schema_subset(
        admission,
        _load_schema("authorization_admission"),
    )

    _validate_schema_subset(
        binding,
        _load_schema("execution_evidence_binding"),
    )

    if decision["enforcement_state"] != "ACCEPTED":
        raise BindingValidationFailure(
            "decision enforcement is not ACCEPTED"
        )

    if admission["admission_state"] != "ADMITTED":
        raise BindingValidationFailure(
            "authorization admission is not ADMITTED"
        )

    if binding["binding_state"] != "BOUND":
        raise BindingValidationFailure(
            "execution evidence is not BOUND"
        )

    _require_equal(
        "decision enforcement identity",
        decision["enforcement_id"],
        admission["decision_enforcement_id"],
        binding["decision_enforcement_id"],
    )

    _require_equal(
        "certification identity",
        decision["certification_id"],
        admission["certification_id"],
        binding["certification_id"],
    )

    _require_equal(
        "lineage identity",
        decision["lineage_id"],
        admission["lineage_id"],
        binding["lineage_id"],
    )

    _require_equal(
        "subject identity",
        decision["subject_identity"],
        admission["subject_identity"],
        binding["subject_identity"],
    )

    _require_equal(
        "action identity",
        decision["action"],
        admission["action"],
        binding["action"],
    )

    _require_equal(
        "execution scope",
        decision["scope"],
        admission["scope"],
    )

    _require_equal(
        "admission identity",
        admission["admission_id"],
        binding["admission_id"],
    )

    execution_reference = binding["execution_reference"]

    runtime_execution_id = runtime.get("execution_id")

    runtime_data = runtime.get("data")

    if not isinstance(runtime_data, dict):
        raise EvidenceValidationFailure(
            "runtime evidence data is invalid"
        )

    data_execution_id = runtime_data.get("execution_id")

    _require_equal(
        "runtime execution identity",
        execution_reference["execution_id"],
        runtime_execution_id,
        data_execution_id,
    )

    runtime_schema_version = runtime.get("schema_version")

    _require_equal(
        "runtime evidence schema version",
        execution_reference["evidence_schema_version"],
        runtime_schema_version,
    )

    expected_runtime_path = _normalized_path(
        runtime_evidence_path
    )

    reference_runtime_path = _normalized_path(
        Path(execution_reference["evidence_file"])
    )

    if reference_runtime_path != expected_runtime_path:
        raise EvidenceValidationFailure(
            "binding evidence path mismatch"
        )

    runtime_recorded_path = runtime.get("evidence_file")

    if not isinstance(runtime_recorded_path, str):
        raise EvidenceValidationFailure(
            "runtime evidence_file is invalid"
        )

    if (
        _normalized_path(Path(runtime_recorded_path))
        != expected_runtime_path
    ):
        raise EvidenceValidationFailure(
            "runtime evidence_file mismatch"
        )

    actual_digest = _sha256(runtime_evidence_path)

    if execution_reference["sha256"] != actual_digest:
        raise EvidenceValidationFailure(
            "runtime evidence sha256 mismatch"
        )

    runtime_result = runtime.get("result")

    if runtime_result not in {"PASS", "FAIL"}:
        raise EvidenceValidationFailure(
            "runtime result is invalid"
        )

    _require_equal(
        "execution result",
        binding["execution_result"],
        runtime_result,
    )

    runtime_command = runtime.get("command")

    if not isinstance(runtime_command, str):
        raise EvidenceValidationFailure(
            "runtime command is invalid"
        )

    _require_equal(
        "runtime action",
        binding["action"],
        runtime_command,
    )

    started_at = runtime_data.get("started_at")
    completed_at = runtime_data.get("completed_at")

    if not isinstance(started_at, str):
        raise EvidenceValidationFailure(
            "runtime started_at is invalid"
        )

    if not isinstance(completed_at, str):
        raise EvidenceValidationFailure(
            "runtime completed_at is invalid"
        )

    decision_created = _parse_datetime(
        decision["created_at"],
        "$.decision.created_at",
    )

    admission_created = _parse_datetime(
        admission["created_at"],
        "$.admission.created_at",
    )

    admission_expires = _parse_datetime(
        admission["expires_at"],
        "$.admission.expires_at",
    )

    execution_started = _parse_datetime(
        started_at,
        "$.runtime.data.started_at",
    )

    execution_completed = _parse_datetime(
        completed_at,
        "$.runtime.data.completed_at",
    )

    binding_created = _parse_datetime(
        binding["created_at"],
        "$.binding.created_at",
    )

    if decision_created > admission_created:
        raise BindingValidationFailure(
            "admission predates decision enforcement"
        )

    if admission_created > admission_expires:
        raise BindingValidationFailure(
            "admission expires before it is created"
        )

    if admission_created > execution_started:
        raise BindingValidationFailure(
            "execution predates admission"
        )

    if execution_started > admission_expires:
        raise BindingValidationFailure(
            "execution started after admission expiry"
        )

    if execution_started > execution_completed:
        raise EvidenceValidationFailure(
            "runtime timestamps are reversed"
        )

    if execution_completed > binding_created:
        raise BindingValidationFailure(
            "evidence binding predates execution completion"
        )

    return str(execution_reference["execution_id"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate StorageOps governance decision, admission, "
            "execution evidence binding, and referenced runtime evidence."
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
        "--execution-evidence-binding",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--runtime-evidence",
        required=True,
        type=Path,
    )

    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        execution_id = validate_governance_lineage(
            args.decision_enforcement,
            args.authorization_admission,
            args.execution_evidence_binding,
            args.runtime_evidence,
        )
    except ValidationFailure as exc:
        print("VALIDATION_RESULT=FAIL")
        print(f"FAILURE_KIND={exc.kind}")
        print(f"ERROR={exc}")
        return 1
    except Exception:
        print("VALIDATION_RESULT=FAIL")
        print("FAILURE_KIND=INTERNAL")
        print("ERROR=validator execution failed")
        return 1

    print("VALIDATION_RESULT=PASS")
    print("SCHEMA_VALIDATION=PASS")
    print("CROSS_ARTIFACT_BINDING=PASS")
    print("RUNTIME_EVIDENCE_BINDING=PASS")
    print(f"EXECUTION_ID={execution_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
