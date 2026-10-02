#!/usr/bin/env bash

set -Eeuo pipefail

ENV_FILE="/etc/storageops/storageops.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ENV_FILE_MISSING=$ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

required_vars=(
    ONTAP_BASE_URL
    ONTAP_TIMEOUT_SECONDS
    STORAGE_SOURCE
    SNAPSHOT_DIR
    EVIDENCE_DIR
)

for var in "${required_vars[@]}"
do
    if [ -z "${!var:-}" ]; then
        echo "${var}=MISSING"
        exit 1
    fi

    echo "${var}=PASS"
done


python - <<'PY'
from api.config import settings

assert settings.ontap_base_url
assert settings.ontap_timeout_seconds > 0
assert settings.storage_source

print("CONFIG_VALIDATION=PASS")
PY
