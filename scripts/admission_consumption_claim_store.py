#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

GATE_PATH = (
    ROOT
    / "scripts"
    / "check_governance_admission.py"
)

CLAIM_SCHEMA_PATH = (
    ROOT
    / "operational"
    / "contracts"
    / "admission-consumption-claim.schema.json"
)


class ClaimPrimitiveFailure(Exception):
    pass


class ClaimInputFailure(ClaimPrimitiveFailure):
    pass


class ClaimAlreadyConsumed(ClaimPrimitiveFailure):
    pass


class ClaimStoreFailure(ClaimPrimitiveFailure):
    pass


class ClaimDurabilityFailure(ClaimPrimitiveFailure):
    pass


@dataclass(frozen=True)
class ClaimCreateResult:
    claim_path: Path
    claim_sha256: str
    consumption_key_sha256: str


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "storageops_claim_schema_gate",
        GATE_PATH,
    )

    if spec is None or spec.loader is None:
        raise ClaimStoreFailure(
            "unable to load governance schema validator"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def _load_claim_schema() -> dict[str, Any]:
    try:
        value = json.loads(
            CLAIM_SCHEMA_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ClaimStoreFailure(
            "claim schema is not readable valid JSON"
        ) from exc

    if not isinstance(value, dict):
        raise ClaimStoreFailure(
            "claim schema must be a JSON object"
        )

    return value


def _validate_claim_payload(
    claim: dict[str, Any],
) -> None:
    if not isinstance(claim, dict):
        raise ClaimInputFailure(
            "claim must be a JSON object"
        )

    gate = _load_gate_module()
    schema = _load_claim_schema()

    try:
        gate.validate_schema_subset(
            claim,
            schema,
        )
    except gate.SchemaFailure as exc:
        raise ClaimInputFailure(
            "claim schema validation failed"
        ) from exc


def _require_nonempty_string(
    value: Any,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
    ):
        raise ClaimInputFailure(
            f"{label} must be a non-empty string"
        )

    return value


def derive_consumption_key_sha256(
    *,
    admission_id: str,
    execution_request_id: str,
) -> str:
    admission_id = _require_nonempty_string(
        admission_id,
        "admission_id",
    )

    execution_request_id = (
        _require_nonempty_string(
            execution_request_id,
            "execution_request_id",
        )
    )

    key_bytes = json.dumps(
        {
            "admission_id": admission_id,
            "execution_request_id": (
                execution_request_id
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return hashlib.sha256(
        key_bytes
    ).hexdigest()


def claim_filename_for(
    *,
    admission_id: str,
    execution_request_id: str,
) -> str:
    digest = derive_consumption_key_sha256(
        admission_id=admission_id,
        execution_request_id=(
            execution_request_id
        ),
    )

    return f"claim-{digest}.json"


def _serialize_claim(
    claim: dict[str, Any],
) -> bytes:
    try:
        return (
            json.dumps(
                claim,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("utf-8")
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ClaimInputFailure(
            "claim is not JSON serializable"
        ) from exc


def _required_os_flag(
    name: str,
) -> int:
    value = getattr(
        os,
        name,
        None,
    )

    if not isinstance(value, int):
        raise ClaimStoreFailure(
            f"required OS flag is unavailable: {name}"
        )

    return value


def _open_claim_store(
    claim_store: Path,
) -> int:
    flags = os.O_RDONLY

    flags |= _required_os_flag(
        "O_DIRECTORY"
    )

    flags |= _required_os_flag(
        "O_NOFOLLOW"
    )

    flags |= _required_os_flag(
        "O_CLOEXEC"
    )

    try:
        directory_fd = os.open(
            os.fspath(claim_store),
            flags,
        )
    except OSError as exc:
        raise ClaimStoreFailure(
            "claim store must already exist as "
            "a directly opened non-symlink directory"
        ) from exc

    try:
        metadata = os.fstat(
            directory_fd
        )

        if not stat.S_ISDIR(
            metadata.st_mode
        ):
            raise ClaimStoreFailure(
                "claim store is not a directory"
            )

    except Exception:
        os.close(
            directory_fd
        )
        raise

    return directory_fd


def _write_all(
    file_descriptor: int,
    payload: bytes,
) -> None:
    offset = 0

    while offset < len(payload):
        written = os.write(
            file_descriptor,
            payload[offset:],
        )

        if written <= 0:
            raise OSError(
                "claim write made no forward progress"
            )

        offset += written


def create_claim_once(
    *,
    claim_store: Path,
    claim: dict[str, Any],
) -> ClaimCreateResult:
    _validate_claim_payload(
        claim
    )

    admission_id = _require_nonempty_string(
        claim.get("admission_id"),
        "admission_id",
    )

    execution_request_id = (
        _require_nonempty_string(
            claim.get(
                "execution_request_id"
            ),
            "execution_request_id",
        )
    )

    consumption_key_sha256 = (
        derive_consumption_key_sha256(
            admission_id=admission_id,
            execution_request_id=(
                execution_request_id
            ),
        )
    )

    filename = (
        f"claim-"
        f"{consumption_key_sha256}"
        f".json"
    )

    payload = _serialize_claim(
        claim
    )

    claim_sha256 = hashlib.sha256(
        payload
    ).hexdigest()

    claim_store = Path(
        os.path.abspath(
            os.fspath(claim_store)
        )
    )

    directory_fd = _open_claim_store(
        claim_store
    )

    file_descriptor: int | None = None

    create_flags = (
        os.O_WRONLY
        | _required_os_flag("O_CREAT")
        | _required_os_flag("O_EXCL")
        | _required_os_flag("O_NOFOLLOW")
        | _required_os_flag("O_CLOEXEC")
    )

    try:
        try:
            file_descriptor = os.open(
                filename,
                create_flags,
                0o600,
                dir_fd=directory_fd,
            )

        except FileExistsError as exc:
            raise ClaimAlreadyConsumed(
                "consumption key is already occupied"
            ) from exc

        except OSError as exc:
            if exc.errno == getattr(
                __import__("errno"),
                "EEXIST",
            ):
                raise ClaimAlreadyConsumed(
                    "consumption key is already occupied"
                ) from exc

            raise ClaimStoreFailure(
                "unable to exclusively create claim"
            ) from exc

        try:
            os.fchmod(
                file_descriptor,
                0o600,
            )

            _write_all(
                file_descriptor,
                payload,
            )

            os.fsync(
                file_descriptor
            )

        except OSError as exc:
            raise ClaimDurabilityFailure(
                "claim was exclusively created but "
                "claim byte durability failed; "
                "the claim key remains consumed"
            ) from exc

        finally:
            if file_descriptor is not None:
                try:
                    os.close(
                        file_descriptor
                    )
                except OSError as exc:
                    raise ClaimDurabilityFailure(
                        "claim was exclusively created but "
                        "claim close failed; "
                        "the claim key remains consumed"
                    ) from exc

        file_descriptor = None

        try:
            os.fsync(
                directory_fd
            )
        except OSError as exc:
            raise ClaimDurabilityFailure(
                "claim was created but directory "
                "durability could not be confirmed; "
                "the claim key remains consumed"
            ) from exc

    finally:
        if file_descriptor is not None:
            try:
                os.close(
                    file_descriptor
                )
            except OSError:
                pass

        os.close(
            directory_fd
        )

    return ClaimCreateResult(
        claim_path=(
            claim_store
            / filename
        ),
        claim_sha256=claim_sha256,
        consumption_key_sha256=(
            consumption_key_sha256
        ),
    )
