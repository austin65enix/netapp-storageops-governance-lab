# StorageOps Scheduled Collection Failure Handling Contract

## Status

Accepted

## Purpose

This contract defines failure and recovery behavior for scheduled collection.

Failure handling does not authorize ONTAP resource mutation.

## System Boundary

The scheduled collection path consists of:

- `storageops-collect.timer`
- `storageops-collect.service`
- `scripts/storageops-ops collect`
- StorageOps API
- Mock ONTAP API
- runtime execution evidence
- `/run/lock/storageops-collect.lock`

## General Failure Rules

A failed collection must:

- preserve the CLI exit code
- cause the oneshot service execution to fail
- write diagnostic output to the systemd journal
- not report `result=PASS`
- not report `exit_code=0`
- not disable or stop the timer
- not authorize ONTAP resource mutation
- remain recoverable after the dependency is restored

## Expected Exit Codes

- `0`: successful operation
- `20`: required local service unavailable
- `30`: HTTP endpoint unavailable
- `40`: external dependency unavailable
- `50`: capacity metric validation failure
- `60`: alert validation failure
- `70`: execution evidence write failure
- `80`: collection lock contention
- `90`: command timeout
- `100`: unexpected internal failure

## Dependency Failure

When Mock ONTAP or the StorageOps collection dependency is unavailable:

- collection must return a non-zero exit code
- systemd must record `Result=failed`
- `ExecMainStatus` must preserve the CLI exit code
- the timer must remain enabled and active
- recovery must not require reinstalling the unit

## Lock Contention

When the collection lock is already held:

- collection must return exit code `80`
- no collection HTTP request may be issued
- contention evidence must be produced when evidence writing is available
- the timer must remain enabled and active

Controlled validation must use a separate process holding the same exclusive
`flock` as the CLI. The holder must have a bounded lifetime and shell-exit
cleanup. A focused automated test that makes `http_post_json` fail if reached
is the authoritative proof that lock contention prevents HTTP dispatch.
StorageOps API journal inspection is optional supporting evidence only. Before
acquiring the lock, confirm the timer is enabled and active and that its
operator-visible next-trigger `LEFT` value is at least five minutes. Stop for
explicit authorization before any `sudo` or live `systemctl` mutation, then
recover without stopping or disabling the timer.

## Evidence Write Failure

When runtime evidence cannot be written:

- collection must return exit code `70`
- the write failure must appear in stderr or the journal
- a successful API response must not override the evidence failure
- the timer must remain enabled and active

Controlled validation must dispatch collection successfully before injecting
the local evidence failure. Use a temporary root-owned directory under `/run`
that user `atn` cannot write, and redirect only the service's
`--evidence-dir` with a transient drop-in under `/run/systemd/system`. Do
not change permissions or remove files in `evidence/m5/runtime`. Capture the
installed `ExecStart` before mutation; cleanup must remove the transient
drop-in, run `systemctl daemon-reload`, verify the original `ExecStart`, and
remove only the temporary isolated directory. The collection lock must be
released after the write failure so that one immediate recovery execution can
succeed.

## Timer Continuity

A single failed service execution must not permanently stop scheduling.

Continuity requires bounded historical failure journal evidence; an enabled and active timer with no override; the earliest later runtime document parsed as JSON with strict UTC `started_at` and `completed_at`, `result=PASS`, and `exit_code=0`; a correlated successful service completion; timer LAST consistent with that execution; and a future NEXT trigger. Runtime ordering must not depend on a top-level `timestamp`, which may be absent.

Use direct systemd trigger metadata when available. Otherwise timer causality may be inferred only from the timer/service relationship, enabled/active and LAST/NEXT state, journal invocation time, configured cadence, and runtime evidence time. Label that conclusion as inference; cadence alone is insufficient.

After the failed condition is removed:

- a later service execution must return exit code `0`
- systemd must record `Result=success`
- a new runtime evidence document must be written
- operational verification must return `RESULT=PASS`

## Evidence Requirements

Failure verification evidence must include:

- scenario name
- injection timestamp
- pre-injection timer state
- service result
- `ExecMainStatus`
- journal output
- evidence file path when available
- recovery timestamp
- post-recovery timer state
- post-recovery successful execution evidence

## Safety Boundary

Failure injection is limited to lab-local service availability,
lock ownership, and evidence-directory permissions.

No volume, LUN, snapshot, aggregate, SVM, or ONTAP configuration
may be created, modified, or deleted.
