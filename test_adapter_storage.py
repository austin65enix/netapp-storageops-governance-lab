from adapters.ontap_adapter import OntapAdapter


adapter = OntapAdapter(
    "http://localhost:8000"
)


print("=== VOLUMES ===")

for v in adapter.list_volumes():
    print(v.name, v.utilization_percent)


print("\n=== LUNS ===")

for l in adapter.list_luns():
    print(l.name, l.os_type)


print("\n=== SNAPSHOTS ===")

for s in adapter.list_snapshots():
    print(s.name)


print("\n=== CAPACITY ===")

print(adapter.get_capacity())
