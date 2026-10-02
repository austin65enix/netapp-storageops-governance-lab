import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from models.inventory import InventorySnapshot


class InventorySnapshotRepository:

    def __init__(self, snapshot_dir: str = "snapshots/runs"):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def save(
        self,
        snapshots: list[InventorySnapshot]
    ) -> Path:

        if not snapshots:
            raise ValueError(
                "Cannot save an empty inventory snapshot list."
            )

        collected_at = snapshots[0].collected_at

        timestamp = datetime.fromisoformat(
            collected_at
        ).strftime("%Y%m%d_%H%M%S_%f")

        output_path = (
            self.snapshot_dir
            / f"inventory_{timestamp}.json"
        )

        payload = {
            "collected_at": collected_at,
            "resources": {
                item.resource_type: {
                    "snapshot_id": item.id,
                    "resource_count": item.resource_count
                }
                for item in snapshots
            }
        }

        output_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        return output_path

    def list_snapshot_files(self) -> list[Path]:
        return sorted(
            self.snapshot_dir.glob("inventory_*.json")
        )

    def load_latest(self) -> dict | None:
        files = self.list_snapshot_files()

        if not files:
            return None

        latest_file = files[-1]

        return json.loads(
            latest_file.read_text(
                encoding="utf-8"
            )
        )
