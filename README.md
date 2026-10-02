# NetApp StorageOps Lab

Governed storage operations, automation, observability and execution-evidence lab.

This repository demonstrates a synthetic NetApp ONTAP operations environment
that combines infrastructure automation with explicit operational governance.

The public edition contains no production credentials, customer data,
production storage inventories, private infrastructure addresses or raw
historical runtime evidence.

## What this project demonstrates

The lab covers:

- synthetic NetApp ONTAP inventory collection
- volume, LUN and snapshot models
- inventory comparison and change detection
- REST API boundaries
- operational summaries
- Prometheus-compatible metrics
- Grafana-oriented observability assets
- scheduled collection workflows
- dependency failure handling
- lock contention handling
- evidence-write failure handling
- failure recovery
- execution authorization
- admission control
- authority consumption
- execution evidence binding

## Governance flow

The operational governance model follows this sequence:

    Request
      |
      v
    Decision
      |
      v
    Authorization
      |
      v
    Admission
      |
      v
    Authority Consumption
      |
      v
    Execution
      |
      v
    Evidence
      |
      v
    Verification

The goal is not only to automate a storage operation, but to make the
authorization and resulting effect independently inspectable.

## Repository structure

    adapters/              ONTAP and operational adapters
    api/                   FastAPI application and routes
    diff_engine/           inventory comparison logic
    fixtures/              synthetic NetApp fixtures
    inventory/             inventory repository
    mock-ontap/            mock ONTAP service
    models/                storage and operational models
    observability/         metrics and dashboard assets
    operational/
      contracts/           operational and governance contracts
      runbooks/            controlled operational procedures
      systemd/             scheduled operation examples
    scripts/               operator and verification tools
    services/              application service boundaries
    tests/                 automated tests
    docs/                  architecture and runtime documentation

## Governance assets

Representative governance artifacts include:

    operational/contracts/authorization-admission.schema.json
    operational/contracts/decision-enforcement.schema.json
    operational/contracts/execution-authority-material.schema.json
    operational/contracts/execution-evidence-binding.schema.json
    operational/contracts/execution-evidence-binding-v2.schema.json
    operational/contracts/admission-consumption-claim.schema.json

Supporting validation logic includes:

    scripts/check_governance_admission.py
    scripts/validate_execution_authority_claim.py
    scripts/validate_governance_lineage.py
    scripts/validate_governance_lineage_v2.py

## Public runtime profile

The canonical example runtime root is:

    /opt/netapp-storageops-lab

This location is illustrative and is not tied to the original development
environment.

Historical raw evidence and runtime snapshots are intentionally excluded from
this public repository.

See:

    docs/public-runtime-profile.md
    SECURITY.md

## Local configuration

Copy the public environment template:

    cp .env.example .env

Then replace only the local synthetic test values required by your
environment.

Never commit real ONTAP credentials.

## Testing

Typical local validation:

    python3 -m compileall -q .
    python3 -m pytest -q

Some operational runbooks and systemd examples assume the public runtime path:

    /opt/netapp-storageops-lab

They are intended as controlled deployment examples rather than mandatory
requirements for running unit tests.

## Project background

This lab explores the transition from traditional infrastructure operations
toward governed automation:

    Observe
      -> Decide
      -> Authorize
      -> Execute
      -> Produce Evidence
      -> Verify

The storage domain provides a concrete environment for testing operational
authority boundaries, execution controls and evidence continuity.

## Safety boundary

This repository is intended for synthetic lab use.

Before connecting any component to a real storage system, independently review:

- credentials
- network boundaries
- authorization scope
- logging behavior
- change-control requirements
- evidence retention
- rollback procedures

See SECURITY.md for the public repository security boundary.
