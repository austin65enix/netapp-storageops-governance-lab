from dataclasses import dataclass


@dataclass
class InventoryCountChange:
    resource_type: str
    before_count: int
    after_count: int
    delta: int
    change_type: str


class InventoryDiffEngine:

    def compare(
        self,
        before: dict,
        after: dict
    ) -> list[InventoryCountChange]:

        before_resources = before.get("resources", {})
        after_resources = after.get("resources", {})

        resource_types = sorted(
            set(before_resources)
            | set(after_resources)
        )

        changes = []

        for resource_type in resource_types:

            before_count = (
                before_resources
                .get(resource_type, {})
                .get("resource_count", 0)
            )

            after_count = (
                after_resources
                .get(resource_type, {})
                .get("resource_count", 0)
            )

            delta = after_count - before_count

            if delta > 0:
                change_type = "ADDED"
            elif delta < 0:
                change_type = "REMOVED"
            else:
                change_type = "UNCHANGED"

            changes.append(
                InventoryCountChange(
                    resource_type=resource_type,
                    before_count=before_count,
                    after_count=after_count,
                    delta=delta,
                    change_type=change_type
                )
            )

        return changes
