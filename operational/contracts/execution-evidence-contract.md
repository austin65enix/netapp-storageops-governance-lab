# StorageOps Execution and Evidence Contract

## Status

Accepted

## Scope

This contract defines execution identity, evidence output, and concurrency
control for authorized StorageOps operational commands.

The contract does not authorize ONTAP storage resource mutation.

## Applicable Commands

- collect
- verify

The initial implementation applies evidence generation and locking to
`collect` only.

## Execution ID

Every evidence-producing execution must have one execution ID.

The execution ID format is:

```text
<command>-<UTC timestamp>-<random suffix>
```

Example:

```text
collect-20260804T081500Z-a1b2c3d4
```

Execution IDs must:

- identify the executed command
- contain a UTC timestamp
- contain a collision-resistant random suffix
- contain only letters, numbers, and hyphens
- remain stable for the complete execution

## Evidence File Name

The default evidence file name is:

```text
<execution-id>.json
```

## Default Evidence Directory

```text
evidence/m5/runtime
```

The directory may be overridden using `--evidence-dir`.

## Evidence Document

Evidence must be valid UTF-8 JSON.

Required fields:

- schema_version
- execution_id
- command
- started_at
- completed_at
- result
- exit_code
- data
- errors
- evidence_file

## Schema Version

The initial evidence schema version is:

```text
1
```

## Write Behavior

Evidence must be written atomically.

The implementation must:

- create the destination directory when authorized
- write to a temporary file in the destination directory
- flush and close the temporary file
- atomically replace the final evidence file
- avoid reporting PASS when evidence writing fails

Evidence write failure must return exit code 70.

## Manual Evidence Suppression

`--no-evidence` may suppress CLI-owned evidence only for explicitly manual
execution.

The underlying StorageOps inventory snapshot is not suppressed.

Scheduled executions must not use `--no-evidence`.

## Concurrency Lock

Evidence-producing collection must use a non-blocking exclusive lock.

The default lock file is:

```text
/run/lock/storageops-collect.lock
```

When another collection owns the lock:

- no second collection request may be sent
- no PASS result may be emitted
- exit code 80 must be returned
- failure evidence should be written when possible

## Timeout

A collection timeout must return exit code 90.

## Safety Boundary

Execution evidence and locking must not:

- alter ONTAP resources
- restart services
- retry resource mutation
- delete existing inventory snapshots
- overwrite evidence from another execution
