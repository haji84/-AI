from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_structure import PARSER_VERSION, parse_legal_document
from .models import (
    Document,
    LegalProvision,
    LegalRuleCitation,
    LegalRuleVersion,
    LegalSourceDocumentVersion,
    LegalUpdateCandidate,
)
from .settings import settings


def structure_legal_version(
    db: Session,
    version: LegalSourceDocumentVersion,
) -> dict:
    if not version.raw_document_id:
        version.structure_status = "skipped_no_original"
        version.structure_parser_version = PARSER_VERSION
        version.structured_at = datetime.now(timezone.utc)
        return {
            "version_id": version.legal_source_document_version_id,
            "status": version.structure_status,
            "count": 0,
            "inserted": 0,
            "updated": 0,
            "diff": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
        }

    raw = db.get(Document, version.raw_document_id)
    if not raw:
        version.structure_status = "error_missing_original"
        version.structure_parser_version = PARSER_VERSION
        version.structured_at = datetime.now(timezone.utc)
        return {
            "version_id": version.legal_source_document_version_id,
            "status": version.structure_status,
            "count": 0,
            "inserted": 0,
            "updated": 0,
            "diff": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
        }

    root = Path(settings.storage_root).resolve()
    path = (root / raw.storage_path).resolve()
    if root not in path.parents and path != root:
        raise RuntimeError("original file path escapes managed storage")
    if not path.exists():
        version.structure_status = "error_missing_original_file"
        version.structure_parser_version = PARSER_VERSION
        version.structured_at = datetime.now(timezone.utc)
        return {
            "version_id": version.legal_source_document_version_id,
            "status": version.structure_status,
            "count": 0,
            "inserted": 0,
            "updated": 0,
            "diff": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
        }

    data = path.read_bytes()
    parsed = parse_legal_document(data, raw.mime_type, raw.original_filename)

    current = {
        x.provision_key: x
        for x in db.scalars(
            select(LegalProvision).where(
                LegalProvision.legal_source_document_version_id
                == version.legal_source_document_version_id
            )
        ).all()
    }

    for row in current.values():
        row.present_in_source = False

    key_to_row: dict[str, LegalProvision] = {}
    inserted = 0
    updated = 0

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
                    LegalProvision.legal_source_document_version_id
                    == version.previous_version_id,
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

        impacted_rule_ids: set[str] = set()
        impacted_rule_version_ids: set[str] = set()
        impacted_keys = set(diff["removed"]) | set(diff["changed"])
        if impacted_keys:
            previous_by_key = {x.provision_key: x for x in prev_rows.values()}
            impacted_provision_ids = [
                previous_by_key[key].legal_provision_id
                for key in impacted_keys
                if key in previous_by_key
            ]
            if impacted_provision_ids:
                citations = db.scalars(
                    select(LegalRuleCitation).where(
                        LegalRuleCitation.legal_provision_id.in_(impacted_provision_ids)
                    )
                ).all()
                for citation in citations:
                    impacted_rule_version_ids.add(citation.legal_rule_version_id)
                    rv = db.get(LegalRuleVersion, citation.legal_rule_version_id)
                    if rv:
                        impacted_rule_ids.add(rv.rule_id)

        candidate = db.scalar(
            select(LegalUpdateCandidate).where(
                LegalUpdateCandidate.legal_source_document_version_id
                == version.legal_source_document_version_id
            )
        )
        if candidate:
            candidate.impacted_rule_ids = sorted(impacted_rule_ids)
            candidate.diff_payload = {
                **(candidate.diff_payload or {}),
                "provision_diff": {
                    "added": diff["added"],
                    "removed": diff["removed"],
                    "changed": diff["changed"],
                    "unchanged_count": len(diff["unchanged"]),
                    "parser_version": PARSER_VERSION,
                    "impacted_rule_ids": sorted(impacted_rule_ids),
                    "impacted_rule_version_ids": sorted(impacted_rule_version_ids),
                },
            }

    return {
        "version_id": version.legal_source_document_version_id,
        "status": version.structure_status,
        "parser_version": PARSER_VERSION,
        "count": len(parsed),
        "inserted": inserted,
        "updated": updated,
        "table_row_count": sum(1 for item in parsed if item.provision_type == "table_row"),
        "diff": {
            "added": len(diff["added"]),
            "removed": len(diff["removed"]),
            "changed": len(diff["changed"]),
            "unchanged": len(diff["unchanged"]),
        },
    }
