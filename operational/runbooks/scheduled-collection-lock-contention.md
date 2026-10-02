# Scheduled Collection Lock Contention Validation

## Purpose and safety

Failure-injection runbook for `NETAPP-M5-R3-D6-C-D1`. It validates exit-code
preservation, absence of an inventory HTTP request, timer continuity, evidence,
and recovery. Never stop `storageops-api.service` or
`storageops-mock-ontap.service`; never stop/disable the timer; never change
installed units, reboot, mutate ONTAP resources, or delete runtime evidence.

Inputs: explicit operator authorization; user `atn`; working directory
`/opt/netapp-storageops-lab`; a 120-second holder timeout; active API and Mock
ONTAP services; and an enabled, active `storageops-collect.timer` whose next
trigger is at least five minutes away.

## PREFLIGHT

Run without sudo:

```bash
cd /opt/netapp-storageops-lab
test "$(git branch --show-current)" = feature/netapp-m5-operational-automation
test "$(git rev-parse --short HEAD)" = 1d1543b
git status --short
python3 -m py_compile scripts/storageops-ops tests/operational/test_storageops_ops.py
python3 -m pytest -q tests/operational/test_storageops_ops.py -k 'lock_contention or acquire_and_release_collect_lock or external_holder'
```

## DESIGN_REVIEW

The focused external-holder test makes `http_post_json` raise immediately if
the command reaches HTTP dispatch. That test is the authoritative proof that
dispatch is unreachable during contention. API journal inspection is optional
supporting evidence only; access-log presence or formatting is not assumed.

The separate Python process uses `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, exactly
matching the CLI. It signals readiness only after acquisition. `timeout`
automatically terminates it after 120 seconds, while a shell trap provides
immediate cleanup.

Journal validation is bounded to timestamps captured immediately before and
after each service start. A reusable Python validator ignores non-JSON lines,
parses compact or pretty-spaced single-line JSON with `json.loads`, selects the
latest `command=collect` record in that bounded journal, and asserts its result,
exit code, and (for contention) lock-held error.

On this host, `NextElapseUSecMonotonic` is rendered as a human-readable value
rather than a stable numeric timestamp. Immediately before lock acquisition,
the controlled block therefore displays `systemctl list-timers` and requires
the operator to confirm its `LEFT` value is at least five minutes. Stop if it
is not; the timer remains enabled and active throughout.

## READY_FOR_CONTROLLED_EXECUTION

Stop here. Do not run the remaining sudo or live-systemd commands without
explicit operator authorization.

## EXECUTION_RESULT

After authorization, run this entire block in one shell:

```bash
cd /opt/netapp-storageops-lab
RUN_ID="m5-r3-d6-c-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="/tmp/$RUN_ID"
mkdir -m 700 "$RUN_DIR"
HOLDER_PID=
cleanup_lock_holder() {
  if test -n "${HOLDER_PID:-}" && kill -0 "$HOLDER_PID" 2>/dev/null; then
    kill "$HOLDER_PID" 2>/dev/null || true
    wait "$HOLDER_PID" 2>/dev/null || true
  fi
}
trap cleanup_lock_holder EXIT INT TERM HUP

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

test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
test "$(systemctl is-active storageops-api.service)" = active
test "$(systemctl is-active storageops-mock-ontap.service)" = active
test "$(systemctl is-active storageops-collect.service)" = inactive
find evidence/m5/runtime -maxdepth 1 -type f -name 'collect-*.json' -printf '%f\n' | sort >"$RUN_DIR/evidence.before"

# Capture timer state immediately before lock acquisition. On this systemd
# version, use the operator-visible LEFT value because the show property is not
# a reliable numeric timestamp. Enter YES only when LEFT is at least 5 minutes.
systemctl show storageops-collect.timer -p UnitFileState -p ActiveState -p NextElapseUSecMonotonic --no-pager | tee "$RUN_DIR/timer-before-lock.properties"
systemctl list-timers storageops-collect.timer --no-pager | tee "$RUN_DIR/timer-before-lock.list"
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
read -r -p 'Confirm displayed LEFT is at least 5 minutes (YES to continue): ' TIMER_WINDOW_CONFIRMED
test "$TIMER_WINDOW_CONFIRMED" = YES

