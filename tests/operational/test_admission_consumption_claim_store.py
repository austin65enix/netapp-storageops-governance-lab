from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]

PRIMITIVE_PATH = (
    ROOT
    / "scripts"
    / "admission_consumption_claim_store.py"
)


def _load_primitive(
    module_name: str,
):
    spec = importlib.util.spec_from_file_location(
        module_name,
        PRIMITIVE_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "unable to import claim primitive"
        )

    module = importlib.util.module_from_spec(spec)

    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


STORE = _load_primitive(
    "r40_admission_consumption_claim_store"
)


def _valid_claim(
    *,
    claim_id: str = "CLAIM-R40-001",
    admission_id: str = "ADM-R40-001",
    execution_request_id: str = "REQ-R40-001",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "claim_id": claim_id,
        "authority_material_id": "AUTH-R40-001",
        "authority_material_file": "/tmp/authority-r40.json",
        "authority_material_sha256": "1" * 64,
        "execution_request_id": execution_request_id,
        "admission_id": admission_id,
        "decision_enforcement_id": "ENF-R40-001",
        "certification_id": "CERT-R40-001",
        "lineage_id": "LIN-R40-001",
        "subject_identity": "storageops-agent",
        "action": "collect",
        "scope": {
            "target": "netapp-lab",
        },
        "runtime_target": "storageops-collect",
        "decision_enforcement_sha256": "2" * 64,
        "authorization_admission_sha256": "3" * 64,
        "claimed_at": "2026-08-28T06:40:00Z",
        "claim_state": "CLAIMED",
    }


