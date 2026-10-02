from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException
import requests

from adapters.ontap_adapter import OntapAdapter
from api.config import settings
from api.errors import (
    ontap_invalid_response_error,
    ontap_timeout_error,
    ontap_unavailable_error,
)
from api.metrics import (
    record_diff_events,
    record_snapshot_run,
    update_inventory_object_metrics,
)
from diff_engine.inventory_diff import (
    InventoryDiffEngine,
)
from evidence.change_record import (
    StorageChangeEvidence,
)
from evidence.repository import EvidenceRepository
from inventory.repository import (
    InventorySnapshotRepository,
)
from services.inventory_service import (
    InventoryService,
)


router = APIRouter(
    prefix="/api/inventory",
    tags=["inventory"],
)


def get_inventory_repository(
) -> InventorySnapshotRepository:
    return InventorySnapshotRepository(
        snapshot_dir=settings.snapshot_dir
    )


def get_evidence_repository(
) -> EvidenceRepository:
    return EvidenceRepository(
        evidence_dir=settings.evidence_dir
    )


@router.get("/latest")
def get_latest_inventory():
    repository = get_inventory_repository()
    latest = repository.load_latest()

    if latest is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INVENTORY_NOT_FOUND",
                "message": (
                    "No inventory snapshots are "
                    "available."
                ),
            },
        )

    return latest


@router.get("/runs")
def list_inventory_runs():
    repository = get_inventory_repository()
    files = repository.list_snapshot_files()

    return {
        "count": len(files),
        "runs": [
            {
                "filename": path.name,
                "path": str(path),
            }
            for path in files
        ],
    }


def _collect_inventory_impl():
    adapter = OntapAdapter(
        base_url=settings.ontap_base_url,
        timeout_seconds=(
            settings.ontap_timeout_seconds
        ),
    )

    service = InventoryService(adapter)
    snapshot_repository = (
        get_inventory_repository()
    )
    evidence_repository = (
        get_evidence_repository()
    )
    diff_engine = InventoryDiffEngine()

    before = snapshot_repository.load_latest()

    try:
        snapshots = service.collect()

    except requests.Timeout as exc:
        raise ontap_timeout_error(
            "inventory collection"
        ) from exc

    except requests.RequestException as exc:
        raise ontap_unavailable_error(
            "inventory collection"
        ) from exc

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ontap_invalid_response_error(
            "inventory collection"
        ) from exc

    saved_path = snapshot_repository.save(
        snapshots
    )

    resource_summary = {
        item.resource_type:
            item.resource_count
        for item in snapshots
    }

    update_inventory_object_metrics(
        resource_summary
    )

    after = snapshot_repository.load_latest()
    evidence_records = []

    if before is not None and after is not None:
        changes = diff_engine.compare(
            before,
            after,
        )

        for change in changes:
            if change.change_type == "UNCHANGED":
                continue

            evidence_records.append(
                StorageChangeEvidence(
                    event_id=str(uuid4()),
                    source=settings.storage_source,
                    collected_at=(
                        after["collected_at"]
                    ),
                    resource_type=(
                        change.resource_type
                    ),
                    change_type=(
                        change.change_type
                    ),
                    before_count=(
                        change.before_count
                    ),
                    after_count=(
                        change.after_count
                    ),
                    delta=change.delta,
                )
            )

    evidence_path = None

    if evidence_records:
        evidence_path = (
            evidence_repository.save(
                evidence_records
            )
        )

        record_diff_events(
            evidence_records
        )

    return {
        "status": "collected",
        "source": settings.storage_source,
        "collected_at": (
            snapshots[0].collected_at
        ),
        "snapshot_file": str(saved_path),
        "resource_summary": resource_summary,
        "change_count": len(
            evidence_records
        ),
        "changes": [
            asdict(record)
            for record in evidence_records
        ],
        "evidence_file": (
            str(evidence_path)
            if evidence_path is not None
            else None
        ),
    }


@router.post("/collect")
def collect_inventory():
    try:
        payload = _collect_inventory_impl()

    except Exception:
        record_snapshot_run(
            result="failure",
        )
        raise

    record_snapshot_run(
        result="success",
    )

    return payload
