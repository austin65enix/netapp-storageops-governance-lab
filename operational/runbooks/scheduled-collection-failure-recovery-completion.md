# Scheduled Collection Failure and Recovery Completion Verification

## 1. Scope

This document records the final read-only verification for
`NETAPP-M5-R3-D6-F-D1`, covering the D6-A through D6-E scheduled collection
failure and recovery workstream. No new failure scenario was created, no live
failure injection was repeated, systemd state and runtime evidence were not
modified, and no finalized evidence or commit was created.

This verification does not declare the broader M5-R3 or M5 project complete.

## 2. Baseline Branch and Starting HEAD

- Required and observed branch: `feature/netapp-m5-operational-automation`
- Required and observed starting HEAD:
  `6b82a9293fb2d24fbc88c746431aa11eee0ef703` (`6b82a92`)
- Initial working tree: clean, including untracked files
- Preflight result: PASS

## 3. D6-A Through D6-E Stage Matrix

| Stage | Verified completion basis | Result |
| --- | --- | --- |
| D6-A | Accepted failure contract documents boundaries, exit taxonomy, recovery, cleanup, and safety expectations; committed evidence ends `NETAPP_M5_R3_D6_A=PASS`. | PASS |
| D6-B | Committed evidence records Mock ONTAP unavailability, `FAIL/40`, preserved failure evidence, timer continuity, dependency restoration, recovery `Result=success` and `ExecMainStatus=0`, and operational verification PASS. | PASS |
| D6-C | Contract, executable runbook, operator documentation, focused tests, and final evidence verify lock-before-collection behavior, `FAIL/80`, no HTTP dispatch in the authoritative focused test, lock reacquisition, and recovery success. | PASS |
| D6-D | Contract, executable runbook, operator documentation, focused tests, and final evidence verify HTTP success before evidence writing, replacement by `FAIL/70`, bounded systemd failure records, cleanup/restoration, recovery success, and automated immutability coverage. | PASS, subject to documented live-manifest limitation |
| D6-E | Final evidence and focused tests verify failure/recovery ordering, later successes, continuing enabled/active/waiting timer state, future NEXT, and the timer-driven inference boundary. | PASS, inference boundary retained |

The completed stages are historically supported. D6-F initially found forbidden
system-Python pytest invocations in the D6-C operator script; the bounded
remediation and successful revalidation are recorded in Sections 10, 15, and 16.

## 4. Failure Taxonomy

| Failure boundary | Required behavior | Verified source |
| --- | --- | --- |
| Required local service unavailable | Fail closed; preserve nonzero result. | Failure contract |
| HTTP endpoint unavailable | Fail closed; preserve nonzero result. | Collection and failure contracts/tests |
| External dependency unavailable | `FAIL/40`; timer remains enabled and active; recover after restoration without reinstalling the unit. | D6-B evidence |
| Capacity validation failure | Fail closed with code 50. | Failure contract |
| Alert validation failure | Fail closed with code 60. | Failure contract |
| Evidence write failure | Successful HTTP collection must not mask evidence failure; `FAIL/70`; journal diagnostic; cleanup and recovery. | D6-D evidence/tests |
| Lock contention | Acquire lock before HTTP dispatch; `FAIL/80`; later reacquisition and recovery. | D6-C evidence/tests |
| Timeout | Fail closed with code 90. | Failure contract |
| Unexpected internal failure | Fail closed with code 100. | Failure contract |

## 5. Exit-Code Matrix

| Code | Meaning |
| ---: | --- |
| 0 | Successful operation |
| 20 | Required local service unavailable |
| 30 | HTTP endpoint unavailable |
| 40 | External dependency unavailable |
| 50 | Capacity metric validation failure |
| 60 | Alert validation failure |
| 70 | Execution evidence write failure |
| 80 | Collection lock contention |
| 90 | Command timeout |
| 100 | Unexpected internal failure |

