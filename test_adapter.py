from adapters.ontap_adapter import OntapAdapter


adapter = OntapAdapter(
    "http://localhost:8000"
)


volumes = adapter.list_volumes()


for volume in volumes:

    print(volume)

    print(
        "UTILIZATION:",
        volume.utilization_percent,
        "%"
    )
