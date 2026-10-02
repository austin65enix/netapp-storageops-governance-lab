from adapters.ontap_adapter import OntapAdapter
from inventory.repository import InventorySnapshotRepository
from services.inventory_service import InventoryService


adapter = OntapAdapter(
    "http://localhost:8000"
)

service = InventoryService(adapter)

repository = InventorySnapshotRepository(
    "snapshots/runs"
)


snapshots = service.collect()

saved_path = repository.save(
    snapshots
)

print(
    "SAVED:",
    saved_path
)


latest = repository.load_latest()

print(
    "LATEST:",
    latest
)
