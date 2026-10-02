import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

if len(sys.argv) != 2:
    raise SystemExit(
        "usage: query_prometheus.py '<promql>'"
    )

query = sys.argv[1]

url = (
    "http://127.0.0.1:9090/api/v1/query?"
    + urlencode({"query": query})
)

with urlopen(url, timeout=5) as response:
    payload = json.load(response)

if payload.get("status") != "success":
    raise SystemExit("Prometheus query failed")

result = payload["data"]["result"]

print("QUERY=" + query)
print("RESULT_COUNT=" + str(len(result)))

for item in result:
    labels = item.get("metric", {})
    value = item.get("value", [None, None])[1]

    print(
        "VALUE="
        + str(value)
        + " LABELS="
        + json.dumps(
            labels,
            sort_keys=True,
        )
    )
