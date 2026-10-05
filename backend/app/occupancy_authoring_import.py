from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_structure import PARSER_VERSION
from .models import (
    LegalProvision,
    LegalRuleDraftCandidate,
    LegalRuleDraftCitation,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
)


IMPORT_VERSION = "occupancy-authoring-import-v1"
CATALOG_FORMAT = "fire-ai-occupancy-classification-catalog-v1"
TARGET_LAW_TITLE = "消防法施行令"
TARGET_LAW_EXTERNAL_ID = "336CO0000000037"


@dataclass
class OccupancyImportStats:
    entries_seen: int = 0
    inserted: int = 0
    unchanged: int = 0
    skipped_terminal: int = 0
    invalid_entry: int = 0
    missing_source_document: int = 0
    missing_source_version: int = 0
    parser_upgrade_required: int = 0
    missing_provision: int = 0
    stale_provision: int = 0
    resolved_source_version_id: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _canonical_sha(value: dict) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _resolve_source_version(
    db: Session,
    *,
    source_sha256: str,
) -> tuple[str, LegalSourceDocumentVersion | None]:
    docs = db.scalars(
        select(LegalSourceDocument).where(
            LegalSourceDocument.external_id == TARGET_LAW_EXTERNAL_ID,
            LegalSourceDocument.title == TARGET_LAW_TITLE,
        )
    ).all()
    if not docs:
        return "missing_source_document", None

    versions = db.scalars(
        select(LegalSourceDocumentVersion)
        .where(
            LegalSourceDocumentVersion.legal_source_document_id.in_(
                [x.legal_source_document_id for x in docs]
            ),
            LegalSourceDocumentVersion.sha256 == source_sha256,
        )
        .order_by(LegalSourceDocumentVersion.retrieved_at.desc())
    ).all()
    if not versions:
        return "missing_source_version", None

    version = versions[0]
    if (
        version.structure_status != "structured"
        or version.structure_parser_version != PARSER_VERSION
    ):
        return "parser_upgrade_required", version
    return "ok", version


def _valid_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    required = (
        "classification_code",
        "classification_label",
        "official_text",
        "row_provision_key",
        "entry_sha256",
        "proposed_rule_code",
        "proposed_name",
        "proposed_outcome",
    )
    if any(not entry.get(x) for x in required):
        return False
    outcome = entry.get("proposed_outcome")
    if not isinstance(outcome, dict):
        return False
    return (
        outcome.get("decision") == "classification_candidate"
        and outcome.get("classification_code") == entry.get("classification_code")
        and outcome.get("classification_label") == entry.get("classification_label")
    )


def import_occupancy_catalog(
    db: Session,
    catalog: dict,
    *,
    apply: bool = False,
    created_by: str | None = None,
) -> OccupancyImportStats:
    if not isinstance(catalog, dict) or catalog.get("format") != CATALOG_FORMAT:
        raise ValueError("unsupported occupancy catalog format")
    if catalog.get("law_title") != TARGET_LAW_TITLE:
        raise ValueError("occupancy catalog is not for 消防法施行令")

    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise ValueError("occupancy catalog entries must be a list")
    if int(catalog.get("classification_entry_count", -1)) != len(entries):
        raise ValueError("occupancy catalog entry count mismatch")

    source_sha = str(catalog.get("source_xml_sha256") or "")
    if len(source_sha) != 64:
        raise ValueError("invalid source_xml_sha256")

    stats = OccupancyImportStats()
    resolution, source_version = _resolve_source_version(
        db,
        source_sha256=source_sha,
    )
    if resolution != "ok":
        setattr(stats, resolution, getattr(stats, resolution) + 1)
        if source_version is not None:
            stats.resolved_source_version_id = (
                source_version.legal_source_document_version_id
            )
        return stats

    assert source_version is not None
    stats.resolved_source_version_id = source_version.legal_source_document_version_id

    for entry in entries:
        stats.entries_seen += 1
        if not _valid_entry(entry):
            stats.invalid_entry += 1
            continue

        provision = db.scalar(
            select(LegalProvision).where(
                LegalProvision.legal_source_document_version_id
                == source_version.legal_source_document_version_id,
                LegalProvision.provision_key == entry["row_provision_key"],
                LegalProvision.present_in_source.is_(True),
            )
        )
        if provision is None:
            stats.missing_provision += 1
            continue
        if provision.provision_type != "table_row":
            stats.stale_provision += 1
            continue
        if str(entry["official_text"]) not in (provision.body_text or ""):
            stats.stale_provision += 1
            continue

        fingerprint = _canonical_sha(
            {
                "import_version": IMPORT_VERSION,
                "source_version_id": source_version.legal_source_document_version_id,
                "entry_sha256": entry["entry_sha256"],
                "row_provision_key": entry["row_provision_key"],
                "proposed_rule_code": entry["proposed_rule_code"],
            }
        )
        existing = db.scalar(
            select(LegalRuleDraftCandidate).where(
                LegalRuleDraftCandidate.candidate_fingerprint == fingerprint
            )
        )
        if existing is not None:
            if existing.status == "pending":
                stats.unchanged += 1
            else:
                stats.skipped_terminal += 1
            continue

        stats.inserted += 1
        if not apply:
            continue

        row = LegalRuleDraftCandidate(
            source_legal_document_version_id=source_version.legal_source_document_version_id,
            domain="occupancy_classification",
            proposed_rule_code=str(entry["proposed_rule_code"]),
            proposed_name=str(entry["proposed_name"]),
            proposed_conditions={},
            proposed_outcome=dict(entry["proposed_outcome"]),
            extraction_method="deterministic",
            model_version=IMPORT_VERSION,
            confidence=None,
            rationale=(
                "Official Schedule 1 classification identity imported from the "
                "verified e-Gov catalog. Applicability conditions require Human legal authoring."
            ),
            candidate_fingerprint=fingerprint,
            generation_context={
                "import_version": IMPORT_VERSION,
                "catalog_format": CATALOG_FORMAT,
                "source_xml_sha256": source_sha,
                "classification_code": entry["classification_code"],
                "classification_label": entry["classification_label"],
                "entry_sha256": entry["entry_sha256"],
                "row_provision_key": entry["row_provision_key"],
                "conditions_authoring_status": "required",
                "catalog_entry_count": len(entries),
            },
            created_by=created_by,
        )
        db.add(row)
        db.flush()
        db.add(
            LegalRuleDraftCitation(
                legal_rule_draft_candidate_id=row.legal_rule_draft_candidate_id,
                legal_provision_id=provision.legal_provision_id,
                citation_role="primary",
            )
        )

    if apply:
        db.flush()
    return stats



