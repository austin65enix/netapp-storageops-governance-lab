import json
from dataclasses import asdict
from pathlib import Path


class EvidenceRepository:

    def __init__(
        self,
        evidence_dir: str = "evidence/events"
    ):
        self.evidence_dir = Path(evidence_dir)

        self.evidence_dir.mkdir(
            parents=True,
            exist_ok=True
        )


    def save(
        self,
        records
    ):

        if not records:
            raise ValueError(
                "Evidence records cannot be empty."
            )

        filename = (
            self.evidence_dir
            / "storage_changes.json"
        )

        payload = [
            asdict(record)
            for record in records
        ]

        filename.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        return filename


    def load(self):

        filename = (
            self.evidence_dir
            / "storage_changes.json"
        )

        if not filename.exists():
            return []

        return json.loads(
            filename.read_text(
                encoding="utf-8"
            )
        )
