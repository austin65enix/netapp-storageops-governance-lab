import requests

from models.storage import (
    StorageCapacity,
    StorageLUN,
    StorageSnapshot,
    StorageVolume,
)


class OntapAdapter:

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get_json(
        self,
        endpoint: str,
    ):
        response = requests.get(
            f"{self.base_url}{endpoint}",
            timeout=self.timeout_seconds,
        )

        response.raise_for_status()

        return response.json()

    def list_volumes(self) -> list[StorageVolume]:
        records = self._get_json(
            "/api/storage/volumes"
        )

        return [
            StorageVolume(
                id=item["uuid"],
                name=item["name"],
                svm_id=item["svm_uuid"],
                protocol=item["protocol"],
                state=item["state"],
                size_bytes=item["size_bytes"],
                used_bytes=item["used_bytes"],
                available_bytes=item["available_bytes"],
            )
            for item in records
        ]

    def list_luns(self) -> list[StorageLUN]:
        records = self._get_json(
            "/api/storage/luns"
        )

        return [
            StorageLUN(
                id=item["uuid"],
                name=item["name"],
                volume_id=item["volume_uuid"],
                size_bytes=item["size_bytes"],
                os_type=item["os_type"],
                state=item["state"],
            )
            for item in records
        ]

    def list_snapshots(
        self,
    ) -> list[StorageSnapshot]:
        records = self._get_json(
            "/api/storage/snapshots"
        )

        return [
            StorageSnapshot(
                id=item["uuid"],
                name=item["name"],
                volume_id=item["volume_uuid"],
                created_time=item["created_time"],
                size_bytes=item["size_bytes"],
            )
            for item in records
        ]

    def get_capacity(self) -> StorageCapacity:
        item = self._get_json(
            "/api/storage/capacity"
        )

        return StorageCapacity(
            total_bytes=item["total_bytes"],
            used_bytes=item["used_bytes"],
            available_bytes=item["available_bytes"],
            utilization_percent=(
                item["utilization_percent"]
            ),
        )
