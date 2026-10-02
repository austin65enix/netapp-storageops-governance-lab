# Scheduled Collection Timer Continuity and Automatic Recovery

## PREFLIGHT

Confirm branch `feature/netapp-m5-operational-automation`, HEAD `6402b99`, and an initially clean tree. Installed timer values are `Unit=storageops-collect.service`, `OnBootSec=5min`, `OnUnitActiveSec=15min`, `AccuracySec=1min`, and `Persistent=true`. Confirm `TriggeredBy=storageops-collect.timer` and empty `DropInPaths` for both units.

## HISTORICAL_EVIDENCE_REVIEW

Bound the journal from `2026-08-05T07:40:06Z` and parse JSON with Python `json.loads`. D6-D `collect-20260805T074006Z-fe60d2a1` has `command=collect`, `FAIL/70`, strict `started_at`/`completed_at`, HTTP 200, collection `status=collected`, and the evidence-write diagnostic. The journal has `status=70/SOFTWARE` and `Failed with result 'exit-code'`. Current service Result is not historical proof.

The earliest later evidence is `collect-20260805T075507Z-ced54553.json`: start `2026-08-05T07:55:07.991815Z`, completion `2026-08-05T07:55:08.066198Z`, `PASS/0`. Journal start `07:55:07.882630Z` correlates with `Deactivated successfully` and `Finished` at `07:55:08.090221Z` and `07:55:08.090379Z`.

## TIMER_CONTINUITY_DESIGN_REVIEW

`OnUnitActiveSec=15min` schedules from prior activation. Recovery started 15 minutes and 1.55 seconds after failure start, followed by another start at `08:10:08.203696Z`. The installed unit relationship directly identifies timer/service linkage.

Historical `Starting` messages have no per-invocation trigger-source field. Timer causality at 07:55 is therefore an explicit inference from the unit relationship, exact cadence, uninterrupted sequence, runtime correlation, and retained schedule. No bounded journal entry indicates manual timer enable/start/restart. A generic `Starting` message alone does not distinguish manual and timer starts.

## EXISTING_EVIDENCE_SUFFICIENT

Existing evidence proves continuity. Do not inject failure or create an observation script. At review the timer was enabled, active/waiting, LAST `2026-08-06T02:53:12Z`, future NEXT `2026-08-06T03:08:12Z`; service `Result=success`, `ExecMainStatus=0`; both drop-in lists empty. LAST correlated with PASS/0 `collect-20260806T025313Z-1be4e7bd`.

## OBSERVATION_RESULT

`NOT_REQUIRED`: no live observation or timer mutation was performed.

## FINAL_VERIFICATION

Compile Python; run focused and full tests; `bash -n` shell scripts; check tracked and untracked diffs; run operational verify; reject `.orig`/`.rej`; report exact status; do not create finalized evidence or commit.
