#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DECISION_SCHEMA_PATH = (
    REPO_ROOT
    / "operational"
    / "contracts"
    / "decision-enforcement.schema.json"
)

ADMISSION_SCHEMA_PATH = (
    REPO_ROOT
    / "operational"
    / "contracts"
    / "authorization-admission.schema.json"
)


class GateFailure(Exception):
    kind = "GATE"


class SchemaFailure(GateFailure):
    kind = "SCHEMA"


class BindingFailure(GateFailure):
    kind = "BINDING"


class AdmissionFailure(GateFailure):
    kind = "ADMISSION"


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SchemaFailure(f"{label} does not exist")

    if not path.is_file():
        raise SchemaFailure(f"{label} is not a regular file")

    if path.is_symlink():
        raise SchemaFailure(f"{label} must not be a symbolic link")

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaFailure(f"{label} is not valid JSON") from exc

    if not isinstance(value, dict):
        raise SchemaFailure(f"{label} root must be an object")

    return value


def load_schema(path: Path, label: str) -> dict[str, Any]:
    schema = load_object(path, label)

    if (
        schema.get("$schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        raise SchemaFailure(f"{label} draft is unexpected")

    return schema


def json_type_matches(value: Any, expected: str) -> bool:
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


def parse_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise SchemaFailure(
            f"{label} is not a valid date-time"
        ) from exc

    if parsed.tzinfo is None:
        raise SchemaFailure(
            f"{label} must include a timezone"
        )

    return parsed


def validate_schema_subset(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    expected_type = schema.get("type")

    if (
        expected_type is not None
        and not json_type_matches(value, expected_type)
    ):
        raise SchemaFailure(f"{path} has invalid type")

    if "const" in schema and value != schema["const"]:
        raise SchemaFailure(f"{path} does not match const")

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaFailure(f"{path} is not an allowed value")

    if isinstance(value, str):
        minimum = schema.get("minLength")

        if minimum is not None and len(value) < minimum:
            raise SchemaFailure(f"{path} is too short")

        pattern = schema.get("pattern")

        if pattern is not None and re.search(pattern, value) is None:
            raise SchemaFailure(
                f"{path} does not match required pattern"
            )

        if schema.get("format") == "date-time":
            parse_datetime(value, path)

    if isinstance(value, dict):
        required = schema.get("required", [])

        for field in required:
            if field not in value:
                raise SchemaFailure(
                    f"{path}.{field} is required"
                )

        properties = schema.get("properties", {})

        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))

            if unknown:
                raise SchemaFailure(
                    f"{path} has unknown field: {unknown[0]}"
                )

        for field, child_schema in properties.items():
            if field in value:
                validate_schema_subset(
                    value[field],
                    child_schema,
                    f"{path}.{field}",
                )

    for rule in schema.get("allOf", []):
        condition = rule.get("if")

        if condition is None:
            validate_schema_subset(value, rule, path)
            continue

        try:
            validate_schema_subset(value, condition, path)
            matched = True
        except SchemaFailure:
            matched = False

        if matched and "then" in rule:
            validate_schema_subset(
                value,
                rule["then"],
                path,
            )

        if not matched and "else" in rule:
            validate_schema_subset(
                value,
                rule["else"],
                path,
            )


def require_equal(label: str, *values: Any) -> None:
    if not values:
        return

    first = values[0]

    if any(value != first for value in values[1:]):
        raise BindingFailure(f"{label} mismatch")


def evaluate_pre_execution_admission(
    *,
    decision_path: Path,
    admission_path: Path,
    expected_enforcement_id: str,
    expected_admission_id: str,
    expected_execution_request_id: str,
    expected_certification_id: str,
    expected_lineage_id: str,
    expected_subject_identity: str,
    expected_action: str,
    expected_runtime_target: str,
    expected_scope: dict[str, Any],
    evaluation_time: datetime | None = None,
) -> dict[str, str]:
    decision = load_object(
        decision_path,
        "decision enforcement record",
    )

    admission = load_object(
        admission_path,
        "authorization admission record",
    )

    decision_schema = load_schema(
        DECISION_SCHEMA_PATH,
        "decision enforcement schema",
    )

    admission_schema = load_schema(
        ADMISSION_SCHEMA_PATH,
        "authorization admission schema",
    )

    validate_schema_subset(
        decision,
        decision_schema,
    )

    validate_schema_subset(
        admission,
        admission_schema,
    )

    if decision["enforcement_state"] != "ACCEPTED":
        raise AdmissionFailure(
            "decision enforcement is not ACCEPTED"
        )

    if admission["admission_state"] != "ADMITTED":
        raise AdmissionFailure(
            "authorization admission is not ADMITTED"
        )

    require_equal(
        "decision enforcement identity",
        expected_enforcement_id,
        decision["enforcement_id"],
        admission["decision_enforcement_id"],
    )

    require_equal(
        "admission identity",
        expected_admission_id,
        admission["admission_id"],
    )

    require_equal(
        "execution request identity",
        expected_execution_request_id,
        admission["execution_request_id"],
    )

    require_equal(
        "certification identity",
        expected_certification_id,
        decision["certification_id"],
        admission["certification_id"],
    )

    require_equal(
        "lineage identity",
        expected_lineage_id,
        decision["lineage_id"],
        admission["lineage_id"],
    )

    require_equal(
        "subject identity",
        expected_subject_identity,
        decision["subject_identity"],
        admission["subject_identity"],
    )

    require_equal(
        "action identity",
        expected_action,
        decision["action"],
        admission["action"],
    )

    require_equal(
        "scope",
        expected_scope,
        decision["scope"],
        admission["scope"],
    )

    require_equal(
        "runtime target",
        expected_runtime_target,
        admission["runtime_target"],
    )

    decision_created = parse_datetime(
        decision["created_at"],
        "$.decision.created_at",
    )

    admission_created = parse_datetime(
        admission["created_at"],
        "$.admission.created_at",
    )

    admission_expires = parse_datetime(
        admission["expires_at"],
        "$.admission.expires_at",
    )

    now = evaluation_time or datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise AdmissionFailure(
            "evaluation time must include a timezone"
        )

    if decision_created > admission_created:
        raise AdmissionFailure(
            "admission predates decision enforcement"
        )

    if admission_created > admission_expires:
        raise AdmissionFailure(
            "admission expires before it is created"
        )

    if admission_created > now:
        raise AdmissionFailure(
            "admission is not yet effective"
        )

    if now > admission_expires:
        raise AdmissionFailure(
            "admission has expired"
        )

    return {
        "decision_enforcement_id": decision["enforcement_id"],
        "admission_id": admission["admission_id"],
        "execution_request_id": admission["execution_request_id"],
        "certification_id": admission["certification_id"],
        "lineage_id": admission["lineage_id"],
        "subject_identity": admission["subject_identity"],
        "action": admission["action"],
        "runtime_target": admission["runtime_target"],
    }


def parse_expected_scope(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AdmissionFailure(
            "expected scope is not valid JSON"
        ) from exc

    if not isinstance(parsed, dict):
        raise AdmissionFailure(
            "expected scope must be a JSON object"
        )

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a StorageOps governance decision and "
            "authorization admission before runtime dispatch. "
            "This command never dispatches runtime execution."
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
        "--expected-enforcement-id",
        required=True,
    )

    parser.add_argument(
        "--expected-admission-id",
        required=True,
    )

    parser.add_argument(
        "--expected-execution-request-id",
        required=True,
    )

    parser.add_argument(
        "--expected-certification-id",
        required=True,
    )

    parser.add_argument(
        "--expected-lineage-id",
        required=True,
    )

    parser.add_argument(
        "--expected-subject-identity",
        required=True,
    )

    parser.add_argument(
        "--expected-action",
        required=True,
    )

    parser.add_argument(
        "--expected-runtime-target",
        required=True,
    )

    parser.add_argument(
        "--expected-scope-json",
        required=True,
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        expected_scope = parse_expected_scope(
            args.expected_scope_json
        )

        result = evaluate_pre_execution_admission(
            decision_path=args.decision_enforcement,
            admission_path=args.authorization_admission,
            expected_enforcement_id=args.expected_enforcement_id,
            expected_admission_id=args.expected_admission_id,
            expected_execution_request_id=(
                args.expected_execution_request_id
            ),
            expected_certification_id=(
                args.expected_certification_id
            ),
            expected_lineage_id=args.expected_lineage_id,
            expected_subject_identity=(
                args.expected_subject_identity
            ),
            expected_action=args.expected_action,
            expected_runtime_target=(
                args.expected_runtime_target
            ),
            expected_scope=expected_scope,
        )

    except GateFailure as exc:
        print("PRE_DISPATCH_RESULT=DENY")
        print(f"FAILURE_KIND={exc.kind}")
        print(f"ERROR={exc}")
        return 1

    except Exception:
        print("PRE_DISPATCH_RESULT=DENY")
        print("FAILURE_KIND=INTERNAL")
        print("ERROR=pre-execution admission gate failed")
        return 1

    print("PRE_DISPATCH_RESULT=ALLOW")
    print("SCHEMA_VALIDATION=PASS")
    print("DECISION_ENFORCEMENT_VALIDATION=PASS")
    print("AUTHORIZATION_ADMISSION_VALIDATION=PASS")
    print("EXPECTED_CONTEXT_BINDING=PASS")
    print("TEMPORAL_VALIDITY=PASS")

    for key in (
        "decision_enforcement_id",
        "admission_id",
        "execution_request_id",
        "certification_id",
        "lineage_id",
        "subject_identity",
        "action",
        "runtime_target",
    ):
        print(f"{key.upper()}={result[key]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
