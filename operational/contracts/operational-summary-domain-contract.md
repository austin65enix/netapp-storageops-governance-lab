# StorageOps Scheduled Collection Operational Summary Domain Contract

## Status

Accepted

## Scope

This contract defines a pure read model for the operational state of scheduled
collection. Evaluation consumes supplied state and time; it performs no I/O.

## Fields

The summary contains:

- `latest_run_id`: string or null
- `latest_run_status`: `PASS`, `FAIL`, or null
- `latest_run_started_at`: timezone-aware datetime or null
- `latest_run_completed_at`: timezone-aware datetime or null
- `last_success_at`: timezone-aware datetime or null
- `last_failure_at`: timezone-aware datetime or null
- `consecutive_failures`: non-negative integer or null
- `timer_enabled`: boolean or null
- `timer_active`: boolean or null
- `next_trigger`: timezone-aware datetime or null
- `collection_health`: `HEALTHY`, `DEGRADED`, or `UNHEALTHY`

Null values preserve the distinction between known state and state that could
not be established. Historical success and failure times may be null when no
corresponding run exists.

## Health Evaluation

`HEALTHY` requires all of the following:

- a non-empty latest run ID
- a latest run status of `PASS`
- valid, ordered, timezone-aware latest-run timestamps
- zero consecutive failures
- an enabled and active timer
- a timezone-aware `next_trigger` strictly later than the supplied evaluation
  time

`DEGRADED` requires the same known run and timer state, except that the latest
run status is `FAIL` and consecutive failures is greater than zero.

All other cases are `UNHEALTHY`. In particular, missing state, unknown status,
naive or contradictory timestamps, invalid failure counts, disabled or
inactive timers, and non-future triggers fail closed.

## Safety Boundary

The read model must not:

- execute collection
- mutate systemd services or timers
- mutate ONTAP resources
- create, alter, or delete evidence
- perform remediation
- expose an API, CLI, or dashboard integration
