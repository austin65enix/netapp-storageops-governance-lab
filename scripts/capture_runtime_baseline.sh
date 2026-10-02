#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/storageops-lab}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$PROJECT_DIR/evidence/m3}"

cd "$PROJECT_DIR"

source .venv/bin/activate

mkdir -p "$EVIDENCE_DIR"

TIMESTAMP="$(
  date -u '+%Y%m%dT%H%M%SZ'
)"

OUTPUT_FILE="$EVIDENCE_DIR/runtime-baseline-${TIMESTAMP}.log"

{
  printf '%s\n' \
    '========================================' \
    'NETAPP-M3-R1 RUNTIME BASELINE' \
    '========================================'

  printf 'CAPTURED_AT_UTC=%s\n' \
    "$(date -u --iso-8601=seconds)"

  printf 'HOSTNAME=%s\n' \
    "$(hostname)"

  printf 'RUN_AS_USER=%s\n' \
    "$(id -un)"

  printf 'PROJECT_DIR=%s\n' \
    "$PROJECT_DIR"

  printf 'PYTHON_EXECUTABLE=%s\n' \
    "$(command -v python)"

  printf 'PYTHON_VERSION=%s\n' \
    "$(python --version 2>&1)"

  printf 'PIP_VERSION=%s\n' \
    "$(python -m pip --version)"

  printf '%s\n' \
    '--- OS RELEASE ---'

  cat /etc/os-release

  printf '%s\n' \
    '--- KEY PACKAGES ---'

  python -m pip freeze |
    grep -Ei \
      '^(fastapi|uvicorn|requests|pytest|httpx|starlette|pydantic|anyio)=='

  printf '%s\n' \
    '--- LISTENING PORTS ---'

  ss -tlnp |
    grep -E ':8000|:8100' ||
    true

  printf '%s\n' \
    '--- PROJECT PATHS ---'

  for required_path in \
    api/main.py \
    api/config.py \
    api/errors.py \
    adapters/ontap_adapter.py \
    services/inventory_service.py \
    scripts/verify_m2.sh \
    requirements.txt \
    requirements.lock.txt
  do
    if test -e "$required_path"; then
      printf 'PATH_CHECK=%s:PASS\n' \
        "$required_path"
    else
      printf 'PATH_CHECK=%s:FAIL\n' \
        "$required_path"
    fi
  done

  printf '%s\n' \
    '--- M2 VERIFICATION ---'

  ./scripts/verify_m2.sh

  printf '%s\n' \
    'RUNTIME_BASELINE=PASS'
} | tee "$OUTPUT_FILE"

printf 'EVIDENCE_FILE=%s\n' \
  "$OUTPUT_FILE"
