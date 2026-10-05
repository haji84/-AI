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
    EquipmentRequirementAuthoringBatch,
    EquipmentRequirementBatchCandidate,
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalRule,
    LegalRuleCitation,
    LegalRuleDraftCandidate,
    LegalRuleVersion,
    EquipmentRequirementTestCase,
    EquipmentRequirementTestRun,
)


EQUIPMENT_CATEGORY = "equipment_requirement"
BATCH_IMPORT_VERSION = "equipment-requirement-batch-v1"


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _equipment_candidate_specs(items: list[dict]) -> list[dict]:
    specs = []
    seen = set()
    for item_index, item in enumerate(items):
        for hit_index, hit in enumerate(item.get("hits") or []):
            if hit.get("category") != EQUIPMENT_CATEGORY:
                continue
            key = (
                str(item.get("scope") or ""),
                str(item.get("source_ref") or ""),
                str(item.get("provision_key") or ""),
                str(item.get("provision_content_sha256") or ""),
                EQUIPMENT_CATEGORY,
            )
            if key in seen:
                continue
            seen.add(key)
            specs.append(
                {
                    "item_index": item_index,
                    "hit_index": hit_index,
                    "item": item,
                    "provision_content_sha256": str(
                        item.get("provision_content_sha256") or ""
                    ),
                }
            )
    return specs


