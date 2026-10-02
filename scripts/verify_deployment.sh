#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/opt/netapp-storageops-lab"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
MOCK_SERVICE="storageops-mock-ontap"
API_SERVICE="storageops-api"
MOCK_URL="http://127.0.0.1:8000"
API_URL="http://127.0.0.1:8100"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="${PROJECT_DIR}/evidence/m3/deployment"
EVIDENCE_FILE="${EVIDENCE_DIR}/deployment-verification-${TIMESTAMP}.log"

mkdir -p "$EVIDENCE_DIR"
cd "$PROJECT_DIR"

exec > >(tee "$EVIDENCE_FILE") 2>&1

restore_runtime() {
    sudo systemctl start "$MOCK_SERVICE" >/dev/null 2>&1 || true
    sudo systemctl start "$API_SERVICE" >/dev/null 2>&1 || true
}

trap restore_runtime EXIT

wait_for_http() {
    local url="$1"
    local attempts="${2:-20}"

    for ((attempt=1; attempt<=attempts; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done

    echo "HTTP_WAIT_TIMEOUT=$url"
    return 1
}

assert_active() {
    local service="$1"
    test "$(systemctl is-active "$service")" = "active"
    echo "${service}_ACTIVE=PASS"
}

assert_enabled() {
    local service="$1"
    test "$(systemctl is-enabled "$service")" = "enabled"
    echo "${service}_ENABLED=PASS"
}

echo "========================================"
echo "NETAPP-M3-R5 Deployment Verification"
echo "UTC_TIMESTAMP=$TIMESTAMP"
echo "HOSTNAME=$(hostname)"
echo "========================================"

echo
echo "=== 1. ENVIRONMENT ==="

test -r /etc/storageops/storageops.env
echo "ENV_FILE_READABLE=PASS"

stat -c \
  'ENV_OWNER=%U ENV_GROUP=%G ENV_MODE=%a ENV_FILE=%n' \
  /etc/storageops/storageops.env

./scripts/verify_environment.sh

echo
echo "=== 2. SYSTEMD UNITS ==="

sudo systemd-analyze verify \
  /etc/systemd/system/storageops-mock-ontap.service \
  /etc/systemd/system/storageops-api.service

echo "SYSTEMD_UNIT_VERIFY=PASS"

grep -q '^Wants=storageops-mock-ontap.service$' \
  /etc/systemd/system/storageops-api.service

if grep -q '^Requires=storageops-mock-ontap.service$' \
  /etc/systemd/system/storageops-api.service; then
    echo "API_STRONG_DEPENDENCY=FAIL"
    exit 1
fi

echo "API_LIFECYCLE_DECOUPLING=PASS"

echo
echo "=== 3. SERVICE STARTUP ==="

sudo systemctl start "$MOCK_SERVICE"
sudo systemctl start "$API_SERVICE"

wait_for_http "${MOCK_URL}/api/storage/volumes"
wait_for_http "${API_URL}/healthz"

assert_active "$MOCK_SERVICE"
assert_active "$API_SERVICE"
assert_enabled "$MOCK_SERVICE"
assert_enabled "$API_SERVICE"

echo
echo "=== 4. PORTS AND HEALTH ==="

sudo ss -tlnp | grep -E ':8000|:8100'

sudo ss -tln | grep -q ':8000 '
echo "PORT_8000_LISTENING=PASS"

sudo ss -tln | grep -q ':8100 '
echo "PORT_8100_LISTENING=PASS"

HEALTH_JSON="$(curl -fsS "${API_URL}/healthz")"
echo "$HEALTH_JSON"

HEALTH_JSON="$HEALTH_JSON" "$PYTHON_BIN" - <<'PY'
import json
import os

payload = json.loads(os.environ["HEALTH_JSON"])

assert payload["status"] == "ok"
assert payload["source"] == "ONTAP-LAB-01"
assert payload["ontap_base_url"] == "http://127.0.0.1:8000"
assert float(payload["ontap_timeout_seconds"]) > 0

print("HEALTH_CONTRACT=PASS")
PY

echo
echo "=== 5. OPENAPI CONTRACT ==="

OPENAPI_FILE="$(mktemp)"
curl -fsS "${API_URL}/openapi.json" > "$OPENAPI_FILE"

OPENAPI_FILE="$OPENAPI_FILE" "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

document = json.loads(
    Path(os.environ["OPENAPI_FILE"]).read_text()
)

paths = document.get("paths", {})

assert "/healthz" in paths
assert "/api/storage/volumes" in paths

print(f"OPENAPI_TITLE={document.get('info', {}).get('title', '')}")
print(f"OPENAPI_VERSION={document.get('info', {}).get('version', '')}")
print(f"OPENAPI_PATH_COUNT={len(paths)}")
print("OPENAPI_CONTRACT=PASS")
PY

rm -f "$OPENAPI_FILE"

echo
echo "=== 6. PROCESS FAILURE RECOVERY ==="

OLD_PID="$(
  systemctl show "$API_SERVICE" \
    --property=MainPID \
    --value
)"

echo "API_OLD_PID=$OLD_PID"

test -n "$OLD_PID"
test "$OLD_PID" != "0"

sudo kill -TERM "$OLD_PID"

NEW_PID=""

for _ in $(seq 1 20); do
    NEW_PID="$(
      systemctl show "$API_SERVICE" \
        --property=MainPID \
        --value
    )"

    if test -n "$NEW_PID" &&
       test "$NEW_PID" != "0" &&
       test "$NEW_PID" != "$OLD_PID" &&
       test "$(systemctl is-active "$API_SERVICE")" = "active"; then
        break
    fi

    sleep 1
