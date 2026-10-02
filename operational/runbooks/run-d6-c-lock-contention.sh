#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO=/opt/netapp-storageops-lab
readonly PYTHON="$REPO/.venv/bin/python"
readonly EXPECTED_BRANCH=feature/netapp-m5-operational-automation
readonly EXPECTED_HEAD=1d1543b
readonly LOCK_FILE=/run/lock/storageops-collect.lock

test -x "$PYTHON"

RUN_ID=
RUN_DIR=
LOG_TMP=
FINAL_LOG=
HOLDER_WRAPPER_PID=
HOLDER_OWNER_PID=
FINALIZED=no

cleanup_lock_holder() {
  local pid

  pid="${HOLDER_OWNER_PID:-}"
  if test -n "$pid" && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi

  pid="${HOLDER_WRAPPER_PID:-}"
  if test -n "$pid" && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi

  if test -n "${HOLDER_WRAPPER_PID:-}"; then
    wait "$HOLDER_WRAPPER_PID" 2>/dev/null || true
  fi
}

on_exit() {
  local rc=$?
  trap - EXIT INT TERM HUP
  cleanup_lock_holder
  if test -n "${LOG_TMP:-}" && test -e "$LOG_TMP" && test "$FINALIZED" != yes; then
    printf 'FINALIZED=no\nEXIT_CODE=%s\n' "$rc" >>"$LOG_TMP"
    printf 'Controlled execution did not finalize; diagnostic transcript retained at %s\n' "$LOG_TMP" >&2
  fi
  exit "$rc"
}
trap on_exit EXIT INT TERM HUP

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

validate_latest_collect_json() {
  python3 - "$1" "$2" "$3" <<PY
import json
import pathlib
import sys

journal_path = pathlib.Path(sys.argv[1])
expected_result = sys.argv[2]
expected_exit_code = int(sys.argv[3])
collect_records = []

for line in journal_path.read_text(encoding="utf-8").splitlines():
    try:
        record = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        continue
    if isinstance(record, dict) and record.get("command") == "collect":
        collect_records.append(record)

assert collect_records, f"no collect JSON record found in {journal_path}"
latest = collect_records[-1]
assert latest.get("command") == "collect", latest
assert latest.get("result") == expected_result, latest
assert latest.get("exit_code") == expected_exit_code, latest
if expected_result == "FAIL":
    errors = latest.get("errors")
    assert isinstance(errors, list), latest
    assert any("collection lock is already held" in str(error) for error in errors), latest
PY
}

test "$(id -un)" = atn || fail 'must be executed by user atn'
test "$PWD" = "$REPO" || fail "must be executed from $REPO"
test "$(git branch --show-current)" = "$EXPECTED_BRANCH" || fail 'unexpected branch'
test "$(git rev-parse --short HEAD)" = "$EXPECTED_HEAD" || fail 'unexpected HEAD'

mapfile -t WORKTREE_STATUS < <(git status --short --untracked-files=all)
EXPECTED_STATUS=(
  ' M operational/contracts/scheduled-collection-failure-contract.md'
  ' M tests/operational/test_storageops_ops.py'
  '?? evidence/m5/m5-r3-d6-c-d1-20260805T052545Z.log'
  '?? operational/runbooks/run-d6-c-lock-contention.sh'
  '?? operational/runbooks/scheduled-collection-lock-contention.md'
)
mapfile -t ACTUAL_SORTED < <(printf '%s\n' "${WORKTREE_STATUS[@]}" | LC_ALL=C sort)
mapfile -t EXPECTED_SORTED < <(printf '%s\n' "${EXPECTED_STATUS[@]}" | LC_ALL=C sort)
test "$(printf '%s\n' "${ACTUAL_SORTED[@]}")" = "$(printf '%s\n' "${EXPECTED_SORTED[@]}")" || {
  printf 'ERROR: working tree does not match approved changes:\n' >&2
  printf '%s\n' "${WORKTREE_STATUS[@]}" >&2
  exit 1
}

if find . -path ./.git -prune -o -type f \( -name '*.orig' -o -name '*.rej' \) -print -quit | grep -q .; then
  fail '.orig or .rej file found'
fi

# This is deliberately before timer inspection, confirmation, and lock acquisition.
sudo -n true || fail 'sudo credential cache is unavailable; lock was not acquired'

