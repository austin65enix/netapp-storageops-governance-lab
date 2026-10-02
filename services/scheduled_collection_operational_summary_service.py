from typing import Protocol

from adapters.scheduled_collection_operational_summary_adapter import (
    ScheduledCollectionOperationalSummaryAdapter,
)
from models.operational_summary import ScheduledCollectionOperationalSummary


class ScheduledCollectionOperationalSummaryReader(Protocol):
    def read(self) -> ScheduledCollectionOperationalSummary: ...


def read_scheduled_collection_operational_summary(
    reader: ScheduledCollectionOperationalSummaryReader | None = None,
) -> ScheduledCollectionOperationalSummary:
    if reader is None:
        reader = ScheduledCollectionOperationalSummaryAdapter()
    return reader.read()
