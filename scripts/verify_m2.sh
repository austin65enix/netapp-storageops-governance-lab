#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$HOME/storageops-lab"

cd "$PROJECT_DIR"

source .venv/bin/activate

printf '%s\n' \
  '=== COMPILE CHECK ==='

python -m compileall -q \
  api \
  adapters \
  models \
  inventory \
  evidence \
  diff_engine \
  services \
  tests

printf '%s\n' \
  'COMPILE_CHECK=PASS'

printf '%s\n' \
  '=== PYTEST BASELINE ==='

pytest -q

printf '%s\n' \
  'M2_INTEGRATION_TEST_BASELINE=PASS'

printf '%s\n' \
  '=== OPENAPI BASELINE ==='

python - <<'PY'
from api.main import app

expected = {
    "/api/storage/volumes",
    "/api/storage/luns",
    "/api/storage/snapshots",
    "/api/storage/capacity",
    "/api/inventory/latest",
    "/api/inventory/runs",
    "/api/inventory/collect",
    "/api/evidence/changes",
}

actual = set(
    app.openapi().get("paths", {})
)

missing = sorted(
    expected - actual
)

print(
    f"APP_VERSION={app.version}"
)
print(
    f"MISSING_ROUTES={missing}"
)

assert not missing

print(
    "OPENAPI_BASELINE=PASS"
)
PY

printf '%s\n' \
  'NETAPP_M2_R5=PASS'