## 6. Cleanup Matrix

| Stage | Cleanup requirement | Verified outcome |
| --- | --- | --- |
| D6-B | Restore dependency; leave no permanent dependency mutation. | Mock ONTAP recovery recorded; current service active; no permanent dependency mutation evidenced. |
| D6-C | Release bounded external lock holder; make lock reacquirable; do not stop or disable timer. | Holder processes gone, lock-release verification PASS, recovery collection PASS. |
| D6-D | Remove transient drop-in and isolated failure directory; daemon-reload; restore original `ExecStart`; preserve runtime evidence. | Override removed, failure directory removed, original `ExecStart` restored, no current drop-ins. Live pre-existing runtime immutability cannot be reconstructed; automated coverage passes. |
| D6-E | No injected state; confirm continued timer scheduling and successful later execution. | Enabled/active/waiting timer and later PASS/0 executions verified. |

## 7. Recovery Matrix

| Stage | Failure | Recovery proof | Result |
| --- | --- | --- | --- |
| D6-B | Mock ONTAP unavailable; collection `FAIL/40`. | Dependency online, service `Result=success`, `ExecMainStatus=0`, operational verify PASS. | PASS |
| D6-C | Lock contention; collection `FAIL/80`; HTTP dispatch blocked by focused test. | Lock reacquired and scheduled collection succeeded. | PASS |
| D6-D | `collect-20260805T074006Z-fe60d2a1`; HTTP 200/collected followed by evidence-write `FAIL/70`; journal `status=70/SOFTWARE` and `Failed with result 'exit-code'`. | Cleanup/restoration PASS; later service `Result=success`, `ExecMainStatus=0`. | PASS with limitation |
| D6-E | Historical D6-D failure above. | First later recovery `collect-20260805T075507Z-ced54553`; additional later success `collect-20260805T081008Z-50f91e1e`; timer continuity retained. | PASS, timer-driven classification is inference |

## 8. Evidence Inventory with SHA-256

All three final evidence files are tracked, non-empty, contain their expected
stage identifier and final PASS marker, and contain none of: `unbound
variable`, `Traceback`, `FAILED ATTEMPT`, `command not found`, or `syntax
error`. Known D6-D historical observations (`status=70/SOFTWARE`, `Failed with
result 'exit-code'`, and `evidence write failed`) were treated as intentional
failure evidence, not evidence-file failures.

| Evidence file | Bytes | SHA-256 | Validation |
| --- | ---: | --- | --- |
| `evidence/m5/m5-r3-d6-c-lock-contention-final-20260805T062826Z.log` | 7112 | `454946f033133fd11ae0f3743154c7c94db74055dd585fb18bfd4ab4441f97da` | PASS |
| `evidence/m5/m5-r3-d6-d-evidence-write-failure-final-20260806T020619Z.log` | 6780 | `a26af6c61ffec713d8b336e08a3d63407841a44489a311c2f3ab5cdab2adaa13` | PASS |
| `evidence/m5/m5-r3-d6-e-timer-continuity-final-20260806T035452Z.log` | 7822 | `442c13b725d71e51c924d9c9334503a16fd6010c8aa388107e4130b7f53e39a7` | PASS |

D6-A and D6-B are additionally supported by tracked committed evidence:

- `evidence/m5/r3-d6-a-failure-handling-contract-20260805T024556Z.log`
- `evidence/m5/r3-d6-b-ontap-dependency-failure-20260805T031459Z.log`

## 9. Commit Inventory

All five commits below exist and `git merge-base --is-ancestor <commit> HEAD`
returned zero for each.

