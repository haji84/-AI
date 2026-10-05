from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_authoring_import import (
    WORKLIST_IMPORT_VERSION,
    _resolve_provision,
    import_worklist,
)
from .models import (
    EquipmentPlacementAuthoringBatch,
    EquipmentPlacementBatchCandidate,
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalRuleCitation,
    LegalRuleDraftCandidate,
    LegalRuleVersion,
)


PLACEMENT_CATEGORY = "equipment_placement"
PLACEMENT_BATCH_IMPORT_VERSION = "equipment-placement-batch-v1"


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _placement_specs(items: list[dict]) -> list[dict]:
    specs = []
    seen = set()
    for item in items:
        for hit in item.get("hits") or []:
            if hit.get("category") != PLACEMENT_CATEGORY:
                continue
            key = (
                str(item.get("scope") or ""),
                str(item.get("source_ref") or ""),
                str(item.get("provision_key") or ""),
                str(item.get("provision_content_sha256") or ""),
                PLACEMENT_CATEGORY,
            )
            if key in seen:
                continue
            seen.add(key)
            specs.append({"item": item})
    return specs


def placement_worklist_batch_sha(items: list[dict]) -> str:
    normalized = []
    for spec in _placement_specs(items):
        item = spec["item"]
        normalized.append(
            {
                "scope": item.get("scope"),
                "document_title": item.get("document_title"),
                "source_ref": item.get("source_ref"),
                "provision_key": item.get("provision_key"),
                "provision_content_sha256": item.get("provision_content_sha256"),
                "placement_hits": [
                    {
                        "category": hit.get("category"),
                        "score": hit.get("score"),
                        "reasons": hit.get("reasons") or [],
                    }
                    for hit in (item.get("hits") or [])
                    if hit.get("category") == PLACEMENT_CATEGORY
                ],
            }
        )
    normalized.sort(
        key=lambda x: (
            str(x.get("scope") or ""),
            str(x.get("document_title") or ""),
            str(x.get("source_ref") or ""),
            str(x.get("provision_key") or ""),
        )
    )
    return _canonical_sha(normalized)


def import_equipment_placement_batch(
    db: Session,
    *,
    items: list[dict],
    source_metadata: dict | None = None,
    apply: bool = False,
    created_by: str | None = None,
) -> dict:
    if not isinstance(items, list):
        raise ValueError("worklist items must be a list")
    specs = _placement_specs(items)
    worklist_sha = placement_worklist_batch_sha(items)

    base_stats = import_worklist(
        db,
        items,
        allowed_categories={PLACEMENT_CATEGORY},
        apply=apply,
    )
    resolution_errors = (
        base_stats.missing_document
        + base_stats.missing_provision
        + base_stats.stale_hash
    )
    result = {
        "apply": apply,
        "worklist_sha256": worklist_sha,
        "worklist_item_count": len(items),
        "expected_candidate_count": len(specs),
        "base_import_stats": base_stats.as_dict(),
        "batch_created": False,
        "linked_candidate_count": 0,
        "resolution_error_count": resolution_errors,
        "ready_to_apply": resolution_errors == 0,
    }
    if not apply:
        return result
    if resolution_errors:
        db.rollback()
        result["applied"] = False
        return result

    batch = db.scalar(
        select(EquipmentPlacementAuthoringBatch).where(
            EquipmentPlacementAuthoringBatch.worklist_sha256 == worklist_sha
        )
    )
    if batch is None:
        batch = EquipmentPlacementAuthoringBatch(
            worklist_sha256=worklist_sha,
            worklist_item_count=len(items),
            expected_candidate_count=len(specs),
            import_version=PLACEMENT_BATCH_IMPORT_VERSION,
            source_metadata={
                **(source_metadata or {}),
                "base_import_version": WORKLIST_IMPORT_VERSION,
            },
            created_by=created_by,
        )
        db.add(batch)
        db.flush()
        result["batch_created"] = True
    else:
        if batch.expected_candidate_count != len(specs):
            raise ValueError("existing placement batch candidate count mismatch")
        if batch.worklist_item_count != len(items):
            raise ValueError("existing placement batch item count mismatch")

    linked = 0
    for spec in specs:
        item = spec["item"]
        resolution, provision = _resolve_provision(db, item)
        if resolution != "ok" or provision is None:
            raise ValueError(
                f"worklist changed during apply: {resolution} for {item.get('provision_key')}"
            )
        candidate = db.scalar(
            select(LegalProvisionReviewCandidate).where(
                LegalProvisionReviewCandidate.legal_provision_id
                == provision.legal_provision_id,
                LegalProvisionReviewCandidate.category == PLACEMENT_CATEGORY,
            )
        )
        if candidate is None:
            raise ValueError(
                f"placement review candidate missing after import: {provision.provision_key}"
            )
        key = (
            batch.equipment_placement_authoring_batch_id,
            candidate.legal_provision_review_candidate_id,
        )
        existing = db.get(EquipmentPlacementBatchCandidate, key)
        if existing is None:
            db.add(
                EquipmentPlacementBatchCandidate(
                    equipment_placement_authoring_batch_id=
                        batch.equipment_placement_authoring_batch_id,
                    legal_provision_review_candidate_id=
                        candidate.legal_provision_review_candidate_id,
                    provision_content_sha256=provision.content_sha256,
                )
            )
        elif existing.provision_content_sha256 != provision.content_sha256:
            raise ValueError("placement batch candidate source hash changed")
        linked += 1

    db.flush()
    result["linked_candidate_count"] = linked
    result["applied"] = True
    result["batch_id"] = batch.equipment_placement_authoring_batch_id
    return result


