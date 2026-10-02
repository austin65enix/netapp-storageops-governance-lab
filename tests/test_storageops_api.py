from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import api.routes.evidence as evidence_route
import api.routes.inventory as inventory_route
import api.routes.operational as operational_route
from adapters.ontap_adapter import OntapAdapter
from api.config import load_settings
from evidence.repository import EvidenceRepository
from inventory.repository import InventorySnapshotRepository
from models.storage import (
    StorageCapacity,
    StorageLUN,
    StorageSnapshot,
    StorageVolume,
)
from models.operational_summary import (
    CollectionHealth,
    ScheduledCollectionOperationalSummary,
)


EXPECTED_API_PATHS = {
    "/api/storage/volumes",
    "/api/storage/luns",
    "/api/storage/snapshots",
    "/api/storage/capacity",
    "/api/inventory/latest",
    "/api/inventory/runs",
    "/api/inventory/collect",
    "/api/evidence/changes",
    "/api/operational/collection-summary",
}


def fake_volumes() -> list[StorageVolume]:
    return [
        StorageVolume(
            id="vol-001",
            name="vol_business_data",
            svm_id="svm-001",
            protocol="nfs",
            state="online",
            size_bytes=100,
            used_bytes=60,
            available_bytes=40,
        )
    ]


def fake_luns() -> list[StorageLUN]:
    return [
        StorageLUN(
            id="lun-001",
            name="db-lun-01",
            volume_id="vol-001",
            size_bytes=50,
            os_type="linux",
            state="online",
        )
    ]


def fake_snapshots() -> list[StorageSnapshot]:
    return [
        StorageSnapshot(
            id="snap-001",
            name="daily.test",
            volume_id="vol-001",
            created_time=(
                "2026-07-31T01:00:00+00:00"
            ),
            size_bytes=10,
        )
    ]


def fake_capacity() -> StorageCapacity:
    return StorageCapacity(
        total_bytes=100,
        used_bytes=60,
        available_bytes=40,
        utilization_percent=60.0,
    )


def patch_adapter_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        lambda self: fake_volumes(),
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_luns",
        lambda self: fake_luns(),
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_snapshots",
        lambda self: fake_snapshots(),
    )

    monkeypatch.setattr(
        OntapAdapter,
        "get_capacity",
        lambda self: fake_capacity(),
    )


def test_health_contract(
    client: TestClient,
) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["source"] == "ONTAP-LAB-01"
    assert payload["ontap_timeout_seconds"] > 0


def test_openapi_route_baseline(
    client: TestClient,
) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]
    actual_paths = set(paths)

    assert EXPECTED_API_PATHS <= actual_paths
    assert "post" in paths[
        "/api/inventory/collect"
    ]
    assert "get" in paths[
        "/api/operational/collection-summary"
    ]


def operational_summary(
    health: CollectionHealth = CollectionHealth.HEALTHY,
) -> ScheduledCollectionOperationalSummary:
    eastern = timezone(timedelta(hours=-4))
    return ScheduledCollectionOperationalSummary(
        latest_run_id="collect-20260810T115800Z-ab12cd34",
        latest_run_status="PASS",
        latest_run_started_at=datetime(
            2026, 8, 10, 7, 58, tzinfo=eastern
        ),
        latest_run_completed_at=datetime(
            2026, 8, 10, 7, 59, tzinfo=eastern
        ),
        last_success_at=datetime(
            2026, 8, 10, 7, 59, tzinfo=eastern
        ),
        last_failure_at=None,
        consecutive_failures=0,
        timer_enabled=True,
        timer_active=True,
        next_trigger=datetime(
            2026, 8, 10, 8, 5, tzinfo=eastern
        ),
        collection_health=health,
    )


def test_operational_collection_summary_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operational_route,
        "read_scheduled_collection_operational_summary",
        operational_summary,
    )
    response = client.get("/api/operational/collection-summary")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "command", "contract_version", "timestamp", "result",
        "exit_code", "data", "errors", "evidence_file",
    }
    assert payload["command"] == "collection-summary"
    assert payload["contract_version"] == "1"
    assert payload["result"] == "PASS"
    assert payload["exit_code"] == 0
    assert payload["errors"] == []
    assert payload["evidence_file"] is None
    assert payload["timestamp"].endswith("Z")
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


@pytest.mark.parametrize("health", list(CollectionHealth))
def test_operational_collection_health_is_informational(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    health: CollectionHealth,
) -> None:
    monkeypatch.setattr(
        operational_route,
        "read_scheduled_collection_operational_summary",
        lambda: operational_summary(health),
    )
    payload = client.get(
        "/api/operational/collection-summary"
    ).json()
    assert payload["result"] == "PASS"
    assert payload["exit_code"] == 0
    assert payload["data"]["collection_health"] == health.value


def test_operational_collection_summary_unexpected_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_detail = "secret reader implementation detail"

    def fail() -> ScheduledCollectionOperationalSummary:
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(
        operational_route,
        "read_scheduled_collection_operational_summary",
        fail,
    )

    response = client.get(
        "/api/operational/collection-summary"
    )

    assert response.status_code == 500
    payload = response.json()
    assert set(payload) == {
        "command", "contract_version", "timestamp", "result",
        "exit_code", "data", "errors", "evidence_file",
    }
    assert payload["command"] == "collection-summary"
    assert payload["contract_version"] == "1"
    assert payload["timestamp"].endswith("Z")
    assert payload["result"] == "FAIL"
    assert payload["exit_code"] == 100
    assert payload["data"] == {}
    assert payload["errors"]
    assert payload["evidence_file"] is None
    assert internal_detail not in response.text
    assert "Traceback" not in response.text


