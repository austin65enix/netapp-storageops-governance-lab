# Public Runtime Profile

The public repository uses the following canonical example installation root:

    /opt/netapp-storageops-lab

This path is illustrative and is not tied to the original development host.

## Runtime directories

Example runtime layout:

    /opt/netapp-storageops-lab
    ├── evidence/
    │   └── runtime/
    ├── snapshots/
    │   └── runs/
    └── .venv/

Runtime evidence and snapshots are generated locally and are not distributed
as historical raw artifacts in the public repository.

## Data boundary

The public edition is intended for synthetic NetApp ONTAP operational
simulation, automation, governance and evidence-validation demonstrations.

It must not be connected to production storage without an independent review
of credentials, network boundaries, logging and operational authorization.
