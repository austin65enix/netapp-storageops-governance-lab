# StorageOps Operational Runbook Contract

## Status

Accepted

## Purpose

This contract defines how StorageOps operational runbooks are designed,
executed, verified, and recorded.

## Execution Modes

A runbook may execute in one of the following modes:

- manual
- scheduled
- verification
- failure-injection

## Safety Boundary

Runbooks may perform health checks, metric queries, inventory collection,
evidence capture, and project-owned service verification.

Runbooks must not create, modify, or delete ONTAP storage resources unless a
future milestone explicitly authorizes storage mutation.

## Required Inputs

Each runbook must define:

- runbook name
- execution mode
- trigger
- timeout
- required services
- required endpoints
- required permissions

## Required Outputs

Each execution must produce:

- execution ID
- UTC start timestamp
- UTC completion timestamp
- result
- exit code
- relevant service states
- relevant endpoint states
- relevant metric states
- relevant alert states
- evidence file path

## Exit Codes

- 0: successful execution
- 10: contract validation failure
- 20: required service unavailable
- 30: required endpoint unavailable
- 40: dependency unavailable
- 50: metric validation failure
- 60: alert validation failure
- 70: evidence write failure
- 80: lock contention
- 90: timeout
- 100: unexpected execution failure

## Result States

- PASS
- FAIL
- PARTIAL
- SKIPPED
- BLOCKED

A PASS result must only be emitted after all required assertions succeed.

## Evidence Rules

Evidence must:

- use UTC timestamps
- identify the runbook
- include an execution ID
- include the final exit code
- preserve raw diagnostic output where relevant
- avoid exposing passwords, tokens, private keys, or credentials
- clearly identify superseded or invalid evidence

## Concurrency

Scheduled runbooks must prevent overlapping execution.

The default concurrency mechanism is an exclusive file lock.

Lock contention must return exit code 80 and must not be reported as PASS.

## Timeout

Every scheduled runbook must define a maximum execution duration.

Timeout must return exit code 90 and produce failure evidence when possible.

## Failure Handling

Runbooks must:

- use fail-closed assertions
- avoid unconditional PASS messages
- preserve diagnostic context
- clean temporary files where safe
- avoid modifying unrelated runtime state
- leave service recovery to an explicitly authorized recovery runbook

## Dependency Model

StorageOps API depends on the ONTAP source.

Prometheus and Grafana are observability consumers and are not runtime
dependencies of StorageOps API.

Failure of Prometheus or Grafana must not cause StorageOps API shutdown.

## Scheduling

Scheduled operations must use project-owned systemd service and timer units.

Timers must be independently enabled, disabled, and inspected.

## Auditability

Every runbook execution must be traceable through:

- systemd journal or operator terminal output
- evidence file
- execution ID
- runbook version
- Git commit when available

## Initial Authorized Runbooks

The following runbooks are authorized in NETAPP-M5:

- runtime status
- API health
- ONTAP dependency health
- inventory collection
- capacity inspection
- Prometheus target inspection
- StorageOps alert inspection
- final operational verification
