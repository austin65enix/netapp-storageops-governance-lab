from evidence.change_record import (
    StorageChangeEvidence
)

from evidence.repository import (
    EvidenceRepository
)


records = [

    StorageChangeEvidence(
        event_id="evt-001",
        source="ONTAP-LAB-01",
        collected_at="2026-07-30T13:30:00+08:00",
        resource_type="volume",
        change_type="ADDED",
        before_count=3,
        after_count=4,
        delta=1
    ),

    StorageChangeEvidence(
        event_id="evt-002",
        source="ONTAP-LAB-01",
        collected_at="2026-07-30T13:30:00+08:00",
        resource_type="snapshot",
        change_type="REMOVED",
        before_count=3,
        after_count=2,
        delta=-1
    )
]


repo = EvidenceRepository()

path = repo.save(records)

print(
    "SAVED:",
    path
)


print(
    repo.load()
)
