from fastapi import APIRouter

from api.config import settings
from evidence.repository import EvidenceRepository


router = APIRouter(
    prefix="/api/evidence",
    tags=["evidence"],
)


@router.get("/changes")
def list_storage_changes():
    repository = EvidenceRepository(
        evidence_dir=settings.evidence_dir
    )

    records = repository.load()

    return {
        "count": len(records),
        "changes": records,
    }
