# StorageOps Scheduled Collection Contract

## Status

Accepted

## Scope

This contract defines scheduled inventory collection through systemd.

Scheduled execution does not authorize ONTAP resource mutation.

## Service

The service unit name is `storageops-collect.service`.

The service must:

- use `Type=oneshot`
- execute as user `atn`
- use `/opt/netapp-storageops-lab` as `WorkingDirectory`
- execute `scripts/storageops-ops collect`
- use the default runtime evidence directory
- use `/run/lock/storageops-collect.lock`
- preserve CLI exit codes
- write output to the systemd journal
- not use `--no-evidence`
- not restart automatically

## Timer

The timer unit name is `storageops-collect.timer`.

The timer must:

- trigger `storageops-collect.service`
- persist missed executions across reboot
- avoid sub-minute scheduling
- use randomized delay only when explicitly configured
- remain independently disableable

## Failure Behavior

Scheduled execution must remain fail-closed.

Expected CLI exit codes include:

- `0` successful collection
- `30` endpoint unavailable
- `40` collection validation failure
- `70` evidence write failure
- `80` lock contention
- `90` timeout
- `100` unexpected failure

## Evidence

Every scheduled execution must produce CLI-owned JSON evidence unless
evidence writing itself fails.

The default evidence directory is:

`/opt/netapp-storageops-lab/evidence/runtime`

## Safety Boundary

Scheduled collection must not:

- modify ONTAP storage resources
- restart StorageOps services
- retry resource mutation
- delete inventory snapshots
- suppress lock contention
- suppress non-zero exit codes