RUN_ID="m5-r3-d6-c-d1-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="/tmp/$RUN_ID"
LOG_TMP="$RUN_DIR/$RUN_ID.incomplete.log"
FINAL_LOG="evidence/m5/$RUN_ID.log"
mkdir -m 700 "$RUN_DIR"
exec > >(tee -a "$LOG_TMP") 2>&1

printf 'NETAPP-M5-R3-D6-C-D1 CONTROLLED EXECUTION\n'
printf 'UTC_TIMESTAMP=%s\n' "${RUN_ID##m5-r3-d6-c-d1-}"
printf 'BRANCH=%s\nHEAD=%s\nFINAL_EVIDENCE=%s\n' "$EXPECTED_BRANCH" "$EXPECTED_HEAD" "$FINAL_LOG"
printf '%s\n' '=== PRECONDITIONS ==='
printf 'USER=%s\nPWD=%s\nWORKTREE_ALLOWLIST=PASS\nORIG_REJ_CHECK=PASS\nSUDO_NONINTERACTIVE=PASS\n' "$(id -un)" "$PWD"
git status --short --untracked-files=all

test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
test "$(systemctl is-active storageops-api.service)" = active
test "$(systemctl is-active storageops-mock-ontap.service)" = active
test "$(systemctl is-active storageops-collect.service)" = inactive
printf 'TIMER_ENABLED=enabled\nTIMER_ACTIVE=active\nAPI_ACTIVE=active\nMOCK_ONTAP_ACTIVE=active\nCOLLECT_STATE=inactive\n'

find evidence/m5/runtime -maxdepth 1 -type f -name 'collect-*.json' -printf '%f\n' | LC_ALL=C sort >"$RUN_DIR/evidence.before"
systemctl show storageops-collect.timer -p UnitFileState -p ActiveState -p NextElapseUSecMonotonic --no-pager | tee "$RUN_DIR/timer-before-lock.properties"
systemctl list-timers storageops-collect.timer --no-pager | tee "$RUN_DIR/timer-before-lock.list"
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
read -r -p 'Confirm displayed timer LEFT is at least 5 minutes (exact YES to continue): ' TIMER_WINDOW_CONFIRMED
test "$TIMER_WINDOW_CONFIRMED" = YES || fail 'timer confirmation was not exact YES; lock was not acquired'
printf 'TIMER_WINDOW_CONFIRMED=YES\n'

timeout --signal=TERM --kill-after=5s 120s python3 -u -c '
import fcntl, os, pathlib, signal, sys, time
lock = pathlib.Path(sys.argv[1])
ready = pathlib.Path(sys.argv[2])
with lock.open("a+", encoding="utf-8") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready.write_text(f"pid={os.getpid()}\n", encoding="utf-8")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(1)
' "$LOCK_FILE" "$RUN_DIR/holder.ready" &
HOLDER_WRAPPER_PID=$!
for _ in $(seq 1 50); do
  test -s "$RUN_DIR/holder.ready" && break
  kill -0 "$HOLDER_WRAPPER_PID" 2>/dev/null || break
  sleep 0.1
done
test -s "$RUN_DIR/holder.ready" || fail 'holder readiness was not confirmed; systemd execution was not attempted'
HOLDER_OWNER_PID="$(sed -n 's/^pid=//p' "$RUN_DIR/holder.ready")"
test -n "$HOLDER_OWNER_PID"
kill -0 "$HOLDER_OWNER_PID"
printf 'HOLDER_READINESS=PASS\nHOLDER_WRAPPER_PID=%s\nHOLDER_OWNER_PID=%s\n' "$HOLDER_WRAPPER_PID" "$HOLDER_OWNER_PID"

printf '%s\n' '=== CONTENTION_RESULT ==='
CONTENTION_JOURNAL_SINCE="$(date --utc --iso-8601=ns)"
set +e
sudo -n systemctl start storageops-collect.service
CONTENTION_START_RC=$?
set -e
CONTENTION_JOURNAL_UNTIL="$(date --utc --iso-8601=ns)"
test "$CONTENTION_START_RC" -ne 0
printf 'CONTENTION_START_RC=%s\n' "$CONTENTION_START_RC"
sudo -n systemctl show storageops-collect.service -p Result -p ExecMainStatus --no-pager | tee "$RUN_DIR/contention.systemd"
test "$(sudo -n systemctl show storageops-collect.service -p Result --value)" = exit-code
test "$(sudo -n systemctl show storageops-collect.service -p ExecMainStatus --value)" = 80
sudo -n journalctl -u storageops-collect.service --since "$CONTENTION_JOURNAL_SINCE" --until "$CONTENTION_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/contention.journal"
validate_latest_collect_json "$RUN_DIR/contention.journal" FAIL 80

