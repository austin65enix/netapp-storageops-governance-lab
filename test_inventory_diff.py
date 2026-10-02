from diff_engine.inventory_diff import InventoryDiffEngine


before = {
    "collected_at": "2026-07-30T05:31:38",
    "resources": {
        "volume": {
            "resource_count": 3
        },
        "lun": {
            "resource_count": 2
        },
        "snapshot": {
            "resource_count": 3
        }
    }
}


after = {
    "collected_at": "2026-07-30T06:00:00",
    "resources": {
        "volume": {
            "resource_count": 4
        },
        "lun": {
            "resource_count": 2
        },
        "snapshot": {
            "resource_count": 2
        }
    }
}


engine = InventoryDiffEngine()

changes = engine.compare(
    before,
    after
)


for change in changes:
    print(change)
