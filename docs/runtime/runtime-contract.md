# StorageOps Runtime Contract

## Runtime identity

- Project: Enyrax StorageOps Lab
- Project directory: `/opt/netapp-storageops-lab`
- Runtime user: `atn`
- Python environment: `/opt/netapp-storageops-lab/.venv`
- Operating system: Ubuntu 24.04

## Services

| Service | Port | Purpose |
|---|---:|---|
| Mock ONTAP API | 8000 | Simulated vendor REST API |
| StorageOps API | 8100 | Normalized inventory and evidence API |

## Required environment

- `ONTAP_BASE_URL`
- `ONTAP_TIMEOUT_SECONDS`
- `STORAGE_SOURCE`
- `SNAPSHOT_DIR`
- `EVIDENCE_DIR`

## Required startup order

1. Mock ONTAP API
2. StorageOps API
3. Health and integration verification

## Health checks

- `GET http://127.0.0.1:8000/api/storage/volumes`
- `GET http://127.0.0.1:8100/healthz`
- `GET http://127.0.0.1:8100/api/storage/volumes`

## Baseline verification

Run:

    cd /opt/netapp-storageops-lab
    ./scripts/verify_m2.sh

Expected terminal marker:

    NETAPP_M2_R5=PASS


## Environment Configuration

Runtime configuration location:

/etc/storageops/storageops.env

Ownership:

root:root

Permission:

640

Required variables:

- ONTAP_BASE_URL
- ONTAP_TIMEOUT_SECONDS
- STORAGE_SOURCE
- SNAPSHOT_DIR
- EVIDENCE_DIR