timeout --signal=TERM --kill-after=5s 120s python3 -u -c '
import fcntl, os, pathlib, signal, sys, time
lock = pathlib.Path(sys.argv[1])
ready = pathlib.Path(sys.argv[2])
with lock.open("a+", encoding="utf-8") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready.write_text(f"pid={os.getpid()}\n", encoding="utf-8")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True: time.sleep(1)
' /run/lock/storageops-collect.lock "$RUN_DIR/holder.ready" &
HOLDER_PID=$!
for attempt in $(seq 1 50); do
  test -s "$RUN_DIR/holder.ready" && break
  kill -0 "$HOLDER_PID"
  sleep 0.1
done
test -s "$RUN_DIR/holder.ready"
HOLDER_OWNER_PID="$(sed -n 's/^pid=//p' "$RUN_DIR/holder.ready")"
kill -0 "$HOLDER_OWNER_PID"

CONTENTION_JOURNAL_SINCE="$(date --utc --iso-8601=ns)"
sudo systemctl start storageops-collect.service || test "$?" -ne 0
CONTENTION_JOURNAL_UNTIL="$(date --utc --iso-8601=ns)"
sudo systemctl show storageops-collect.service -p Result -p ExecMainStatus --no-pager | tee "$RUN_DIR/contention.systemd"
test "$(sudo systemctl show storageops-collect.service -p Result --value)" = exit-code
test "$(sudo systemctl show storageops-collect.service -p ExecMainStatus --value)" = 80
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
sudo journalctl -u storageops-collect.service --since "$CONTENTION_JOURNAL_SINCE" --until "$CONTENTION_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/contention.journal"
validate_latest_collect_json "$RUN_DIR/contention.journal" FAIL 80

find evidence/m5/runtime -maxdepth 1 -type f -name 'collect-*.json' -printf '%f\n' | sort >"$RUN_DIR/evidence.after"
comm -13 "$RUN_DIR/evidence.before" "$RUN_DIR/evidence.after" >"$RUN_DIR/evidence.new"
test "$(wc -l <"$RUN_DIR/evidence.new")" -ge 1
CONTENTION_EVIDENCE="$(tail -n 1 "$RUN_DIR/evidence.new")"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["result"]=="FAIL" and d["exit_code"]==80 and any("lock is already held" in e for e in d["errors"])' "evidence/m5/runtime/$CONTENTION_EVIDENCE"

# Optional supporting observation only; the focused automated test is the
# authoritative no-dispatch proof. Do not fail validation based on access-log
# presence, absence, or formatting.
sudo journalctl -u storageops-api.service --since "$CONTENTION_JOURNAL_SINCE" --until "$CONTENTION_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/api-supporting.journal"
```

Expected: systemd `Result=exit-code`, `ExecMainStatus=80`; CLI JSON
`result=FAIL`, `exit_code=80`; contention evidence; focused no-dispatch test
passed; timer enabled and active.

## RECOVERY_RESULT

Continue in the same shell:

```bash
cleanup_lock_holder
HOLDER_PID=
test ! -e "/proc/$HOLDER_OWNER_PID"
RECOVERY_JOURNAL_SINCE="$(date --utc --iso-8601=ns)"
sudo systemctl start storageops-collect.service
RECOVERY_JOURNAL_UNTIL="$(date --utc --iso-8601=ns)"
sudo systemctl show storageops-collect.service -p Result -p ExecMainStatus --no-pager | tee "$RUN_DIR/recovery.systemd"
test "$(sudo systemctl show storageops-collect.service -p Result --value)" = success
test "$(sudo systemctl show storageops-collect.service -p ExecMainStatus --value)" = 0
test "$(systemctl is-enabled storageops-collect.timer)" = enabled
test "$(systemctl is-active storageops-collect.timer)" = active
sudo journalctl -u storageops-collect.service --since "$RECOVERY_JOURNAL_SINCE" --until "$RECOVERY_JOURNAL_UNTIL" -o cat --no-pager | tee "$RUN_DIR/recovery.journal"
validate_latest_collect_json "$RUN_DIR/recovery.journal" PASS 0
```

## FINAL_VERIFICATION

```bash
python3 -m py_compile scripts/storageops-ops tests/operational/test_storageops_ops.py
python3 -m pytest -q tests/operational/test_storageops_ops.py -k 'lock_contention or acquire_and_release_collect_lock or external_holder'
python3 -m pytest -q
git diff --check
scripts/storageops-ops verify | tee "$RUN_DIR/verify.log"
grep -Fx 'RESULT=PASS' "$RUN_DIR/verify.log"
grep -Fx 'EXIT_CODE=0' "$RUN_DIR/verify.log"
git status --short
trap - EXIT INT TERM HUP
```

Copy finalized, redacted output to `evidence/m5/` only after all assertions
pass. Do not remove the runtime evidence documents.
