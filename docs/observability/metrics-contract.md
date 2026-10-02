# NETAPP-M4 Metrics Contract

## Purpose

This contract defines the first observability metrics exposed by the
Enyrax StorageOps API.

## Endpoint

GET /metrics

The endpoint uses the Prometheus text exposition format.

## Metric Namespace

All application metrics use the prefix:

storageops_

## Runtime Metrics

### storageops_info

Type: Gauge

Purpose:

Application build and runtime identity.

Labels:

- version
- source

Expected value:

1

### storageops_up

Type: Gauge

Purpose:

Indicates whether the StorageOps API process is operational.

Values:

- 1: operational
- 0: unavailable

### storageops_ontap_up

Type: Gauge

Purpose:

Indicates whether the configured ONTAP source is reachable.

Labels:

- source

Values:

- 1: reachable
- 0: unavailable

## HTTP Metrics

### storageops_http_requests_total

Type: Counter

Labels:

- method
- endpoint

Purpose:

Counts requests received by the StorageOps API.

### storageops_http_responses_total

Type: Counter

Labels:

- method
- endpoint
- status_code

Purpose:

Counts responses by HTTP status code.

### storageops_http_request_duration_seconds

Type: Histogram

Labels:

- method
- endpoint

Purpose:

Measures request latency.

## ONTAP Dependency Metrics

### storageops_ontap_requests_total

Type: Counter

Labels:

- operation
- result

Purpose:

Counts calls to the ONTAP adapter.

### storageops_ontap_errors_total

Type: Counter

Labels:

- operation
- error_type

Purpose:

Counts controlled ONTAP dependency failures.

## Inventory Metrics

### storageops_inventory_objects

Type: Gauge

Labels:

- resource_type
- source

Resource types:

- volume
- lun
- snapshot

Purpose:

Reports the current inventory object count.

### storageops_capacity_bytes

Type: Gauge

Labels:

- category
- source

Categories:

- total
- used
- available

Purpose:

Reports aggregate storage capacity.

### storageops_volume_utilization_percent

Type: Gauge

Labels:

- volume
- svm
- source

Purpose:

Reports volume utilization percentage.

## Workflow Metrics

### storageops_snapshot_runs_total

Type: Counter

Labels:

- result

Purpose:

Counts inventory snapshot workflow runs.

### storageops_diff_events_total

Type: Counter

Labels:

- resource_type
- change_type

Purpose:

Counts inventory change events.

## Label Policy

Allowed bounded labels include:

- method
- endpoint
- status_code
- operation
- result
- resource_type
- change_type
- source
- volume
- svm

The following labels are prohibited:

- request_id
- timestamp
- arbitrary error messages
- dynamically generated UUID values
- full URL query strings

This policy prevents uncontrolled metric cardinality.

## Initial Acceptance Criteria

- Metrics use the storageops_ namespace.
- GET /metrics returns Prometheus text format.
- ONTAP dependency status is observable.
- HTTP 200 and 502 responses are countable.
- Inventory object counts are observable.
- Capacity values are observable.
- Metrics do not expose secrets.
