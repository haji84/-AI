from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
)


WORKLIST_IMPORT_VERSION = "core-authoring-worklist-import-v1"
KNOWN_REVIEW_CATEGORIES = {
    "equipment_requirement",
    "equipment_placement",
    "submission_requirement",
    "fire_management",
    "inspection_enforcement",
    "hazardous_materials",
    "fire_prevention_local",
}


@dataclass
class WorklistImportStats:
    items_seen: int = 0
    category_rows_seen: int = 0
    inserted: int = 0
    updated_pending: int = 0
    unchanged: int = 0
    skipped_terminal: int = 0
    missing_document: int = 0
    missing_provision: int = 0
    stale_hash: int = 0
    invalid_category: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def worklist_external_id(item: dict) -> str:
    scope = item.get("scope")
    source_ref = str(item.get("source_ref") or "")
    if scope == "national":
        head = source_ref.split("/", 1)[0]
        return head.split("_", 1)[0]
    if scope == "oshima_fire_union":
        return source_ref
    return source_ref


def _resolve_provision(db: Session, item: dict) -> tuple[str, LegalProvision | None]:
    external_id = worklist_external_id(item)
    doc = db.scalar(
        select(LegalSourceDocument).where(
            LegalSourceDocument.external_id == external_id
        )
    )
    if doc is None:
        return "missing_document", None

    provision = db.scalar(
        select(LegalProvision)
        .join(
            LegalSourceDocumentVersion,
            LegalSourceDocumentVersion.legal_source_document_version_id
            == LegalProvision.legal_source_document_version_id,
        )
        .where(
            LegalSourceDocumentVersion.legal_source_document_id
            == doc.legal_source_document_id,
            LegalProvision.provision_key == item.get("provision_key"),
            LegalProvision.present_in_source.is_(True),
        )
        .order_by(LegalSourceDocumentVersion.retrieved_at.desc())
    )
    if provision is None:
        return "missing_provision", None

    expected_hash = item.get("provision_content_sha256")
    if not expected_hash or provision.content_sha256 != expected_hash:
        return "stale_hash", provision

    if item.get("document_title") and doc.title != item.get("document_title"):
        # Same external ID with a changed title is evidence the worklist should be rebuilt.
        return "stale_hash", provision

    return "ok", provision


def import_worklist(
    db: Session,
    items: Iterable[dict],
    *,
    allowed_categories: set[str] | None = None,
    apply: bool = False,
) -> WorklistImportStats:
    stats = WorklistImportStats()
    allowed = allowed_categories or KNOWN_REVIEW_CATEGORIES

    for item in items:
        stats.items_seen += 1
        resolution, provision = _resolve_provision(db, item)
        if resolution != "ok":
            setattr(stats, resolution, getattr(stats, resolution) + 1)
            continue
        assert provision is not None

        for hit in item.get("hits") or []:
            category = hit.get("category")
            if category not in KNOWN_REVIEW_CATEGORIES or category not in allowed:
                stats.invalid_category += 1
                continue
            stats.category_rows_seen += 1

            reasons = [
                {
                    "scanner_version": WORKLIST_IMPORT_VERSION,
                    "match": reason,
                    "source": "verified_core_authoring_worklist",
                }
                for reason in (hit.get("reasons") or [])
            ]
            existing = db.scalar(
                select(LegalProvisionReviewCandidate).where(
                    LegalProvisionReviewCandidate.legal_provision_id
                    == provision.legal_provision_id,
                    LegalProvisionReviewCandidate.category == category,
                )
            )
            if existing is None:
                if apply:
                    db.add(
                        LegalProvisionReviewCandidate(
                            legal_provision_id=provision.legal_provision_id,
                            category=category,
                            relevance_score=float(hit.get("score") or 0),
                            priority_lane=str(item.get("priority_lane") or "normal"),
                            source_priority_score=float(item.get("source_priority_score") or 0),
                            provision_context=str(item.get("provision_context") or "main"),
                            context_priority_score=float(item.get("context_priority_score") or 0),
                            reasons=reasons,
                            extraction_method="deterministic",
                            model_version=WORKLIST_IMPORT_VERSION,
                        )
                    )
                stats.inserted += 1
                continue

            if existing.status != "pending":
                stats.skipped_terminal += 1
                continue

            same = (
                existing.relevance_score == float(hit.get("score") or 0)
                and existing.priority_lane == str(item.get("priority_lane") or "normal")
                and existing.source_priority_score == float(item.get("source_priority_score") or 0)
                and existing.provision_context == str(item.get("provision_context") or "main")
                and existing.context_priority_score == float(item.get("context_priority_score") or 0)
                and existing.reasons == reasons
                and existing.model_version == WORKLIST_IMPORT_VERSION
            )
            if same:
                stats.unchanged += 1
                continue

            if apply:
                existing.relevance_score = float(hit.get("score") or 0)
                existing.priority_lane = str(item.get("priority_lane") or "normal")
                existing.source_priority_score = float(item.get("source_priority_score") or 0)
                existing.provision_context = str(item.get("provision_context") or "main")
                existing.context_priority_score = float(item.get("context_priority_score") or 0)
                existing.reasons = reasons
                existing.extraction_method = "deterministic"
                existing.model_version = WORKLIST_IMPORT_VERSION
            stats.updated_pending += 1

    if apply:
        db.flush()
    return stats
