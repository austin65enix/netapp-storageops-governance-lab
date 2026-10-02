# Collection Summary JSON Contract v1

## Scope

This contract defines the machine-consumable JSON output of:

```text
storageops-ops --format json collection-summary
```

Machine consumers must use JSON rather than the command's operator-oriented
text output.

## Envelope

Successful and failure JSON envelopes contain the existing fields
`command`, `timestamp`, `result`, `exit_code`, `data`, `errors`, and
`evidence_file`, plus the top-level string field:

```json
"contract_version": "1"
```

`result` describes whether inspection succeeded. `collection_health`
describes the observed operational condition. Consequently, `HEALTHY`,
`DEGRADED`, and `UNHEALTHY` all produce `"result": "PASS"` and
`"exit_code": 0` when inspection succeeds.

An unexpected service or serialization failure produces the existing
unexpected-failure exit code (`100`) and a failure envelope carrying
`"contract_version": "1"`. This contract introduces no new exit-code
taxonomy. The command does not write evidence, so `evidence_file` remains
`null`.

## Data

On success, `data` contains exactly these 11 fields:

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

Datetime values are serialized in UTC ISO-8601 form ending in `Z`. Python
`None` values are JSON `null`, booleans are JSON booleans, and
`collection_health` is the enum value: `HEALTHY`, `DEGRADED`, or `UNHEALTHY`.

## Compatibility

Consumers must ignore unknown future fields and must not treat field ordering
as semantic. Adding optional fields without changing existing semantics is
backward compatible. A semantic breaking change requires a future contract
version.

## Example

```json
{
  "command": "collection-summary",
  "contract_version": "1",
  "data": {
    "collection_health": "HEALTHY",
    "consecutive_failures": 0,
    "last_failure_at": null,
    "last_success_at": "2026-08-10T11:59:00Z",
    "latest_run_completed_at": "2026-08-10T11:59:00Z",
    "latest_run_id": "collect-20260810T115800Z-ab12cd34",
    "latest_run_started_at": "2026-08-10T11:58:00Z",
    "latest_run_status": "PASS",
    "next_trigger": "2026-08-10T12:05:00Z",
    "timer_active": true,
    "timer_enabled": true
  },
  "errors": [],
  "evidence_file": null,
  "exit_code": 0,
  "result": "PASS",
  "timestamp": "2026-08-10T12:00:00Z"
}
```
