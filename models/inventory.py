from dataclasses import dataclass
from datetime import datetime


@dataclass
class InventorySnapshot:

    id: str

    collected_at: str

    resource_type: str

    resource_count: int