def _placement_draft_state(
    db: Session,
    candidate: LegalProvisionReviewCandidate,
    *,
    evaluation_date: date,
) -> dict:
    draft = (
        db.get(LegalRuleDraftCandidate, candidate.legal_rule_draft_candidate_id)
        if candidate.legal_rule_draft_candidate_id
        else None
    )
    if draft is None:
        return {
            "draft_id": None,
            "draft_status": None,
            "terminal": False,
            "approved_effective": False,
            "citations_valid": False,
        }
    if draft.status == "rejected":
        return {
            "draft_id": draft.legal_rule_draft_candidate_id,
            "draft_status": "rejected",
            "terminal": True,
            "approved_effective": False,
            "citations_valid": True,
        }
    if draft.status != "promoted" or not draft.promoted_rule_version_id:
        return {
            "draft_id": draft.legal_rule_draft_candidate_id,
            "draft_status": draft.status,
            "terminal": False,
            "approved_effective": False,
            "citations_valid": False,
        }
    rv = db.get(LegalRuleVersion, draft.promoted_rule_version_id)
    if rv is None:
        return {
            "draft_id": draft.legal_rule_draft_candidate_id,
            "draft_status": draft.status,
            "terminal": False,
            "approved_effective": False,
            "citations_valid": False,
        }

    citations = db.scalars(
        select(LegalRuleCitation).where(
            LegalRuleCitation.legal_rule_version_id == rv.legal_rule_version_id
        )
    ).all()
    flags = []
    for citation in citations:
        provision = db.get(LegalProvision, citation.legal_provision_id)
        flags.append(
            bool(
                provision
                and provision.present_in_source
                and provision.legal_source_document_version_id
                == rv.source_legal_document_version_id
            )
        )
    citations_valid = bool(flags) and all(flags)
    approved_effective = bool(
        rv.status == "approved"
        and rv.effective_from <= evaluation_date
        and (rv.effective_to is None or rv.effective_to >= evaluation_date)
        and citations_valid
    )
    return {
        "draft_id": draft.legal_rule_draft_candidate_id,
        "draft_status": draft.status,
        "rule_version_id": rv.legal_rule_version_id,
        "rule_version_status": rv.status,
        "terminal": approved_effective,
        "approved_effective": approved_effective,
        "citations_valid": citations_valid,
    }