def _canonical_claim_bytes(
    claim: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            claim,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def _claim_path(
    store: Path,
    claim: dict[str, Any],
) -> Path:
    return (
        store
        / STORE.claim_filename_for(
            admission_id=claim["admission_id"],
            execution_request_id=(
                claim["execution_request_id"]
            ),
        )
    )


def _concurrent_worker(
    *,
    store_path: str,
    claim: dict[str, Any],
    start_event,
    ready_queue,
    result_queue,
) -> None:
    try:
        module = _load_primitive(
            "r40_worker_"
            + str(os.getpid())
        )

    except BaseException as exc:
        ready_queue.put(
            "IMPORT_ERROR"
        )

        result_queue.put(
            (
                "ERROR",
                type(exc).__name__
                + ":"
                + str(exc),
            )
        )
        return

    ready_queue.put(
        "READY"
    )

    if not start_event.wait(10):
        result_queue.put(
            (
                "ERROR",
                "START_TIMEOUT",
            )
        )
        return

    try:
        result = module.create_claim_once(
            claim_store=Path(
                store_path
            ),
            claim=claim,
        )

    except module.ClaimAlreadyConsumed:
        result_queue.put(
            (
                "CONSUMED",
                "",
            )
        )

    except BaseException as exc:
        result_queue.put(
            (
                "ERROR",
                type(exc).__name__
                + ":"
                + str(exc),
            )
        )

    else:
        result_queue.put(
            (
                "SUCCESS",
                result.claim_path.name,
            )
        )


def test_first_create_persists_exact_canonical_claim(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    result = STORE.create_claim_once(
        claim_store=store,
        claim=claim,
    )

    expected_path = _claim_path(
        store,
        claim,
    )

    expected_bytes = (
        _canonical_claim_bytes(
            claim
        )
    )

    assert result.claim_path == expected_path

    assert (
        result.claim_path.read_bytes()
        == expected_bytes
    )

    assert result.claim_sha256 == (
        hashlib.sha256(
            expected_bytes
        ).hexdigest()
    )

    assert (
        result.consumption_key_sha256
        ==
        STORE.derive_consumption_key_sha256(
            admission_id=claim[
                "admission_id"
            ],
            execution_request_id=claim[
                "execution_request_id"
            ],
        )
    )

    assert stat.S_IMODE(
        result.claim_path.stat().st_mode
    ) == 0o600

    assert list(
        store.iterdir()
    ) == [
        expected_path
    ]


def test_sequential_duplicate_same_key_denied_without_mutation(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    first = STORE.create_claim_once(
        claim_store=store,
        claim=claim,
    )

    before = first.claim_path.read_bytes()

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert (
        first.claim_path.read_bytes()
        == before
    )


def test_same_key_different_claim_identity_denied_without_mutation(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    first_claim = _valid_claim()

    first = STORE.create_claim_once(
        claim_store=store,
        claim=first_claim,
    )

    before = first.claim_path.read_bytes()

    second_claim = copy.deepcopy(
        first_claim
    )

    second_claim[
        "claim_id"
    ] = "CLAIM-R40-OTHER"

    second_claim[
        "claimed_at"
    ] = "2026-08-28T06:41:00Z"

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=second_claim,
        )

    assert (
        first.claim_path.read_bytes()
        == before
    )


def test_different_execution_request_id_creates_different_key(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    first_claim = _valid_claim()

    second_claim = _valid_claim(
        claim_id="CLAIM-R40-002",
        execution_request_id=(
            "REQ-R40-002"
        ),
    )

    first = STORE.create_claim_once(
        claim_store=store,
        claim=first_claim,
    )

    second = STORE.create_claim_once(
        claim_store=store,
        claim=second_claim,
    )

    assert (
        first.claim_path
        != second.claim_path
    )

    assert (
        first.consumption_key_sha256
        != second.consumption_key_sha256
    )

    assert len(
        list(store.iterdir())
    ) == 2


def test_concurrent_same_key_exactly_one_success(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    worker_count = 8

    context = mp.get_context(
        "fork"
    )

    start_event = context.Event()

    ready_queue = context.Queue()
    result_queue = context.Queue()

    processes = [
        context.Process(
            target=_concurrent_worker,
            kwargs={
                "store_path": str(store),
                "claim": claim,
                "start_event": start_event,
                "ready_queue": ready_queue,
                "result_queue": result_queue,
            },
        )
        for _ in range(worker_count)
    ]

    try:
        for process in processes:
            process.start()

        ready = [
            ready_queue.get(
                timeout=10
            )
            for _ in processes
        ]

        assert ready == [
            "READY"
        ] * worker_count

        start_event.set()

        results = [
            result_queue.get(
                timeout=10
            )
            for _ in processes
        ]

        for process in processes:
            process.join(
                timeout=10
            )

            assert not process.is_alive()
            assert process.exitcode == 0

    finally:
        start_event.set()

        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(
                    timeout=5
                )

        ready_queue.close()
        result_queue.close()

        ready_queue.join_thread()
        result_queue.join_thread()

    successes = [
        item
        for item in results
        if item[0] == "SUCCESS"
    ]

    consumed = [
        item
        for item in results
        if item[0] == "CONSUMED"
    ]

    errors = [
        item
        for item in results
        if item[0] == "ERROR"
    ]

    assert len(successes) == 1
    assert len(consumed) == 7
    assert errors == []

    files = list(
        store.iterdir()
    )

    assert len(files) == 1

    assert files[0].read_bytes() == (
        _canonical_claim_bytes(
            claim
        )
    )


def test_malformed_existing_file_blocks_without_overwrite(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    path.write_bytes(
        b"{not-valid-json\n"
    )

    before = path.read_bytes()

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert path.read_bytes() == before


def test_zero_byte_existing_file_blocks_without_overwrite(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    path.write_bytes(
        b""
    )

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert path.read_bytes() == b""


def test_symlink_collision_blocks_without_following_target(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    target = (
        tmp_path
        / "symlink-target"
    )

    target.write_text(
        "sentinel\n",
        encoding="utf-8",
    )

    path = _claim_path(
        store,
        claim,
    )

    path.symlink_to(
        target
    )

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert path.is_symlink()

    assert target.read_text(
        encoding="utf-8"
    ) == "sentinel\n"


def test_directory_collision_blocks(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    path.mkdir()

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert path.is_dir()


def test_missing_store_fails_closed_without_auto_create(
    tmp_path: Path,
) -> None:
    store = (
        tmp_path
        / "missing-store"
    )

    claim = _valid_claim()

    with pytest.raises(
        STORE.ClaimStoreFailure
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert not store.exists()


def test_store_symlink_fails_closed(
    tmp_path: Path,
) -> None:
    real_store = (
        tmp_path
        / "real-store"
    )

    real_store.mkdir()

    store_link = (
        tmp_path
        / "store-link"
    )

    store_link.symlink_to(
        real_store,
        target_is_directory=True,
    )

    claim = _valid_claim()

    with pytest.raises(
        STORE.ClaimStoreFailure
    ):
        STORE.create_claim_once(
            claim_store=store_link,
            claim=claim,
        )

    assert list(
        real_store.iterdir()
    ) == []


def test_non_directory_store_fails_closed(
    tmp_path: Path,
) -> None:
    store = (
        tmp_path
        / "not-a-directory"
    )

    store.write_text(
        "sentinel\n",
        encoding="utf-8",
    )

    claim = _valid_claim()

    with pytest.raises(
        STORE.ClaimStoreFailure
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert store.read_text(
        encoding="utf-8"
    ) == "sentinel\n"


def test_invalid_claim_schema_fails_before_create(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    del claim[
        "execution_request_id"
    ]

    with pytest.raises(
        STORE.ClaimInputFailure
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    assert list(
        store.iterdir()
    ) == []


def test_write_failure_after_exclusive_create_preserves_occupancy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    real_write = STORE.os.write

    def fail_write(
        file_descriptor: int,
        payload: bytes,
    ) -> int:
        raise OSError(
            "R40 injected write failure"
        )

    monkeypatch.setattr(
        STORE.os,
        "write",
        fail_write,
    )

    with pytest.raises(
        STORE.ClaimDurabilityFailure,
        match=(
            "claim byte durability failed"
        ),
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    monkeypatch.setattr(
        STORE.os,
        "write",
        real_write,
    )

    assert path.exists()
    assert path.is_file()

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )


def test_file_fsync_failure_preserves_occupancy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    real_fsync = STORE.os.fsync

    calls = {
        "count": 0,
    }

    def fail_first_fsync(
        file_descriptor: int,
    ) -> None:
        calls["count"] += 1

        if calls["count"] == 1:
            raise OSError(
                "R40 injected file fsync failure"
            )

        real_fsync(
            file_descriptor
        )

    monkeypatch.setattr(
        STORE.os,
        "fsync",
        fail_first_fsync,
    )

    with pytest.raises(
        STORE.ClaimDurabilityFailure,
        match=(
            "claim byte durability failed"
        ),
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    monkeypatch.setattr(
        STORE.os,
        "fsync",
        real_fsync,
    )

    assert path.exists()
    assert path.is_file()

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )


def test_directory_fsync_failure_preserves_occupancy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim()

    path = _claim_path(
        store,
        claim,
    )

    real_fsync = STORE.os.fsync

    calls = {
        "count": 0,
    }

    def fail_second_fsync(
        file_descriptor: int,
    ) -> None:
        calls["count"] += 1

        if calls["count"] == 2:
            raise OSError(
                "R40 injected directory fsync failure"
            )

        real_fsync(
            file_descriptor
        )

    monkeypatch.setattr(
        STORE.os,
        "fsync",
        fail_second_fsync,
    )

    with pytest.raises(
        STORE.ClaimDurabilityFailure,
        match=(
            "directory durability "
            "could not be confirmed"
        ),
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )

    monkeypatch.setattr(
        STORE.os,
        "fsync",
        real_fsync,
    )

    assert path.exists()
    assert path.is_file()

    assert path.read_bytes() == (
        _canonical_claim_bytes(
            claim
        )
    )

    with pytest.raises(
        STORE.ClaimAlreadyConsumed
    ):
        STORE.create_claim_once(
            claim_store=store,
            claim=claim,
        )


def test_raw_identity_characters_are_hash_encoded_not_path_components(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()

    claim = _valid_claim(
        claim_id="CLAIM-R40-HASH",
        admission_id="../ADM/R40\nHASH",
        execution_request_id=(
            "../../REQ/R40\tHASH"
        ),
    )

    result = STORE.create_claim_once(
        claim_store=store,
        claim=claim,
    )

    assert (
        result.claim_path.parent
        == store
    )

    assert re.fullmatch(
        r"claim-[0-9a-f]{64}\.json",
        result.claim_path.name,
    )

    assert ".." not in (
        result.claim_path.name
    )

    assert "/" not in (
        result.claim_path.name
    )
