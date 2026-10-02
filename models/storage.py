from dataclasses import dataclass


@dataclass
class StorageCluster:
    id: str
    name: str
    version: str
    state: str
    location: str


@dataclass
class StorageSVM:
    id: str
    name: str
    state: str
    protocols: list[str]


@dataclass
class StorageVolume:
    id: str
    name: str
    svm_id: str
    protocol: str
    state: str
    size_bytes: int
    used_bytes: int
    available_bytes: int

    @property
    def utilization_percent(self) -> float:
        if self.size_bytes == 0:
            return 0

        return round(
            self.used_bytes / self.size_bytes * 100,
            2
        )


@dataclass
class StorageLUN:
    id: str
    name: str
    volume_id: str
    size_bytes: int
    os_type: str
    state: str


@dataclass
class StorageSnapshot:
    id: str
    name: str
    volume_id: str
    created_time: str
    size_bytes: int


@dataclass
class StorageCapacity:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    utilization_percent: float