def equipment_placement_batch_coverage(
    db: Session,
    *,
    worklist_sha256: str | None = None,
    evaluation_date: date | None = None,
) -> dict:
    evaluation_date = evaluation_date or date.today()
    stmt = select(EquipmentPlacementAuthoringBatch).order_by(
        EquipmentPlacementAuthoringBatch.created_at.desc()
    )
    if worklist_sha256:
        stmt = stmt.where(
            EquipmentPlacementAuthoringBatch.worklist_sha256 == worklist_sha256
        )
    batch = db.scalar(stmt)
    if batch is None:
        return {
            "batch_found": False,
            "coverage_complete": False,
            "blockers": ["equipment placement authoring batch is not imported"],
        }

    links = db.scalars(
        select(EquipmentPlacementBatchCandidate).where(
            EquipmentPlacementBatchCandidate.equipment_placement_authoring_batch_id
            == batch.equipment_placement_authoring_batch_id
        )
    ).all()
    counts = {
        "pending": 0,
        "reviewed": 0,
        "ignored": 0,
        "drafted": 0,
        "other": 0,
        "stale_source": 0,
        "draft_terminal_rejected": 0,
        "draft_terminal_approved": 0,
        "draft_nonterminal": 0,
    }
    items = []
    for link in links:
        candidate = db.get(
            LegalProvisionReviewCandidate,
            link.legal_provision_review_candidate_id,
        )
        if candidate is None:
            counts["other"] += 1
            items.append({
                "candidate_id": link.legal_provision_review_candidate_id,
                "state": "missing_candidate",
            })
            continue
        provision = db.get(LegalProvision, candidate.legal_provision_id)
        source_valid = bool(
            provision
            and provision.present_in_source
            and provision.content_sha256 == link.provision_content_sha256
        )
        if not source_valid:
            counts["stale_source"] += 1
        if candidate.status in counts:
            counts[candidate.status] += 1
        else:
            counts["other"] += 1

        processed = False
        draft_state = None
        if candidate.status == "ignored":
            processed = source_valid
        elif candidate.status == "drafted":
            draft_state = _placement_draft_state(
                db,
                candidate,
                evaluation_date=evaluation_date,
            )
            if draft_state["draft_status"] == "rejected":
                counts["draft_terminal_rejected"] += 1
                processed = source_valid
            elif draft_state["approved_effective"]:
                counts["draft_terminal_approved"] += 1
                processed = source_valid
            else:
                counts["draft_nonterminal"] += 1

        items.append({
            "candidate_id": candidate.legal_provision_review_candidate_id,
            "candidate_status": candidate.status,
            "provision_key": provision.provision_key if provision else None,
            "source_valid": source_valid,
            "processed": processed,
            "draft_state": draft_state,
        })

    expected = batch.expected_candidate_count
    linked = len(links)
    processed = sum(1 for x in items if x.get("processed"))
    complete = bool(
        expected > 0
        and linked == expected
        and processed == expected
        and counts["stale_source"] == 0
    )
    blockers = []
    if linked != expected:
        blockers.append(f"batch links {linked}/{expected}")
    if counts["pending"]:
        blockers.append(f"pending Human review candidates: {counts['pending']}")
    if counts["reviewed"]:
        blockers.append(
            f"reviewed candidates awaiting placement Rule Draft handoff: {counts['reviewed']}"
        )
    if counts["draft_nonterminal"]:
        blockers.append(
            f"placement Rule Drafts awaiting rejection or Approved effective promotion: {counts['draft_nonterminal']}"
        )
    if counts["stale_source"]:
        blockers.append(f"stale source provisions: {counts['stale_source']}")
    if counts["other"]:
        blockers.append(f"unexpected/missing candidate states: {counts['other']}")
    if processed != expected:
        blockers.append(f"processed candidates {processed}/{expected}")

    return {
        "batch_found": True,
        "batch_id": batch.equipment_placement_authoring_batch_id,
        "worklist_sha256": batch.worklist_sha256,
        "worklist_item_count": batch.worklist_item_count,
        "expected_candidate_count": expected,
        "linked_candidate_count": linked,
        "processed_candidate_count": processed,
        "evaluation_date": evaluation_date.isoformat(),
        "counts": counts,
        "coverage_complete": complete,
        "blockers": blockers,
        "source_metadata": batch.source_metadata or {},
        "items": items,
    }