def check_occupancy_catalog_readiness(
    db: Session,
    catalog: dict,
) -> dict:
    if not isinstance(catalog, dict) or catalog.get("format") != CATALOG_FORMAT:
        raise ValueError("unsupported occupancy catalog format")
    if catalog.get("law_title") != TARGET_LAW_TITLE:
        raise ValueError("occupancy catalog is not for 消防法施行令")

    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise ValueError("occupancy catalog entries must be a list")
    if int(catalog.get("classification_entry_count", -1)) != len(entries):
        raise ValueError("occupancy catalog entry count mismatch")

    source_sha = str(catalog.get("source_xml_sha256") or "")
    if len(source_sha) != 64:
        raise ValueError("invalid source_xml_sha256")

    resolution, source_version = _resolve_source_version(
        db,
        source_sha256=source_sha,
    )

    result = {
        "ready": False,
        "resolution": resolution,
        "source_xml_sha256": source_sha,
        "source_version_id": None,
        "source_structure_status": None,
        "source_structure_parser_version": None,
        "expected_parser_version": PARSER_VERSION,
        "catalog_entry_count": len(entries),
        "valid_entry_count": 0,
        "exact_provision_match_count": 0,
        "missing_provision_count": 0,
        "stale_provision_count": 0,
        "existing_pending_skeleton_count": 0,
        "existing_terminal_skeleton_count": 0,
        "would_insert_count": 0,
        "blockers": [],
    }

    if source_version is None:
        result["blockers"].append(resolution)
        return result

    result["source_version_id"] = source_version.legal_source_document_version_id
    result["source_structure_status"] = source_version.structure_status
    result["source_structure_parser_version"] = source_version.structure_parser_version

    if resolution != "ok":
        result["blockers"].append(resolution)
        return result

    for entry in entries:
        if not _valid_entry(entry):
            result["blockers"].append(
                {
                    "type": "invalid_entry",
                    "classification_code": (
                        entry.get("classification_code")
                        if isinstance(entry, dict)
                        else None
                    ),
                }
            )
            continue

        result["valid_entry_count"] += 1
        provision = db.scalar(
            select(LegalProvision).where(
                LegalProvision.legal_source_document_version_id
                == source_version.legal_source_document_version_id,
                LegalProvision.provision_key == entry["row_provision_key"],
                LegalProvision.present_in_source.is_(True),
            )
        )
        if provision is None:
            result["missing_provision_count"] += 1
            result["blockers"].append(
                {
                    "type": "missing_provision",
                    "classification_code": entry["classification_code"],
                    "row_provision_key": entry["row_provision_key"],
                }
            )
            continue

        if (
            provision.provision_type != "table_row"
            or str(entry["official_text"]) not in (provision.body_text or "")
        ):
            result["stale_provision_count"] += 1
            result["blockers"].append(
                {
                    "type": "stale_provision",
                    "classification_code": entry["classification_code"],
                    "row_provision_key": entry["row_provision_key"],
                }
            )
            continue

        result["exact_provision_match_count"] += 1
        fingerprint = _canonical_sha(
            {
                "import_version": IMPORT_VERSION,
                "source_version_id": source_version.legal_source_document_version_id,
                "entry_sha256": entry["entry_sha256"],
                "row_provision_key": entry["row_provision_key"],
                "proposed_rule_code": entry["proposed_rule_code"],
            }
        )
        existing = db.scalar(
            select(LegalRuleDraftCandidate).where(
                LegalRuleDraftCandidate.candidate_fingerprint == fingerprint
            )
        )
        if existing is None:
            result["would_insert_count"] += 1
        elif existing.status == "pending":
            result["existing_pending_skeleton_count"] += 1
        else:
            result["existing_terminal_skeleton_count"] += 1

    result["ready"] = (
        not result["blockers"]
        and result["valid_entry_count"] == len(entries)
        and result["exact_provision_match_count"] == len(entries)
    )
    return result
