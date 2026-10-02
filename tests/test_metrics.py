import pytest
import requests
from fastapi.testclient import TestClient

from adapters.ontap_adapter import OntapAdapter


def test_metrics_endpoint_contract(
    client: TestClient,
) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200

    content_type = response.headers[
        "content-type"
    ]

    assert content_type.startswith(
        "text/plain"
    )

    body = response.text

    required_metrics = {
        "storageops_info",
        "storageops_up",
        "storageops_ontap_up",
        "storageops_http_requests_total",
        "storageops_http_responses_total",
        (
            "storageops_http_request_"
            "duration_seconds"
        ),
        "storageops_ontap_requests_total",
        "storageops_ontap_errors_total",
        "storageops_inventory_objects",
        "storageops_capacity_bytes",
        (
            "storageops_volume_"
            "utilization_percent"
        ),
        "storageops_snapshot_runs_total",
        "storageops_diff_events_total",
    }

    for metric in required_metrics:
        assert metric in body


def test_http_metrics_are_recorded(
    client: TestClient,
) -> None:
    health_response = client.get("/healthz")

    assert health_response.status_code == 200

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200

    body = metrics_response.text

    assert (
        'method="GET"'
        in body
    )

    assert (
        'endpoint="/healthz"'
        in body
    )

    assert (
        'status_code="200"'
        in body
    )


def test_ontap_unavailable_metric(
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

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200

    body = metrics_response.text

    assert (
        'storageops_ontap_up'
        in body
    )

    assert (
        'result="unavailable"'
        in body
    )

    assert (
        'error_type="unavailable"'
        in body
    )


def test_volume_and_capacity_metrics(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from models.storage import (
        StorageCapacity,
        StorageVolume,
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        lambda self: [
            StorageVolume(
                id="vol-metric-001",
                name="metric-volume",
                svm_id="svm-metric",
                protocol="nfs",
                state="online",
                size_bytes=100,
                used_bytes=75,
                available_bytes=25,
            )
        ],
    )

    monkeypatch.setattr(
        OntapAdapter,
        "get_capacity",
        lambda self: StorageCapacity(
            total_bytes=1000,
            used_bytes=700,
            available_bytes=300,
            utilization_percent=70.0,
        ),
    )

    volume_response = client.get(
        "/api/storage/volumes"
    )
    capacity_response = client.get(
        "/api/storage/capacity"
    )

    assert volume_response.status_code == 200
    assert capacity_response.status_code == 200

    body = client.get("/metrics").text

    assert (
        'storageops_volume_utilization_percent'
        '{source="ONTAP-LAB-01",'
        'svm="svm-metric",'
        'volume="metric-volume"} 75.0'
        in body
    )

    assert (
        'storageops_capacity_bytes'
        '{category="total",'
        'source="ONTAP-LAB-01"} 1000.0'
        in body
    )

    assert (
        'storageops_capacity_bytes'
        '{category="used",'
        'source="ONTAP-LAB-01"} 700.0'
        in body
    )

    assert (
        'storageops_capacity_bytes'
        '{category="available",'
        'source="ONTAP-LAB-01"} 300.0'
        in body
    )


def test_volume_metric_stale_labels_are_removed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from models.storage import StorageVolume

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        lambda self: [
            StorageVolume(
                id="vol-old",
                name="old-volume",
                svm_id="svm-old",
                protocol="nfs",
                state="online",
                size_bytes=100,
                used_bytes=50,
                available_bytes=50,
            )
        ],
    )

    assert client.get(
        "/api/storage/volumes"
    ).status_code == 200

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        lambda self: [
            StorageVolume(
                id="vol-new",
                name="new-volume",
                svm_id="svm-new",
                protocol="nfs",
                state="online",
                size_bytes=100,
                used_bytes=40,
                available_bytes=60,
            )
        ],
    )

    assert client.get(
        "/api/storage/volumes"
    ).status_code == 200

    body = client.get("/metrics").text

    assert 'volume="new-volume"' in body
    assert 'volume="old-volume"' not in body


def test_inventory_snapshot_success_metric(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.routes.inventory as inventory_route
    from evidence.repository import EvidenceRepository
    from inventory.repository import (
        InventorySnapshotRepository,
    )
    from models.storage import (
        StorageCapacity,
        StorageLUN,
        StorageSnapshot,
        StorageVolume,
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_volumes",
        lambda self: [
            StorageVolume(
                id="vol-001",
                name="volume-one",
                svm_id="svm-001",
                protocol="nfs",
                state="online",
                size_bytes=100,
                used_bytes=50,
                available_bytes=50,
            )
        ],
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_luns",
        lambda self: [
            StorageLUN(
                id="lun-001",
                name="lun-one",
                volume_id="vol-001",
                size_bytes=50,
                os_type="linux",
                state="online",
            )
        ],
    )

    monkeypatch.setattr(
        OntapAdapter,
        "list_snapshots",
        lambda self: [
            StorageSnapshot(
                id="snap-001",
                name="snapshot-one",
                volume_id="vol-001",
                created_time=(
                    "2026-08-04T03:00:00+00:00"
                ),
                size_bytes=10,
            )
        ],
    )

    monkeypatch.setattr(
        OntapAdapter,
        "get_capacity",
        lambda self: StorageCapacity(
            total_bytes=100,
            used_bytes=50,
            available_bytes=50,
            utilization_percent=50.0,
        ),
    )

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

    body = client.get("/metrics").text

    assert (
        'storageops_inventory_objects'
        '{resource_type="volume",'
        'source="ONTAP-LAB-01"} 1.0'
        in body
    )

    assert (
        'storageops_snapshot_runs_total'
        '{result="success"}'
        in body
    )


def test_diff_event_metric() -> None:
    from api.metrics import (
        record_diff_events,
        render_metrics,
    )
    from evidence.change_record import (
        StorageChangeEvidence,
    )

    record_diff_events(
        [
            StorageChangeEvidence(
                event_id="evt-metric-001",
                source="ONTAP-LAB-01",
                collected_at=(
                    "2026-08-04T03:00:00+00:00"
                ),
                resource_type="volume",
                change_type="ADDED",
                before_count=2,
                after_count=3,
                delta=1,
            )
        ]
    )

    payload, _ = render_metrics()
    body = payload.decode()

    assert (
        'storageops_diff_events_total'
        '{change_type="ADDED",'
        'resource_type="volume"}'
        in body
    )
