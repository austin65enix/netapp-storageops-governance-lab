from dataclasses import asdict
from typing import Callable, TypeVar

from fastapi import APIRouter
import requests

from adapters.ontap_adapter import OntapAdapter
from api.config import settings
from api.errors import (
    ontap_invalid_response_error,
    ontap_timeout_error,
    ontap_unavailable_error,
)
from api.metrics import (
    ONTAP_ERRORS,
    ONTAP_REQUESTS,
    ONTAP_UP,
    update_capacity_metrics,
    update_volume_metrics,
)


router = APIRouter(
    prefix="/api/storage",
    tags=["storage"],
)


T = TypeVar("T")


def get_adapter() -> OntapAdapter:
    return OntapAdapter(
        base_url=settings.ontap_base_url,
        timeout_seconds=(
            settings.ontap_timeout_seconds
        ),
    )


def call_ontap(
    operation_name: str,
    metric_operation: str,
    operation: Callable[[], T],
) -> T:
    try:
        result = operation()

        ONTAP_REQUESTS.labels(
            operation=metric_operation,
            result="success",
        ).inc()

        ONTAP_UP.labels(
            source=settings.storage_source,
        ).set(1)

        return result

    except requests.Timeout as exc:
        ONTAP_REQUESTS.labels(
            operation=metric_operation,
            result="timeout",
        ).inc()

        ONTAP_ERRORS.labels(
            operation=metric_operation,
            error_type="timeout",
        ).inc()

        ONTAP_UP.labels(
            source=settings.storage_source,
        ).set(0)

        raise ontap_timeout_error(
            operation_name
        ) from exc

    except requests.RequestException as exc:
        ONTAP_REQUESTS.labels(
            operation=metric_operation,
            result="unavailable",
        ).inc()

        ONTAP_ERRORS.labels(
            operation=metric_operation,
            error_type="unavailable",
        ).inc()

        ONTAP_UP.labels(
            source=settings.storage_source,
        ).set(0)

        raise ontap_unavailable_error(
            operation_name
        ) from exc

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        ONTAP_REQUESTS.labels(
            operation=metric_operation,
            result="invalid_response",
        ).inc()

        ONTAP_ERRORS.labels(
            operation=metric_operation,
            error_type="invalid_response",
        ).inc()

        ONTAP_UP.labels(
            source=settings.storage_source,
        ).set(1)

        raise ontap_invalid_response_error(
            operation_name
        ) from exc


@router.get("/volumes")
def list_volumes():
    volumes = call_ontap(
        operation_name="volume data",
        metric_operation="volumes",
        operation=get_adapter().list_volumes,
    )

    update_volume_metrics(volumes)

    return [
        {
            **asdict(volume),
            "utilization_percent": (
                volume.utilization_percent
            ),
        }
        for volume in volumes
    ]


@router.get("/luns")
def list_luns():
    luns = call_ontap(
        operation_name="LUN data",
        metric_operation="luns",
        operation=get_adapter().list_luns,
    )

    return [
        asdict(lun)
        for lun in luns
    ]


@router.get("/snapshots")
def list_snapshots():
    snapshots = call_ontap(
        operation_name="snapshot data",
        metric_operation="snapshots",
        operation=get_adapter().list_snapshots,
    )

    return [
        asdict(snapshot)
        for snapshot in snapshots
    ]


@router.get("/capacity")
def get_capacity():
    capacity = call_ontap(
        operation_name="capacity data",
        metric_operation="capacity",
        operation=get_adapter().get_capacity,
    )

    update_capacity_metrics(capacity)

    return asdict(capacity)
