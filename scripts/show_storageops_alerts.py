import json
import sys
from urllib.request import urlopen

URL = "http://127.0.0.1:9090/api/v1/alerts"

with urlopen(URL, timeout=5) as response:
    payload = json.load(response)

if payload.get("status") != "success":
    raise SystemExit("Prometheus alert API failed")

alerts = payload["data"]["alerts"]

storageops_alerts = [
    alert
    for alert in alerts
    if alert.get("labels", {}).get("service")
    == "storageops-api"
]

for alert in storageops_alerts:
    labels = alert.get("labels", {})

    print(
        "ALERT="
        + labels.get("alertname", "")
        + " STATE="
        + alert.get("state", "")
        + " SEVERITY="
        + labels.get("severity", "")
    )

print(
    "STORAGEOPS_ALERT_COUNT="
    + str(len(storageops_alerts))
)