def test_storage_resource_endpoints(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_adapter_success(monkeypatch)

    volume_response = client.get(
        "/api/storage/volumes"
    )
    lun_response = client.get(
        "/api/storage/luns"
    )
    snapshot_response = client.get(
        "/api/storage/snapshots"
    )
    capacity_response = client.get(
        "/api/storage/capacity"
    )

    assert volume_response.status_code == 200
    assert lun_response.status_code == 200
    assert snapshot_response.status_code == 200
    assert capacity_response.status_code == 200

    volume = volume_response.json()[0]

    assert volume["id"] == "vol-001"
    assert volume["svm_id"] == "svm-001"
    assert volume["utilization_percent"] == 60.0

    lun = lun_response.json()[0]

    assert lun["id"] == "lun-001"
    assert lun["volume_id"] == "vol-001"
    assert lun["os_type"] == "linux"

    snapshot = snapshot_response.json()[0]

    assert snapshot["id"] == "snap-001"
    assert snapshot["volume_id"] == "vol-001"

    capacity = capacity_response.json()

    assert capacity["total_bytes"] == 100
    assert capacity["utilization_percent"] == 60.0


def test_inventory_collection_and_persistence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_adapter_success(monkeypatch)

    snapshot_repository = (
        InventorySnapshotRepository(
            snapshot_dir=str(
                tmp_path / "snapshots"
            )
        )
    )

    evidence_repository = EvidenceRepository(
        evidence_dir=str(
            tmp_path / "evidence"
        )
    )

    monkeypatch.setattr(
        inventory_route,
        "get_inventory_repository",
        lambda: snapshot_repository,
    )

    monkeypatch.setattr(
        inventory_route,
        "get_evidence_repository",
        lambda: evidence_repository,
    )

    response = client.post(
        "/api/inventory/collect"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "collected"
    assert payload["resource_summary"] == {
        "volume": 1,
        "lun": 1,
        "snapshot": 1,
    }

    assert payload["change_count"] == 0
    assert payload["changes"] == []
    assert payload["evidence_file"] is None

    collected_at = datetime.fromisoformat(
        payload["collected_at"]
    )

    assert collected_at.utcoffset() == timedelta(0)

    snapshot_file = Path(
        payload["snapshot_file"]
    )

    assert snapshot_file.exists()

    latest_response = client.get(
        "/api/inventory/latest"
    )

    assert latest_response.status_code == 200

    latest = latest_response.json()

    assert latest["collected_at"] == (
        payload["collected_at"]
    )

    assert (
        latest["resources"]["volume"][
            "resource_count"
        ]
        == 1
    )


def test_inventory_runs_endpoint(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_adapter_success(monkeypatch)

    repository = InventorySnapshotRepository(
        snapshot_dir=str(
            tmp_path / "snapshots"
        )
    )

    monkeypatch.setattr(
        inventory_route,
        "get_inventory_repository",
        lambda: repository,
    )

    collect_response = client.post(
        "/api/inventory/collect"
    )

    assert collect_response.status_code == 200

    runs_response = client.get(
        "/api/inventory/runs"
    )

    assert runs_response.status_code == 200

    payload = runs_response.json()

    assert payload["count"] == 1
    assert len(payload["runs"]) == 1
    assert payload["runs"][0][
        "filename"
    ].startswith("inventory_")


def test_evidence_query_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "event_id": "evt-test-001",
            "source": "ONTAP-LAB-01",
            "collected_at": (
                "2026-07-31T02:00:00+00:00"
            ),
            "resource_type": "volume",
            "change_type": "ADDED",
            "before_count": 1,
            "after_count": 2,
            "delta": 1,
        }
    ]

    monkeypatch.setattr(
        evidence_route.EvidenceRepository,
        "load",
        lambda self: records,
    )

    response = client.get(
        "/api/evidence/changes"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["count"] == 1
    assert payload["changes"][0][
        "change_type"
    ] == "ADDED"


def test_ontap_unavailable_error_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_connection_error(self):
        raise requests.ConnectionError(
            "ONTAP source unavailable"
        )

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        raise_connection_error,
    )

    response = client.get(
        "/api/storage/volumes"
    )

    assert response.status_code == 502

    payload = response.json()

    assert payload == {
        "error": {
            "code": "ONTAP_UNAVAILABLE",
            "message": (
                "Unable to retrieve volume data "
                "from the ONTAP source."
            ),
            "path": "/api/storage/volumes",
        }
    }


def test_ontap_timeout_error_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(self):
        raise requests.Timeout(
            "ONTAP source timed out"
        )

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        raise_timeout,
    )

    response = client.get(
        "/api/storage/volumes"
    )

    assert response.status_code == 504

    payload = response.json()

    assert payload == {
        "error": {
            "code": "ONTAP_TIMEOUT",
            "message": (
                "ONTAP request timed out while "
                "performing volume data."
            ),
            "path": "/api/storage/volumes",
        }
    }


def test_configuration_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ONTAP_TIMEOUT_SECONDS",
        "2.5",
    )

    valid_settings = load_settings()

    assert (
        valid_settings.ontap_timeout_seconds
        == 2.5
    )

    monkeypatch.setenv(
        "ONTAP_TIMEOUT_SECONDS",
        "0",
    )

    with pytest.raises(
        ValueError,
        match="must be greater than zero",
    ):
        load_settings()

    monkeypatch.setenv(
        "ONTAP_TIMEOUT_SECONDS",
        "invalid",
    )

    with pytest.raises(
        ValueError,
        match="must be a number",
    ):
        load_settings()