| Stage | Commit | Subject | Ancestor of starting HEAD |
| --- | --- | --- | --- |
| D6-A | `b68191e209e30a34cf5e8f5255717c4898833160` | `docs: define scheduled collection failure handling` | Yes |
| D6-B | `1d1543bda6de42d61b4fc0000cce349d9f35a56a` | `ops: verify scheduled collection dependency recovery` | Yes |
| D6-C | `012c8aac4e4ee3100315dfc53b0ccaa7707dc876` | `test(operations): validate scheduled collection lock contention` | Yes |
| D6-D | `6402b99aa29b15b72c4e87d026820e594cb2a198` | `test(operations): verify scheduled collection evidence-write failure` | Yes |
| D6-E | `6b82a9293fb2d24fbc88c746431aa11eee0ef703` | `test(operations): verify scheduled timer continuity and recovery` | Yes |

## 10. Implementation and Test Inventory

The following requested files are tracked:

- Contracts: `operational/contracts/scheduled-collection-contract.md` and
  `operational/contracts/scheduled-collection-failure-contract.md`
- Runbooks: `operational/runbooks/run-d6-c-lock-contention.sh`,
  `operational/runbooks/scheduled-collection-lock-contention.md`,
  `operational/runbooks/run-d6-d-evidence-write-failure.sh`,
  `operational/runbooks/scheduled-collection-evidence-write-failure.md`, and
  `operational/runbooks/scheduled-collection-timer-continuity.md`
- Tests: `tests/operational/test_storageops_ops.py` and
  `tests/operational/test_timer_continuity.py`

Both operator scripts are tracked with mode `100755`; all other requested
inventory files are mode `100644`.

Static and test results:

| Check or command | Result |
| --- | --- |
| `bash -n` for every tracked `operational/runbooks/*.sh` | PASS |
| `.venv/bin/python -m py_compile scripts/storageops-ops tests/operational/test_storageops_ops.py tests/operational/test_timer_continuity.py` | PASS |
| `.venv/bin/python -m pytest -q tests/operational/test_storageops_ops.py -k dependency_failure` | 1 passed, 33 deselected, 1 warning |
| `.venv/bin/python -m pytest -q tests/operational/test_storageops_ops.py -k lock_contention` | 3 passed, 31 deselected, 1 warning |
| `.venv/bin/python -m pytest -q tests/operational/test_storageops_ops.py -k evidence_write_failure` | 1 passed, 33 deselected, 1 warning |
| `.venv/bin/python -m pytest -q tests/operational/test_timer_continuity.py` | 5 passed, 1 warning |
| `.venv/bin/python -m pytest -q` | 55 passed, 1 warning |
| `git diff --check` before document creation | PASS |
| `.orig`/`.rej` search | PASS; none found |
| Forbidden pytest invocation scan in D6 operator scripts | PASS; no `/usr/bin/python3 -m pytest`, `python3 -m pytest`, or bare `pytest` commands found after remediation |
| Required `.venv/bin/python` usage | PASS; project interpreter exists and is executable; D6-C and D6-D pytest commands use it |

Every focused selection collected and passed at least one test. The dependency
selection verifies the behavior named by `test_health_dependency_failure`; it
does not claim to recreate the historical D6-B live systemd failure.

The initial D6-F static validation found `python3 -m pytest` at the then-current
lines 223 and 224 of `run-d6-c-lock-contention.sh`. Remediation defined
`PYTHON="$REPO/.venv/bin/python"`, added `test -x "$PYTHON"`, and replaced only
those two pytest invocations with `"$PYTHON" -m pytest ...`. Failure injection,
cleanup, timer, lock, runtime evidence, and collection behavior were not
changed. Repository-only revalidation then passed shell syntax, forbidden-form
scanning, compilation, every focused selection, the full suite, operational
verification, diff checks, and artifact checks.

## 11. Operational State Snapshot

Read-only capture time: `2026-08-06T05:10:41+00:00`.

