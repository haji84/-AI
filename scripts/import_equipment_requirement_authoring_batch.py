from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.equipment_authoring_batch import import_equipment_requirement_batch


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import a verified core legal worklist into the equipment-requirement "
            "Human review queue and bind it to an immutable authoring batch."
        )
    )
    parser.add_argument("--worklist", required=True)
    parser.add_argument("--source-metadata")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.worklist).resolve()
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("worklist must be a JSON array")

    source_metadata = {}
    if args.source_metadata:
        source_metadata = json.loads(
            Path(args.source_metadata).resolve().read_text(encoding="utf-8")
        )
        if not isinstance(source_metadata, dict):
            raise SystemExit("source metadata must be a JSON object")

    with SessionLocal() as db:
        result = import_equipment_requirement_batch(
            db,
            items=items,
            source_metadata={
                **source_metadata,
                "worklist_path": str(path),
            },
            apply=args.apply,
        )
        if args.apply and result.get("applied"):
            db.commit()
        else:
            db.rollback()

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