find evidence/m5/runtime -maxdepth 1 -type f -name 'collect-*.json' -printf '%f\n' | LC_ALL=C sort >"$RUN_DIR/evidence.after"
comm -13 "$RUN_DIR/evidence.before" "$RUN_DIR/evidence.after" >"$RUN_DIR/evidence.new"
test "$(wc -l <"$RUN_DIR/evidence.new")" -ge 1
CONTENTION_EVIDENCE="$(tail -n 1 "$RUN_DIR/evidence.new")"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["result"]=="FAIL" and d["exit_code"]==80 and any("lock is already held" in e for e in d["errors"])' "evidence/m5/runtime/$CONTENTION_EVIDENCE"
printf 'CONTENTION_RESULT=exit-code\nCONTENTION_EXEC_MAIN_STATUS=80\nCONTENTION_EVIDENCE=%s\n' "$CONTENTION_EVIDENCE"
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
printf 'CONTENTION_TIMER_ENABLED=enabled\nCONTENTION_TIMER_ACTIVE=active\n'
sudo -n journalctl -u storageops-api.service --since "$CONTENTION_JOURNAL_SINCE" --until "$CONTENTION_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/api-supporting.journal"

printf '%s\n' '=== HOLDER_CLEANUP ==='
cleanup_lock_holder
test ! -e "/proc/$HOLDER_OWNER_PID"
test ! -e "/proc/$HOLDER_WRAPPER_PID"
printf 'HOLDER_OWNER_PID_GONE=PASS\nHOLDER_WRAPPER_PID_GONE=PASS\n'
HOLDER_OWNER_PID=
HOLDER_WRAPPER_PID=

printf '%s\n' '=== RECOVERY_RESULT ==='
RECOVERY_JOURNAL_SINCE="$(date --utc --iso-8601=ns)"
sudo -n systemctl start storageops-collect.service
RECOVERY_JOURNAL_UNTIL="$(date --utc --iso-8601=ns)"
sudo -n systemctl show storageops-collect.service -p Result -p ExecMainStatus --no-pager | tee "$RUN_DIR/recovery.systemd"
test "$(sudo -n systemctl show storageops-collect.service -p Result --value)" = success
test "$(sudo -n systemctl show storageops-collect.service -p ExecMainStatus --value)" = 0
sudo -n journalctl -u storageops-collect.service --since "$RECOVERY_JOURNAL_SINCE" --until "$RECOVERY_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/recovery.journal"
validate_latest_collect_json "$RUN_DIR/recovery.journal" PASS 0
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
printf 'RECOVERY_RESULT=success\nRECOVERY_EXEC_MAIN_STATUS=0\nRECOVERY_TIMER_ENABLED=enabled\nRECOVERY_TIMER_ACTIVE=active\n'

printf '%s\n' '=== FINAL_VERIFICATION ==='
python3 -m py_compile scripts/storageops-ops tests/operational/test_storageops_ops.py
"$PYTHON" -m pytest -q tests/operational/test_storageops_ops.py -k 'lock_contention or acquire_and_release_collect_lock or external_holder'
"$PYTHON" -m pytest -q
git diff --check
scripts/storageops-ops verify | tee "$RUN_DIR/verify.log"
grep -Fx 'RESULT=PASS' "$RUN_DIR/verify.log"
grep -Fx 'EXIT_CODE=0' "$RUN_DIR/verify.log"
printf '%s\n' '=== FINAL_GIT_STATUS ==='
git status --short --untracked-files=all
printf 'FINALIZED=yes\nEXIT_CODE=0\n'
cp -- "$LOG_TMP" "$FINAL_LOG"
FINALIZED=yes
printf 'FINAL_EVIDENCE_WRITTEN=%s\n' "$FINAL_LOG"
