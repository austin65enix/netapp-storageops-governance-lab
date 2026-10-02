# Scheduled Collection Evidence Write Failure Validation

## PREFLIGHT

The operator script verifies branch `feature/netapp-m5-operational-automation`,
HEAD `012c8aa`, the exact working-tree allowlist, no `.orig`/`.rej`,
the executable project interpreter `/opt/netapp-storageops-lab/.venv/bin/python`
with importable pytest, `sudo -n true`, timer enabled/active, API and Mock
ONTAP active, and collect service inactive. Immediately before confirmation,
it obtains the single timer row with `systemctl list-timers
storageops-collect.timer --all --no-legend --no-pager`, reads the displayed
NEXT weekday/date/time/timezone, converts it with `date -d ... +%s`, subtracts
`date +%s`, prints `TIMER_SECONDS_LEFT`, and exits unless the result is at
least 300. Exact `YES` remains a second, later admission gate.

## IMPLEMENTATION_REVIEW

`command_collect` acquires the lock, then HTTP dispatch occurs. The nested
`finish` writes evidence before rendering the CLI result. A writer exception
replaces even HTTP success with `FAIL/70` and a diagnostic. The outer
`finally` releases the lock. Focused tests prove dispatch, 70 mapping,
preservation of existing evidence, lock reacquisition, and recovery.

Before operator confirmation or creation of any isolated runtime directory,
the script uses the project interpreter for compilation and focused/full
pytest, then runs shell syntax, diff, and operational verification. No
repository-level validation is deferred until after systemd mutation.
Pure shell helper checks reject 299 seconds, accept 300 and 301 seconds, accept
`YYYY-MM-DDTHH:MM:SSZ`, and reject the comma-form nanosecond timestamp.

## FAILURE_INJECTION_DESIGN_REVIEW

Create a root-owned mode-0500 directory at
`/run/storageops-evidence-write-failure-<timestamp>`. Never alter
`evidence/m5/runtime`; snapshot its file digests before failure and compare
afterward.

Capture original `ExecStart`, then transiently install only:

```ini
[Service]
ExecStart=
ExecStart=/opt/netapp-storageops-lab/scripts/storageops-ops --format json --timeout 30 --evidence-dir /run/storageops-evidence-write-failure-<timestamp> --lock-file /run/lock/storageops-collect.lock collect
```

at `/run/systemd/system/storageops-collect.service.d/90-evidence-write-failure.conf`.
Cleanup always removes the drop-in, daemon-reloads, verifies original
`ExecStart`, removes only the isolated directory, and resets failed state only
for the collect service if needed. It never removes runtime evidence or
stops/disables the timer.

## READY_FOR_OPERATOR_EXECUTION

Stop here. Do not execute
`operational/runbooks/run-d6-d-evidence-write-failure.sh` without explicit
authorization for sudo and live systemd mutation.

## EXECUTION_RESULT

Authorized execution requires `Result=exit-code`, `ExecMainStatus=70`, and
bounded journal JSON parsed with `json.loads` containing `FAIL/70` and the
evidence-write diagnostic. Both failure and recovery captures set `--since`
with `date -u +%Y-%m-%dT%H:%M:%SZ`; after execution they set `--until` to one
second beyond the current UTC whole second. Both boundaries are validated as
strict `YYYY-MM-DDTHH:MM:SSZ` values before being passed to `journalctl`.

## RECOVERY_RESULT

After cleanup and original-command verification, one collection must produce
`Result=success`, `ExecMainStatus=0`, journal `PASS/0`, with timer and
dependencies still active.

## FINAL_VERIFICATION

Recheck timer safety and original `ExecStart`, then report exact Git status.
Write finalized evidence only afterward.
