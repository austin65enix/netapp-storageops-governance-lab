from datetime import datetime, timezone
from uuid import uuid4

from adapters.ontap_adapter import OntapAdapter
from models.inventory import InventorySnapshot


class InventoryService:

    def __init__(
        self,
        adapter: OntapAdapter,
    ):
        self.adapter = adapter

    def collect(
        self,
    ) -> list[InventorySnapshot]:
        volumes = self.adapter.list_volumes()
        luns = self.adapter.list_luns()
        snapshots = self.adapter.list_snapshots()

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        return [
            InventorySnapshot(
                id=str(uuid4()),
                collected_at=collected_at,
                resource_type="volume",
                resource_count=len(volumes),
            ),
            InventorySnapshot(
                id=str(uuid4()),
                collected_at=collected_at,
                resource_type="lun",
                resource_count=len(luns),
            ),
            InventorySnapshot(
                id=str(uuid4()),
                collected_at=collected_at,
                resource_type="snapshot",
                resource_count=len(snapshots),
            ),
        ]
