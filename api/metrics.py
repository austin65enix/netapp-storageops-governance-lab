from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from api.config import settings


APP_VERSION = "0.3.0"


STORAGEOPS_INFO = Gauge(
    "storageops_info",
    "StorageOps application identity.",
    [
        "version",
        "source",
    ],
)

STORAGEOPS_UP = Gauge(
    "storageops_up",
    "StorageOps API process operational status.",
)

ONTAP_UP = Gauge(
    "storageops_ontap_up",
    "Configured ONTAP source reachability.",
    [
        "source",
    ],
)

HTTP_REQUESTS = Counter(
    "storageops_http_requests_total",
    "StorageOps HTTP requests.",
    [
        "method",
        "endpoint",
    ],
)

HTTP_RESPONSES = Counter(
    "storageops_http_responses_total",
    "StorageOps HTTP responses.",
    [
        "method",
        "endpoint",
        "status_code",
    ],
)

HTTP_DURATION = Histogram(
    "storageops_http_request_duration_seconds",
    "StorageOps HTTP request duration.",
    [
        "method",
        "endpoint",
    ],
)

ONTAP_REQUESTS = Counter(
    "storageops_ontap_requests_total",
    "Requests made to the ONTAP adapter.",
    [
        "operation",
        "result",
    ],
)

ONTAP_ERRORS = Counter(
    "storageops_ontap_errors_total",
    "Controlled ONTAP dependency errors.",
    [
        "operation",
        "error_type",
    ],
)


STORAGEOPS_INFO.labels(
    version=APP_VERSION,
    source=settings.storage_source,
).set(1)

STORAGEOPS_UP.set(1)

ONTAP_UP.labels(
    source=settings.storage_source,
).set(1)


def render_metrics() -> tuple[bytes, str]:
    return (
        generate_latest(),
        CONTENT_TYPE_LATEST,
    )


INVENTORY_OBJECTS = Gauge(
    "storageops_inventory_objects",
    "Current StorageOps inventory object count.",
    [
        "resource_type",
        "source",
    ],
)

CAPACITY_BYTES = Gauge(
    "storageops_capacity_bytes",
    "Current aggregate storage capacity in bytes.",
    [
        "category",
        "source",
    ],
)

VOLUME_UTILIZATION = Gauge(
    "storageops_volume_utilization_percent",
    "Current storage volume utilization percentage.",
    [
        "volume",
        "svm",
        "source",
    ],
)

SNAPSHOT_RUNS = Counter(
    "storageops_snapshot_runs_total",
    "Storage inventory snapshot workflow runs.",
    [
        "result",
    ],
)

DIFF_EVENTS = Counter(
    "storageops_diff_events_total",
    "Storage inventory change events.",
    [
        "resource_type",
        "change_type",
    ],
)


def update_inventory_object_metrics(
    resource_summary: dict[str, int],
) -> None:
    INVENTORY_OBJECTS.clear()

    for resource_type, count in (
        resource_summary.items()
    ):
        INVENTORY_OBJECTS.labels(
            resource_type=resource_type,
            source=settings.storage_source,
        ).set(count)


def update_capacity_metrics(
    capacity,
) -> None:
    values = {
        "total": capacity.total_bytes,
        "used": capacity.used_bytes,
        "available": capacity.available_bytes,
    }

    for category, value in values.items():
        CAPACITY_BYTES.labels(
            category=category,
            source=settings.storage_source,
        ).set(value)


def update_volume_metrics(
    volumes,
) -> None:
    VOLUME_UTILIZATION.clear()

    for volume in volumes:
        VOLUME_UTILIZATION.labels(
            volume=volume.name,
            svm=volume.svm_id,
            source=settings.storage_source,
        ).set(
            volume.utilization_percent
        )


def record_snapshot_run(
    result: str,
) -> None:
    SNAPSHOT_RUNS.labels(
        result=result,
    ).inc()


def record_diff_events(
    records,
) -> None:
    for record in records:
        DIFF_EVENTS.labels(
            resource_type=record.resource_type,
            change_type=record.change_type,
        ).inc()
