from adapters.ontap_adapter import OntapAdapter
from services.inventory_service import InventoryService


adapter = OntapAdapter(
    "http://localhost:8000"
)


service = InventoryService(adapter)


results = service.collect()


for item in results:
    print(item)
