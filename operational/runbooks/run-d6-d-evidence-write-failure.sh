#!/usr/bin/env bash
set -Eeuo pipefail
readonly REPO=/opt/netapp-storageops-lab
PYTHON="$REPO/.venv/bin/python"
readonly BRANCH=feature/netapp-m5-operational-automation
readonly HEAD=012c8aa
readonly SERVICE=storageops-collect.service
readonly DROPIN_DIR=/run/systemd/system/storageops-collect.service.d
readonly DROPIN=$DROPIN_DIR/90-evidence-write-failure.conf
RUN_ID= RUN_DIR= FAILURE_DIR= ORIGINAL_EXEC= DROPIN_INSTALLED=no FINALIZED=no LOG_TMP=

fail() { printf 'ERROR: %s\n' "$*" >&2; return 1; }
cleanup() {
  local current rc=0
  if test "$DROPIN_INSTALLED" = yes; then
    sudo -n rm -f -- "$DROPIN"
    sudo -n rmdir --ignore-fail-on-non-empty "$DROPIN_DIR"
    sudo -n systemctl daemon-reload
    DROPIN_INSTALLED=no
  fi
  if test -n "$ORIGINAL_EXEC"; then
    current="$(systemctl show "$SERVICE" -p ExecStart --value)"
    test "$current" = "$ORIGINAL_EXEC" || rc=1
  fi
  if test -n "$FAILURE_DIR" && test -d "$FAILURE_DIR"; then
    case "$FAILURE_DIR" in
      /run/storageops-evidence-write-failure-*) sudo -n rmdir -- "$FAILURE_DIR" ;;
      *) fail "unsafe cleanup target: $FAILURE_DIR" ;;
    esac
  fi
  if test "$(systemctl is-failed "$SERVICE" 2>/dev/null || true)" = failed; then
    sudo -n systemctl reset-failed "$SERVICE"
  fi
  return "$rc"
}
on_exit() {
  local rc=$?
  trap - EXIT INT TERM HUP
  cleanup || rc=1
  if test -n "$LOG_TMP" && test -e "$LOG_TMP" && test "$FINALIZED" != yes; then
    printf 'FINALIZED=no\nEXIT_CODE=%s\n' "$rc" >>"$LOG_TMP"
  fi
  exit "$rc"
}
trap on_exit EXIT INT TERM HUP

