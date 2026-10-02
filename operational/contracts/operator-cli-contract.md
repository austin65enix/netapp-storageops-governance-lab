# StorageOps Operator CLI Contract

## Status

Accepted

## Command Name

storageops-ops

## Purpose

The StorageOps Operator CLI provides a consistent and auditable interface for
authorized operational inspection, inventory collection, diagnostics, and
verification.

The CLI does not authorize ONTAP storage resource mutation.

## Global Behavior

Every command must:

- use UTC timestamps
- produce deterministic exit codes
- avoid unconditional PASS output
- avoid exposing credentials
- support operator-readable output
- preserve diagnostic context on failure
- identify the executed command
- identify the final result

## Global Options

- `--format text`
- `--format json`
- `--timeout SECONDS`
- `--evidence-dir PATH`
- `--no-evidence`
- `--version`
- `--help`

The default output format is `text`.

Evidence is enabled by default for commands that change operational state or
trigger collection.
## Commands

### status

Purpose:

Inspect project-owned systemd service states.

Required services:

- storageops-mock-ontap
- storageops-api
- prometheus
- grafana-server

Success criteria:

All required services are active.

Exit codes:

- 0: all required services active
- 20: one or more required services unavailable
- 100: unexpected failure

### health

Purpose:

Inspect StorageOps API and ONTAP dependency health.

Required endpoints:

- http://127.0.0.1:8100/healthz
- http://127.0.0.1:8000/api/cluster

Success criteria:

- StorageOps health endpoint returns HTTP 200
- Mock ONTAP cluster endpoint returns HTTP 200
- ONTAP state is online

Exit codes:

- 0: health checks passed
- 30: required endpoint unavailable
- 40: ONTAP dependency unavailable
- 100: unexpected failure

### collect

Purpose:

Trigger an authorized inventory collection.

Endpoint:

POST http://127.0.0.1:8100/api/inventory/collect

Success criteria:

- HTTP 200
- response status is collected
- snapshot file path is returned

Evidence:

Required unless `--no-evidence` is explicitly supplied in manual mode.

Exit codes:

- 0: collection completed
- 30: collection endpoint unavailable
- 40: ONTAP dependency unavailable
- 70: evidence write failure
- 80: lock contention
- 90: timeout
- 100: unexpected failure
### capacity

Purpose:

Inspect aggregate capacity and capacity metrics.

Required endpoint:

GET http://127.0.0.1:8100/api/storage/capacity

Required metric:

storageops_capacity_bytes

Success criteria:

- Capacity API returns HTTP 200
- total bytes is greater than zero
- used bytes is not negative
- available bytes is not negative
- utilization is between 0 and 100
- Prometheus capacity metric is present after collection

Exit codes:

- 0: capacity inspection passed
- 30: capacity endpoint unavailable
- 40: ONTAP dependency unavailable
- 50: capacity metric validation failure
- 100: unexpected failure

### alerts

Purpose:

Inspect active StorageOps alerts from Prometheus.

Success criteria:

The Prometheus alerts API is reachable and the response is valid.

The command may return exit code 0 when alerts are firing, provided the
query itself succeeded.

Output must distinguish:

- no active alerts
- pending alerts
- firing alerts

Exit codes:

- 0: alert inspection completed
- 30: Prometheus endpoint unavailable
- 60: alert response validation failure
- 100: unexpected failure

### collection-summary

Purpose:

Inspect the read-only scheduled collection operational summary through the
application service boundary.

Output fields, in order:

- `latest_run_id`
- `latest_run_status`
- `latest_run_started_at`
- `latest_run_completed_at`
- `last_success_at`
- `last_failure_at`
- `consecutive_failures`
- `timer_enabled`
- `timer_active`
- `next_trigger`
- `collection_health`

Datetime fields use UTC ISO-8601 values ending in `Z`. JSON preserves unknown
values as `null`, booleans as JSON booleans, and collection health as one of
`HEALTHY`, `DEGRADED`, or `UNHEALTHY`.

The JSON output is the machine-consumable interface and follows
`collection-summary-json-contract.md`. Successful and failure JSON envelopes
identify that contract with the top-level string field `"contract_version":
"1"`. Text output is intended for operators and is not a machine-consumable
contract.

The command result reports whether inspection completed. Collection health
reports the observed operational condition. `HEALTHY`, `DEGRADED`, and
`UNHEALTHY` are therefore successful inspection results and do not by
themselves make the command fail.

The command must not execute collection, write evidence, mutate systemd, or
mutate ONTAP resources. Its `evidence_file` is always null.

Exit codes:

- 0: summary inspection completed, for every collection health value
- 100: unexpected inspection failure

### verify

Purpose:

Execute final operational verification.

Checks:

- required services
- required endpoints
- Prometheus target
- ONTAP dependency metric
- core StorageOps metrics
- active alerts
- capacity panel query

Success criteria:

All required assertions pass.

Exit codes:

- 0: verification passed
- 20: service failure
- 30: endpoint failure
- 40: dependency failure
- 50: metric failure
- 60: alert validation failure
- 70: evidence write failure
- 100: unexpected failure
### version

Purpose:

Display CLI version and Git revision when available.

Exit codes:

- 0: version displayed
- 100: unexpected failure

## Text Output Contract

Text output must use key-value records where practical.

Example:

```text
COMMAND=status
UTC_TIMESTAMP=20260804T070000Z
storageops-api=active
storageops-mock-ontap=active
prometheus=active
grafana-server=active
RESULT=PASS
EXIT_CODE=0
```

## JSON Output Contract

JSON output must contain:

```json
{
  "command": "status",
  "timestamp": "2026-08-04T07:00:00Z",
  "result": "PASS",
  "exit_code": 0,
  "data": {},
  "errors": [],
  "evidence_file": null
}
```

## Evidence Contract

Evidence-producing commands must include:

- command
- execution ID
- UTC start timestamp
- UTC completion timestamp
- result
- exit code
- relevant raw responses
- evidence path

## Safety Boundary

The CLI must not:

- create ONTAP volumes
- delete ONTAP volumes
- create or delete LUNs
- modify snapshot policies
- modify ONTAP networking
- modify storage capacity
- execute production remediation

## Initial Version

The initial CLI version is:

0.1.0
