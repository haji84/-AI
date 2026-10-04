from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.legal_structure import PARSER_VERSION, parse_legal_document
from app.models import (
    Document,
    LegalProvision,
    LegalSourceDocumentVersion,
    LegalUpdateCandidate,
)
from app.settings import settings


def _structure_version(db, version: LegalSourceDocumentVersion) -> dict:
    if not version.raw_document_id:
        version.structure_status = "skipped_no_original"
        version.structure_parser_version = PARSER_VERSION
        version.structured_at = datetime.now(timezone.utc)
        return {"version_id": version.legal_source_document_version_id, "status": version.structure_status, "count": 0}

    raw = db.get(Document, version.raw_document_id)
    if not raw:
        version.structure_status = "error_missing_original"
        version.structure_parser_version = PARSER_VERSION
        version.structured_at = datetime.now(timezone.utc)
        return {"version_id": version.legal_source_document_version_id, "status": version.structure_status, "count": 0}

    path = (Path(settings.storage_root).resolve() / raw.storage_path).resolve()
    root = Path(settings.storage_root).resolve()
    if root not in path.parents and path != root:
        raise RuntimeError("original file path escapes managed storage")
    data = path.read_bytes()

    parsed = parse_legal_document(data, raw.mime_type, raw.original_filename)
    current = {
        x.provision_key: x
        for x in db.scalars(
            select(LegalProvision).where(
                LegalProvision.legal_source_document_version_id == version.legal_source_document_version_id
            )
        ).all()
    }

    for row in current.values():
        row.present_in_source = False

    key_to_row: dict[str, LegalProvision] = {}
    inserted = 0
    updated = 0

    # First pass creates/updates without parent relation so forward references cannot break.
    for item in parsed:
        row = current.get(item.provision_key)
        if row is None:
            row = LegalProvision(
                legal_source_document_version_id=version.legal_source_document_version_id,
                provision_key=item.provision_key,
                provision_type=item.provision_type,
                sequence_no=item.sequence_no,
                display_label=item.display_label,
                heading_text=item.heading_text,
                body_text=item.body_text,
                source_anchor=item.source_anchor,
                source_path=item.source_path,
                source_meta=item.source_meta,
                content_sha256=item.content_sha256,
                present_in_source=True,
            )
            db.add(row)
            db.flush()
            inserted += 1
        else:
            row.provision_type = item.provision_type
            row.sequence_no = item.sequence_no
            row.display_label = item.display_label
            row.heading_text = item.heading_text
            row.body_text = item.body_text
            row.source_anchor = item.source_anchor
            row.source_path = item.source_path
            row.source_meta = item.source_meta
            row.content_sha256 = item.content_sha256
            row.present_in_source = True
            updated += 1
        key_to_row[item.provision_key] = row

    # Second pass links parents using stable provision keys.
    for item in parsed:
        row = key_to_row[item.provision_key]
        row.parent_provision_id = (
            key_to_row[item.parent_key].legal_provision_id
            if item.parent_key and item.parent_key in key_to_row
            else None
        )

    version.structure_status = "structured" if parsed else "structured_empty"
    version.structure_parser_version = PARSER_VERSION
    version.provision_count = len(parsed)
    version.structured_at = datetime.now(timezone.utc)

    diff = {"added": [], "removed": [], "changed": [], "unchanged": []}
    if version.previous_version_id:
        prev_rows = {
            x.provision_key: x
            for x in db.scalars(
                select(LegalProvision).where(
                    LegalProvision.legal_source_document_version_id == version.previous_version_id,
                    LegalProvision.present_in_source.is_(True),
                )
            ).all()
        }
        now_rows = {k: v for k, v in key_to_row.items() if v.present_in_source}
        for key in sorted(set(now_rows) | set(prev_rows)):
            a = prev_rows.get(key)
            b = now_rows.get(key)
            if a is None:
                diff["added"].append(key)
            elif b is None:
                diff["removed"].append(key)
            elif a.content_sha256 != b.content_sha256:
                diff["changed"].append(key)
            else:
                diff["unchanged"].append(key)

        candidate = db.scalar(
            select(LegalUpdateCandidate).where(
                LegalUpdateCandidate.legal_source_document_version_id == version.legal_source_document_version_id
            )
        )
        if candidate:
            candidate.diff_payload = {
                **(candidate.diff_payload or {}),
                "provision_diff": {
                    "added": diff["added"],
                    "removed": diff["removed"],
                    "changed": diff["changed"],
                    "unchanged_count": len(diff["unchanged"]),
                    "parser_version": PARSER_VERSION,
                },
            }

    return {
        "version_id": version.legal_source_document_version_id,
        "status": version.structure_status,
        "count": len(parsed),
        "inserted": inserted,
        "updated": updated,
        "diff": {
            "added": len(diff["added"]),
            "removed": len(diff["removed"]),
            "changed": len(diff["changed"]),
            "unchanged": len(diff["unchanged"]),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Structure stored national/local legal originals into article/paragraph/item provisions.")
    p.add_argument("--version-id")
    p.add_argument("--source-document-id")
    p.add_argument("--only-unparsed", action="store_true")
    p.add_argument("--limit", type=int)
    args = p.parse_args()

    with SessionLocal() as db:
        stmt = select(LegalSourceDocumentVersion).order_by(LegalSourceDocumentVersion.retrieved_at)
        if args.version_id:
            stmt = stmt.where(LegalSourceDocumentVersion.legal_source_document_version_id == args.version_id)
        if args.source_document_id:
            stmt = stmt.where(LegalSourceDocumentVersion.legal_source_document_id == args.source_document_id)
        if args.only_unparsed:
            stmt = stmt.where(LegalSourceDocumentVersion.structure_status == "unparsed")
        if args.limit:
            stmt = stmt.limit(max(1, args.limit))
        versions = db.scalars(stmt).all()

        results = []
        failures = []
        for version in versions:
            try:
                results.append(_structure_version(db, version))
                db.commit()
            except Exception as exc:
                db.rollback()
                failures.append({
                    "version_id": version.legal_source_document_version_id,
                    "error": type(exc).__name__,
                    "message": str(exc)[:500],
                })

    print(json.dumps({
        "processed": len(results),
        "failures": len(failures),
        "parser_version": PARSER_VERSION,
        "results": results,
        "failure_details": failures,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
