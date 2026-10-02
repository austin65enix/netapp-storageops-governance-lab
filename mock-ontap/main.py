from fastapi import FastAPI
import json
from pathlib import Path

app = FastAPI(
    title="Mock ONTAP REST API",
    version="0.1"
)


BASE = Path(__file__).parent.parent


@app.get("/api/cluster")
def get_cluster():

    with open(
        BASE / "fixtures/netapp/cluster.json"
    ) as f:
        return json.load(f)


@app.get("/api/svms")
def get_svms():

    with open(
        BASE / "fixtures/netapp/svms.json"
    ) as f:
        return json.load(f)

@app.get("/api/storage/volumes")
def get_volumes():

    with open(
        BASE / "fixtures/netapp/volumes.json"
    ) as f:
        return json.load(f)


@app.get("/api/storage/luns")
def get_luns():

    with open(
        BASE / "fixtures/netapp/luns.json"
    ) as f:
        return json.load(f)


@app.get("/api/storage/snapshots")
def get_snapshots():

    with open(
        BASE / "fixtures/netapp/snapshots.json"
    ) as f:
        return json.load(f)


@app.get("/api/storage/capacity")
def get_capacity():

    with open(
        BASE / "fixtures/netapp/capacity.json"
    ) as f:
        return json.load(f)