def equipment_worklist_batch_sha(items: list[dict]) -> str:
    normalized = []
    for spec in _equipment_candidate_specs(items):
        item = spec["item"]
        normalized.append(
            {
                "scope": item.get("scope"),
                "document_title": item.get("document_title"),
                "source_ref": item.get("source_ref"),
                "provision_key": item.get("provision_key"),
                "provision_content_sha256": item.get("provision_content_sha256"),
                "equipment_hits": [
                    {
                        "category": hit.get("category"),
                        "score": hit.get("score"),
                        "reasons": hit.get("reasons") or [],
                    }
                    for hit in (item.get("hits") or [])
                    if hit.get("category") == EQUIPMENT_CATEGORY
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


def import_equipment_requirement_batch(
    db: Session,
    *,
    items: list[dict],
    source_metadata: dict | None = None,
    apply: bool = False,
    created_by: str | None = None,
) -> dict:
    if not isinstance(items, list):
        raise ValueError("worklist items must be a list")

    specs = _equipment_candidate_specs(items)
    worklist_sha = equipment_worklist_batch_sha(items)

    base_stats = import_worklist(
        db,
        items,
        allowed_categories={EQUIPMENT_CATEGORY},
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
        select(EquipmentRequirementAuthoringBatch).where(
            EquipmentRequirementAuthoringBatch.worklist_sha256 == worklist_sha
        )
    )
    if batch is None:
        batch = EquipmentRequirementAuthoringBatch(
            worklist_sha256=worklist_sha,
            worklist_item_count=len(items),
            expected_candidate_count=len(specs),
            import_version=BATCH_IMPORT_VERSION,
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
            raise ValueError("existing batch candidate count does not match worklist")
        if batch.worklist_item_count != len(items):
            raise ValueError("existing batch item count does not match worklist")

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
                LegalProvisionReviewCandidate.category == EQUIPMENT_CATEGORY,
            )
        )
        if candidate is None:
            raise ValueError(
                f"equipment review candidate missing after import: {provision.provision_key}"
            )

        existing_link = db.get(
            EquipmentRequirementBatchCandidate,
            (
                batch.equipment_requirement_authoring_batch_id,
                candidate.legal_provision_review_candidate_id,
            ),
        )
        if existing_link is None:
            db.add(
                EquipmentRequirementBatchCandidate(
                    equipment_requirement_authoring_batch_id=
                    batch.equipment_requirement_authoring_batch_id,
                    legal_provision_review_candidate_id=
                    candidate.legal_provision_review_candidate_id,
                    provision_content_sha256=provision.content_sha256,
                )
            )
        elif existing_link.provision_content_sha256 != provision.content_sha256:
            raise ValueError("batch candidate source hash changed")
        linked += 1

    db.flush()
    result["linked_candidate_count"] = linked
    result["applied"] = True
    result["batch_id"] = batch.equipment_requirement_authoring_batch_id
    return result


def _draft_terminal_state(
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
            "draft_status": draft.status,
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
    citation_rows = []
    for citation in citations:
        provision = db.get(LegalProvision, citation.legal_provision_id)
        citation_rows.append(
            bool(
                provision
                and provision.present_in_source
                and provision.legal_source_document_version_id
                == rv.source_legal_document_version_id
            )
        )
    citations_valid = bool(citation_rows) and all(citation_rows)
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



def _active_equipment_rule_version(
    db: Session,
    *,
    rule_id: str,
    evaluation_date: date,
) -> LegalRuleVersion | None:
    rows = db.scalars(
        select(LegalRuleVersion)
        .where(
            LegalRuleVersion.rule_id == rule_id,
            LegalRuleVersion.status == "approved",
            LegalRuleVersion.effective_from <= evaluation_date,
        )
        .order_by(LegalRuleVersion.version_no.desc())
    ).all()
    return next(
        (
            row for row in rows
            if row.effective_to is None or row.effective_to >= evaluation_date
        ),
        None,
    )


def equipment_rule_engine_fingerprint(
    db: Session,
    *,
    evaluation_date: date,
) -> str:
    rules = db.scalars(
        select(LegalRule)
        .where(
            LegalRule.domain == EQUIPMENT_CATEGORY,
            LegalRule.active.is_(True),
        )
        .order_by(LegalRule.rule_code)
    ).all()
    payload = []
    for rule in rules:
        version = _active_equipment_rule_version(
            db,
            rule_id=rule.rule_id,
            evaluation_date=evaluation_date,
        )
        if version is None:
            continue
        citations = db.scalars(
            select(LegalRuleCitation).where(
                LegalRuleCitation.legal_rule_version_id
                == version.legal_rule_version_id
            )
        ).all()
        citation_payload = []
        for citation in citations:
            provision = db.get(LegalProvision, citation.legal_provision_id)
            citation_payload.append(
                {
                    "role": citation.citation_role,
                    "provision_id": citation.legal_provision_id,
                    "provision_key": provision.provision_key if provision else None,
                    "content_sha256": provision.content_sha256 if provision else None,
                    "present_in_source": bool(
                        provision and provision.present_in_source
                    ),
                }
            )
        citation_payload.sort(
            key=lambda x: (
                str(x.get("role") or ""),
                str(x.get("provision_key") or ""),
            )
        )
        payload.append(
            {
                "rule_code": rule.rule_code,
                "rule_name": rule.name,
                "rule_version_id": version.legal_rule_version_id,
                "version_no": version.version_no,
                "effective_from": version.effective_from.isoformat(),
                "effective_to": (
                    version.effective_to.isoformat()
                    if version.effective_to
                    else None
                ),
                "conditions": version.conditions or {},
                "outcome": version.outcome or {},
                "source_legal_document_version_id":
                    version.source_legal_document_version_id,
                "citations": citation_payload,
            }
        )
    return _canonical_sha(payload)


def equipment_test_suite_fingerprint(
    db: Session,
    *,
    worklist_sha256: str,
) -> str | None:
    rows = db.scalars(
        select(EquipmentRequirementTestCase)
        .where(
            EquipmentRequirementTestCase.worklist_sha256 == worklist_sha256,
            EquipmentRequirementTestCase.status == "reviewed",
        )
        .order_by(
            EquipmentRequirementTestCase.name,
            EquipmentRequirementTestCase.created_at,
        )
    ).all()
    if not rows:
        return None
    payload = [
        {
            "test_case_id": row.equipment_requirement_test_case_id,
            "version": row.version,
            "name": row.name,
            "input_snapshot": row.input_snapshot or {},
            "expected_equipment_type_codes":
                row.expected_equipment_type_codes or [],
        }
        for row in rows
    ]
    return _canonical_sha(payload)


def equipment_requirement_batch_coverage(
    db: Session,
    *,
    worklist_sha256: str | None = None,
    evaluation_date: date | None = None,
) -> dict:
    evaluation_date = evaluation_date or date.today()
    stmt = select(EquipmentRequirementAuthoringBatch).order_by(
        EquipmentRequirementAuthoringBatch.created_at.desc()
    )
    if worklist_sha256:
        stmt = stmt.where(
            EquipmentRequirementAuthoringBatch.worklist_sha256 == worklist_sha256
        )
    batch = db.scalar(stmt)
    if batch is None:
        return {
            "batch_found": False,
            "coverage_complete": False,
            "blockers": ["equipment requirement authoring batch is not imported"],
        }

    links = db.scalars(
        select(EquipmentRequirementBatchCandidate).where(
            EquipmentRequirementBatchCandidate.equipment_requirement_authoring_batch_id
            == batch.equipment_requirement_authoring_batch_id
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

        draft_state = None
        processed = False
        if candidate.status == "ignored":
            processed = source_valid
        elif candidate.status == "drafted":
            draft_state = _draft_terminal_state(
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

        items.append(
            {
                "candidate_id": candidate.legal_provision_review_candidate_id,
                "candidate_status": candidate.status,
                "provision_key": provision.provision_key if provision else None,
                "source_valid": source_valid,
                "processed": processed,
                "draft_state": draft_state,
            }
        )

    processed_count = sum(1 for x in items if x.get("processed"))
    expected = batch.expected_candidate_count
    linked_count = len(links)
    all_linked = linked_count == expected
    authoring_coverage_complete = (
        expected > 0
        and all_linked
        and processed_count == expected
        and counts["stale_source"] == 0
    )

    blockers = []
    if not all_linked:
        blockers.append(
            f"batch links {linked_count}/{expected}"
        )
    if counts["pending"]:
        blockers.append(f"pending Human review candidates: {counts['pending']}")
    if counts["reviewed"]:
        blockers.append(
            f"reviewed candidates awaiting Rule Draft handoff: {counts['reviewed']}"
        )
    if counts["draft_nonterminal"]:
        blockers.append(
            f"Rule Drafts awaiting rejection or Approved effective promotion: {counts['draft_nonterminal']}"
        )
    if counts["stale_source"]:
        blockers.append(f"stale source provisions: {counts['stale_source']}")
    if counts["other"]:
        blockers.append(f"unexpected/missing candidate states: {counts['other']}")
    if processed_count != expected:
        blockers.append(f"processed candidates {processed_count}/{expected}")


    current_rule_engine_fingerprint = equipment_rule_engine_fingerprint(
        db,
        evaluation_date=evaluation_date,
    )
    current_test_suite_fingerprint = equipment_test_suite_fingerprint(
        db,
        worklist_sha256=batch.worklist_sha256,
    )
    accepted_runs = db.scalars(
        select(EquipmentRequirementTestRun)
        .where(
            EquipmentRequirementTestRun.worklist_sha256 == batch.worklist_sha256,
            EquipmentRequirementTestRun.review_status == "reviewed",
            EquipmentRequirementTestRun.human_decision == "accepted_regression",
        )
        .order_by(EquipmentRequirementTestRun.reviewed_at.desc())
    ).all()
    matching_accepted_run = next(
        (
            run for run in accepted_runs
            if (run.result_payload or {}).get("rule_engine_fingerprint")
            == current_rule_engine_fingerprint
            and (run.result_payload or {}).get("test_suite_fingerprint")
            == current_test_suite_fingerprint
            and (run.result_payload or {}).get("evaluation_date")
            == evaluation_date.isoformat()
            and bool((run.result_payload or {}).get("overall_pass"))
        ),
        None,
    )
    regression_gate_passed = matching_accepted_run is not None
    if authoring_coverage_complete and not regression_gate_passed:
        blockers.append(
            "accepted equipment regression run is missing or stale for the current Rule/test-suite fingerprints"
        )
    final_coverage_complete = (
        authoring_coverage_complete and regression_gate_passed
    )

    return {
        "batch_found": True,
        "batch_id": batch.equipment_requirement_authoring_batch_id,
        "worklist_sha256": batch.worklist_sha256,
        "worklist_item_count": batch.worklist_item_count,
        "expected_candidate_count": expected,
        "linked_candidate_count": linked_count,
        "processed_candidate_count": processed_count,
        "evaluation_date": evaluation_date.isoformat(),
        "counts": counts,
        "authoring_coverage_complete": authoring_coverage_complete,
        "current_rule_engine_fingerprint": current_rule_engine_fingerprint,
        "current_test_suite_fingerprint": current_test_suite_fingerprint,
        "regression_gate_passed": regression_gate_passed,
        "accepted_regression_run_id": (
            matching_accepted_run.equipment_requirement_test_run_id
            if matching_accepted_run
            else None
        ),
        "coverage_complete": final_coverage_complete,
        "blockers": blockers,
        "source_metadata": batch.source_metadata or {},
        "items": items,
    }