utc_journal_timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
validate_journal_timestamp() {
  [[ $1 =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || fail "invalid journal timestamp: $1"
  test "$(date -u -d "$1" +%Y-%m-%dT%H:%M:%SZ)" = "$1" || fail "invalid journal timestamp: $1"
}
timer_seconds_left() {
  local timer_line=$1 now_epoch=$2 next_weekday next_date next_time next_zone remainder next_epoch
  read -r next_weekday next_date next_time next_zone remainder <<<"$timer_line"
  test -n "$remainder" || fail 'unable to parse timer NEXT timestamp'
  next_epoch="$(date -d "$next_weekday $next_date $next_time $next_zone" +%s)" || fail 'unable to convert timer NEXT timestamp'
  printf '%s\n' "$((next_epoch - now_epoch))"
}
assert_timer_window() {
  local seconds_left=$1
  [[ $seconds_left =~ ^-?[0-9]+$ ]] || fail 'non-numeric TIMER_SECONDS_LEFT'
  test "$seconds_left" -ge 300 || fail "timer safety window below 300 seconds: $seconds_left"
}
run_helper_tests() {
  local sample_now=1786000000 seconds_left
  validate_journal_timestamp '2026-08-05T07:40:06Z'
  ! validate_journal_timestamp '2026-08-05T07:40:06,309449529+00:00' 2>/dev/null
  ! assert_timer_window 299 2>/dev/null
  assert_timer_window 300
  assert_timer_window 301
  seconds_left="$(timer_seconds_left "$(date -u -d "@$((sample_now + 300))" '+%a %Y-%m-%d %H:%M:%S UTC') 1h left" "$sample_now")"
  test "$seconds_left" -eq 300
}
validate_json() {
"$PYTHON" - "$1" "$2" "$3" "$4" <<'PY'
import json, pathlib, sys
records = []
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    try: item = json.loads(line)
    except (json.JSONDecodeError, TypeError): continue
    if isinstance(item, dict) and item.get("command") == "collect": records.append(item)
assert records
latest = records[-1]
assert latest.get("result") == sys.argv[2], latest
assert latest.get("exit_code") == int(sys.argv[3]), latest
if sys.argv[4]:
    assert any(sys.argv[4] in str(e) for e in latest.get("errors", [])), latest
PY
}

if test "${1-}" = --self-test; then
  run_helper_tests
  printf 'HELPER_TESTS=PASS\n'
  exit 0
fi

printf '%s\n' '=== PREFLIGHT ==='
test "$(id -un)" = atn
test "$PWD" = "$REPO"
test -x "$PYTHON"
"$PYTHON" -c 'import pytest'
test "$(git branch --show-current)" = "$BRANCH"
test "$(git rev-parse --short HEAD)" = "$HEAD"
mapfile -t status < <(git status --short --untracked-files=all)
expected=(' M operational/contracts/scheduled-collection-failure-contract.md' ' M tests/operational/test_storageops_ops.py' '?? operational/runbooks/run-d6-d-evidence-write-failure.sh' '?? operational/runbooks/scheduled-collection-evidence-write-failure.md')
test "$(printf '%s\n' "${status[@]}" | sort)" = "$(printf '%s\n' "${expected[@]}" | sort)"
! find . -path ./.git -prune -o -type f \( -name '*.orig' -o -name '*.rej' \) -print -quit | grep -q .
sudo -n true
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
test "$(systemctl is-active storageops-api.service)" = active
test "$(systemctl is-active storageops-mock-ontap.service)" = active
test "$(systemctl is-active "$SERVICE")" = inactive
systemctl list-timers storageops-collect.timer --no-pager
printf '%s\n' '=== IMPLEMENTATION_REVIEW ==='
run_helper_tests
"$PYTHON" -m py_compile scripts/storageops-ops tests/operational/test_storageops_ops.py
bash -n operational/runbooks/run-d6-d-evidence-write-failure.sh
"$PYTHON" -m pytest -q tests/operational/test_storageops_ops.py -k evidence_write_failure
"$PYTHON" -m pytest -q
git diff --check
git diff --no-index --check -- /dev/null operational/runbooks/run-d6-d-evidence-write-failure.sh || test "$?" = 1
git diff --no-index --check -- /dev/null operational/runbooks/scheduled-collection-evidence-write-failure.md || test "$?" = 1
verify_output="$(scripts/storageops-ops verify)"
printf '%s\n' "$verify_output"
grep -Fx 'RESULT=PASS' <<<"$verify_output"
grep -Fx 'EXIT_CODE=0' <<<"$verify_output"
printf 'CONTROL_FLOW_AND_FOCUSED_TEST_DESIGN=REVIEWED\n'
printf '%s\n' '=== FAILURE_INJECTION_DESIGN_REVIEW ==='
printf 'ISOLATED_RUN_TARGET_AND_TRANSIENT_OVERRIDE=REVIEWED\n'
printf '%s\n' '=== READY_FOR_OPERATOR_EXECUTION ==='
timer_line="$(systemctl list-timers storageops-collect.timer --all --no-legend --no-pager)"
test "$(printf '%s\n' "$timer_line" | wc -l)" -eq 1
current_epoch="$(date +%s)"
TIMER_SECONDS_LEFT="$(timer_seconds_left "$timer_line" "$current_epoch")"
printf 'TIMER_SECONDS_LEFT=%s\n' "$TIMER_SECONDS_LEFT"
assert_timer_window "$TIMER_SECONDS_LEFT"
read -r -p 'Exact YES only when LEFT >= 5 minutes: ' answer
test "$answer" = YES

RUN_ID="m5-r3-d6-d-d1-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="/tmp/$RUN_ID"
FAILURE_DIR="/run/storageops-evidence-write-failure-$RUN_ID"
LOG_TMP="$RUN_DIR/$RUN_ID.incomplete.log"
FINAL_LOG="evidence/m5/$RUN_ID.log"
mkdir -m 700 "$RUN_DIR"
exec > >(tee -a "$LOG_TMP") 2>&1

printf '%s\n' '=== FAILURE_INJECTION_DESIGN_REVIEW ==='
ORIGINAL_EXEC="$(systemctl show "$SERVICE" -p ExecStart --value)"
test -n "$ORIGINAL_EXEC"
find evidence/m5/runtime -maxdepth 1 -type f -exec sha256sum {} + | sort >"$RUN_DIR/runtime.before"
sudo -n install -d -o root -g root -m 0500 "$FAILURE_DIR"
test ! -w "$FAILURE_DIR"
sudo -n install -d -o root -g root -m 0755 "$DROPIN_DIR"
printf '[Service]\nExecStart=\nExecStart=%s --format json --timeout 30 --evidence-dir %s --lock-file /run/lock/storageops-collect.lock collect\n' "$REPO/scripts/storageops-ops" "$FAILURE_DIR" | sudo -n tee "$DROPIN" >/dev/null
DROPIN_INSTALLED=yes
sudo -n systemctl daemon-reload
case "$(systemctl show "$SERVICE" -p ExecStart --value)" in *"--evidence-dir $FAILURE_DIR"*) ;; *) fail 'override not effective' ;; esac