| Property | Observed value | Result |
| --- | --- | --- |
| `storageops-collect.timer` enabled | `enabled` | PASS |
| Timer active state | `active` | PASS |
| Timer substate | `waiting` | PASS |
| Timer LAST | `Thu 2026-08-06 05:08:14 UTC` | PASS |
| Timer NEXT | `Thu 2026-08-06 05:23:14 UTC` | PASS; future at capture time |
| Timer trigger relationship | `Triggers=storageops-collect.service`; unit `ACTIVATES` service | PASS |
| Timer `DropInPaths` | empty | PASS |
| Service `Result` | `success` | PASS as current recovery state only |
| Service `ExecMainStatus` | `0` | PASS as current recovery state only |
| Service `DropInPaths` | empty | PASS |
| Effective evidence directory | `/opt/netapp-storageops-lab/evidence/runtime` | PASS |
| Effective lock file | `/run/lock/storageops-collect.lock` | PASS |
| `storageops-api.service` | active | PASS |
| `storageops-mock-ontap.service` | active | PASS |
| `prometheus.service` | active | PASS |
| `grafana-server.service` | active | PASS |

Current `Result=success` is not historical failure proof. Historical failure
claims remain sourced from committed final evidence and its bounded journal
records.

Operational revalidation at `20260806T055235Z` returned:

```text
completed_count=4
passed_count=4
required_count=4
read_only=True
RESULT=PASS
EXIT_CODE=0
```

## 12. Known Evidence Limitations

- The D6-D live `runtime.before` SHA-256 manifest was not retained after the
  interrupted operator script.
- Live pre-existing runtime evidence immutability could not be reconstructed
  afterward.
- Automated focused-test coverage verifies the intended immutability behavior.
- D6-E timer-driven recovery is a strongly supported inference, not direct
  per-invocation trigger metadata.
- The Starlette/httpx deprecation warning is non-blocking but remains technical
  debt.

These limitations are not rewritten or counted as independent PASS claims.

## 13. Timer-Driven Inference Boundary

The timer-to-service relationship, enabled/active/waiting state, historical
journal timing, configured cadence, runtime evidence ordering, LAST, and future
NEXT strongly support timer-driven recovery. They do not provide direct
per-invocation trigger identity. Therefore the classification remains an
explicit inference; no direct trigger-identity claim is made.

## 14. Security and Safety Boundaries

- Verification was read-only except for this authorized documentation file.
- No service, timer, drop-in, lock, dependency, or runtime evidence was changed.
- No failure injection was performed.
- No volume, LUN, snapshot, aggregate, SVM, or ONTAP configuration was created,
  modified, or deleted.
- Historical evidence is used only within its recorded bounds.
- No finalized evidence file and no commit were created.

## 15. Final Completion Criteria

| Gate | Result |
| --- | --- |
| PREFLIGHT | PASS |
| COMMIT_HISTORY_REVIEW | PASS |
| IMPLEMENTATION_INVENTORY_REVIEW | PASS |
| EVIDENCE_INVENTORY_REVIEW | PASS |
| FAILURE_RECOVERY_MATRIX_REVIEW | PASS with documented limitations/inference boundary |
| STATIC_VALIDATION | PASS after bounded D6-C project-interpreter remediation and full revalidation |
| OPERATIONAL_STATE_REVIEW | PASS |
| COMPLETION_DOCUMENT_REVIEW | PASS |
| READY_FOR_OPERATOR_FINALIZATION | PASS |

All completion gates pass. The final working tree contains only the authorized
D6-C operator-script remediation and this untracked completion document.

Recommended final evidence filename:
`evidence/m5/m5-r3-d6-f-failure-recovery-completion-final-<UTC_TIMESTAMP>.log`.

Recommended commit message after explicit operator authorization:
`docs(operations): complete scheduled failure recovery verification`.

## 16. Final Status

`NETAPP_M5_R3_D6_IMPLEMENTATION=COMPLETE`

`NETAPP_M5_R3_D6_VERIFICATION=PASS`

`READY_FOR_OPERATOR_FINALIZATION=YES`

No broader M5-R3 or M5 completion claim is made.