done

echo "API_NEW_PID=$NEW_PID"

test "$NEW_PID" != "0"
test "$NEW_PID" != "$OLD_PID"

wait_for_http "${API_URL}/healthz"

echo "API_PID_REPLACEMENT=PASS"
echo "API_PROCESS_RECOVERY=PASS"

echo
echo "=== 7. DEPENDENCY FAILURE MODE ==="

sudo systemctl stop "$MOCK_SERVICE"
sleep 2

MOCK_STATUS="$(systemctl is-active "$MOCK_SERVICE" || true)"
API_STATUS="$(systemctl is-active "$API_SERVICE" || true)"

echo "MOCK_STATUS_DURING_FAILURE=$MOCK_STATUS"
echo "API_STATUS_DURING_FAILURE=$API_STATUS"

test "$MOCK_STATUS" = "inactive"
test "$API_STATUS" = "active"

curl -fsS "${API_URL}/healthz" >/dev/null
echo "API_HEALTH_DURING_DEPENDENCY_FAILURE=PASS"

RESPONSE_FILE="$(mktemp)"

HTTP_STATUS="$(
  curl -sS \
    -o "$RESPONSE_FILE" \
    -w '%{http_code}' \
    "${API_URL}/api/storage/volumes"
)"

cat "$RESPONSE_FILE"
echo
echo "DEPENDENCY_FAILURE_HTTP_STATUS=$HTTP_STATUS"

test "$HTTP_STATUS" = "502"

RESPONSE_FILE="$RESPONSE_FILE" "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

payload = json.loads(
    Path(os.environ["RESPONSE_FILE"]).read_text()
)

error = payload["error"]

assert error["code"] == "ONTAP_UNAVAILABLE"
assert error["path"] == "/api/storage/volumes"

print("DEPENDENCY_ERROR_CONTRACT=PASS")
PY

rm -f "$RESPONSE_FILE"

echo "API_SURVIVAL_DURING_DEPENDENCY_FAILURE=PASS"
echo "DEPENDENCY_DEGRADED_MODE=PASS"

echo
echo "=== 8. DEPENDENCY RECOVERY ==="

sudo systemctl start "$MOCK_SERVICE"

wait_for_http "${MOCK_URL}/api/storage/volumes"
wait_for_http "${API_URL}/api/storage/volumes"

assert_active "$MOCK_SERVICE"
assert_active "$API_SERVICE"

echo "MOCK_ONTAP_RECOVERY=PASS"
echo "DEPENDENCY_RECOVERY=PASS"

echo
echo "=== 9. M2 REGRESSION ==="

./scripts/verify_m2.sh

echo "M2_REGRESSION=PASS"

echo
echo "=== 10. FINAL STATUS ==="

systemctl status "$MOCK_SERVICE" \
  --no-pager \
  --lines=5

systemctl status "$API_SERVICE" \
  --no-pager \
  --lines=5

echo
echo "=== 11. RECENT JOURNAL ==="

journalctl \
  -u "$MOCK_SERVICE" \
  -u "$API_SERVICE" \
  --since "10 minutes ago" \
  --no-pager

echo
echo "========================================"
echo "NETAPP_M3_R5_DEPLOYMENT_VERIFICATION=PASS"
echo "EVIDENCE_FILE=$EVIDENCE_FILE"
echo "========================================"