printf '%s\n' '=== EXECUTION_RESULT ==='
since="$(utc_journal_timestamp)"; validate_journal_timestamp "$since"
set +e
sudo -n systemctl start "$SERVICE"
start_rc=$?
set -e
until="$(date -u -d '+1 second' +%Y-%m-%dT%H:%M:%SZ)"; validate_journal_timestamp "$until"
test "$start_rc" -ne 0
test "$(systemctl show "$SERVICE" -p Result --value)" = exit-code
test "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" = 70
sudo -n journalctl -u "$SERVICE" --since "$since" --until "$until" -o cat --no-pager | tee "$RUN_DIR/failure.journal"
validate_json "$RUN_DIR/failure.journal" FAIL 70 'evidence write failed:'
test "$(systemctl is-active storageops-api.service)" = active
test "$(systemctl is-active storageops-mock-ontap.service)" = active
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
find evidence/m5/runtime -maxdepth 1 -type f -exec sha256sum {} + | sort >"$RUN_DIR/runtime.after"
cmp "$RUN_DIR/runtime.before" "$RUN_DIR/runtime.after"

cleanup
printf 'ORIGINAL_EXECSTART_RESTORED=PASS\n'
printf '%s\n' '=== RECOVERY_RESULT ==='
since="$(utc_journal_timestamp)"; validate_journal_timestamp "$since"
sudo -n systemctl start "$SERVICE"
until="$(date -u -d '+1 second' +%Y-%m-%dT%H:%M:%SZ)"; validate_journal_timestamp "$until"
test "$(systemctl show "$SERVICE" -p Result --value)" = success
test "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" = 0
sudo -n journalctl -u "$SERVICE" --since "$since" --until "$until" -o cat --no-pager | tee "$RUN_DIR/recovery.journal"
validate_json "$RUN_DIR/recovery.journal" PASS 0 ''
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active

printf '%s\n' '=== FINAL_VERIFICATION ==='
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
test "$(systemctl show "$SERVICE" -p ExecStart --value)" = "$ORIGINAL_EXEC"
git status --short --untracked-files=all
printf 'FINALIZED=yes\nEXIT_CODE=0\n'
cp -- "$LOG_TMP" "$FINAL_LOG"
FINALIZED=yes
