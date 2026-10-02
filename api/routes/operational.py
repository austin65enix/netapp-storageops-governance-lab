from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from models.operational_summary import ScheduledCollectionOperationalSummary
from services.scheduled_collection_operational_summary_service import (
    read_scheduled_collection_operational_summary,
)


router = APIRouter(
    prefix="/api/operational",
    tags=["operational"],
)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    normalized = value.astimezone(timezone.utc)

    return normalized.isoformat().replace("+00:00", "Z")


def _serialize_summary(
    summary: ScheduledCollectionOperationalSummary,
) -> dict[str, object]:
    payload = asdict(summary)

    for key, value in payload.items():
        if isinstance(value, datetime):
            payload[key] = _serialize_datetime(value)

    payload["collection_health"] = summary.collection_health.value

    return payload


@router.get("/collection-summary")
def collection_summary():
    timestamp = _serialize_datetime(datetime.now(timezone.utc))

    try:
        summary = read_scheduled_collection_operational_summary()
        data = _serialize_summary(summary)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "command": "collection-summary",
                "contract_version": "1",
                "timestamp": timestamp,
                "result": "FAIL",
                "exit_code": 100,
                "data": {},
                "errors": [
                    "operational summary inspection failed"
                ],
                "evidence_file": None,
            },
        )

    return {
        "command": "collection-summary",
        "contract_version": "1",
        "timestamp": timestamp,
        "result": "PASS",
        "exit_code": 0,
        "data": data,
        "errors": [],
        "evidence_file": None,
    }
