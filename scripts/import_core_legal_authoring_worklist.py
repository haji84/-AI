from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.legal_authoring_import import KNOWN_REVIEW_CATEGORIES, import_worklist


def main() -> None:
    p = argparse.ArgumentParser(
        description="Import a verified, hash-bound legal authoring worklist into the Human review queue."
    )
    p.add_argument("--worklist", required=True)
    p.add_argument(
        "--categories",
        help="Comma-separated categories. Default: all known review categories.",
    )
    p.add_argument("--apply", action="store_true", help="Persist changes. Default is dry-run.")
    p.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail when any document/provision/hash mismatch is detected.",
    )
    args = p.parse_args()

    path = Path(args.worklist).resolve()
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("worklist must be a JSON array")

    categories = KNOWN_REVIEW_CATEGORIES
    if args.categories:
        categories = {x.strip() for x in args.categories.split(",") if x.strip()}
        unknown = categories - KNOWN_REVIEW_CATEGORIES
        if unknown:
            raise SystemExit(f"unknown categories: {sorted(unknown)}")

    with SessionLocal() as db:
        stats = import_worklist(
            db,
            items,
            allowed_categories=categories,
            apply=args.apply,
        )
        result = stats.as_dict()
        result.update(
            {
                "mode": "apply" if args.apply else "dry-run",
                "worklist": str(path),
                "categories": sorted(categories),
            }
        )

        mismatch_total = (
            stats.missing_document + stats.missing_provision + stats.stale_hash
        )
        if args.require_clean and mismatch_total:
            db.rollback()
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(2)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
