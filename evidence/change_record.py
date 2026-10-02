from dataclasses import dataclass


@dataclass
class StorageChangeEvidence:

    event_id: str

    source: str

    collected_at: str

    resource_type: str

    change_type: str

    before_count: int

    after_count: int

    delta: int
