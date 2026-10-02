import os
from dataclasses import dataclass


def read_positive_float(
    variable_name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        variable_name,
        str(default),
    )

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"{variable_name} must be a number."
        ) from exc

    if value <= 0:
        raise ValueError(
            f"{variable_name} must be greater than zero."
        )

    return value


@dataclass(frozen=True)
class Settings:
    ontap_base_url: str
    ontap_timeout_seconds: float
    storage_source: str
    snapshot_dir: str
    evidence_dir: str


def load_settings() -> Settings:
    return Settings(
        ontap_base_url=os.getenv(
            "ONTAP_BASE_URL",
            "http://localhost:8000",
        ).rstrip("/"),
        ontap_timeout_seconds=read_positive_float(
            "ONTAP_TIMEOUT_SECONDS",
            5.0,
        ),
        storage_source=os.getenv(
            "STORAGE_SOURCE",
            "ONTAP-LAB-01",
        ),
        snapshot_dir=os.getenv(
            "SNAPSHOT_DIR",
            "snapshots/runs",
        ),
        evidence_dir=os.getenv(
            "EVIDENCE_DIR",
            "evidence/events",
        ),
    )


settings = load_settings()
