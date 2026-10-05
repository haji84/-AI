from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_rule_validation import validate_rule_conditions
from .models import (
    LegalProvision,
    LegalRule,
    LegalRuleCitation,
    LegalRuleDraftCandidate,
    LegalRuleDraftCitation,
    LegalRuleVersion,
)
from .occupancy_authoring_import import IMPORT_VERSION


EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT = 35

OCCUPANCY_CONDITION_FIELDS = {
    "primary_use",
    "use_tags",
    "has_sleeping_use",
    "has_food_service",
    "public_access",
    "mixed_use",
    "windowless_floor_count",
    "structure",
    "above_ground_floors",
    "basement_floors",
    "building_area",
    "total_floor_area",
    "occupancy_total",
    "employee_total",
}


def _source_sha(row: LegalRuleDraftCandidate) -> str | None:
    context = row.generation_context or {}
    value = context.get("source_xml_sha256")
    return str(value) if value else None


def _classification_code(row: LegalRuleDraftCandidate) -> str | None:
    context = row.generation_context or {}
    value = context.get("classification_code")
    if value:
        return str(value)
    outcome = row.proposed_outcome or {}
    value = outcome.get("classification_code")
    return str(value) if value else None


def _classification_label(row: LegalRuleDraftCandidate) -> str | None:
    context = row.generation_context or {}
    value = context.get("classification_label")
    if value:
        return str(value)
    outcome = row.proposed_outcome or {}
    value = outcome.get("classification_label")
    return str(value) if value else None


def _condition_fields(conditions: dict) -> set[str]:
    fields: set[str] = set()
    if not isinstance(conditions, dict):
        return fields
    for clause in list(conditions.get("all") or []) + list(conditions.get("any") or []):
        if isinstance(clause, dict) and clause.get("field"):
            fields.add(str(clause["field"]))
    return fields


def validate_occupancy_conditions(conditions: dict) -> tuple[bool, str | None]:
    if not conditions:
        return False, "applicability conditions have not been authored"
    try:
        validate_rule_conditions(conditions)
    except ValueError as exc:
        return False, str(exc)
    fields = _condition_fields(conditions)
    unsupported = sorted(fields - OCCUPANCY_CONDITION_FIELDS)
    if unsupported:
        return False, f"occupancy classification cannot use fields: {unsupported}"
    return True, None


def _batch_rows(
    db: Session,
    *,
    source_xml_sha256: str | None = None,
) -> tuple[str | None, list[LegalRuleDraftCandidate]]:
    rows = db.scalars(
        select(LegalRuleDraftCandidate)
        .where(
            LegalRuleDraftCandidate.domain == "occupancy_classification",
            LegalRuleDraftCandidate.model_version == IMPORT_VERSION,
        )
        .order_by(LegalRuleDraftCandidate.created_at.desc())
    ).all()

    if source_xml_sha256:
        return source_xml_sha256, [
            row for row in rows if _source_sha(row) == source_xml_sha256
        ]

    selected_sha = next((_source_sha(row) for row in rows if _source_sha(row)), None)
    if not selected_sha:
        return None, []
    return selected_sha, [row for row in rows if _source_sha(row) == selected_sha]


def _draft_citations(db: Session, row: LegalRuleDraftCandidate) -> list[dict]:
    citations = db.scalars(
        select(LegalRuleDraftCitation).where(
            LegalRuleDraftCitation.legal_rule_draft_candidate_id
            == row.legal_rule_draft_candidate_id
        )
    ).all()
    out = []
    for citation in citations:
        provision = db.get(LegalProvision, citation.legal_provision_id)
        out.append(
            {
                "citation_role": citation.citation_role,
                "legal_provision_id": citation.legal_provision_id,
                "provision_key": provision.provision_key if provision else None,
                "provision_type": provision.provision_type if provision else None,
                "body_text": provision.body_text if provision else None,
                "present_in_source": bool(provision and provision.present_in_source),
                "same_source_version": bool(
                    provision
                    and provision.legal_source_document_version_id
                    == row.source_legal_document_version_id
                ),
            }
        )
    return out


def build_occupancy_authoring_worklist(
    db: Session,
    *,
    source_xml_sha256: str | None = None,
) -> dict:
    selected_sha, rows = _batch_rows(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    rows = sorted(rows, key=lambda x: x.proposed_rule_code or "")

    items = []
    valid_conditions = 0
    blank_conditions = 0
    invalid_conditions = 0

    for row in rows:
        ok, error = validate_occupancy_conditions(row.proposed_conditions or {})
        if ok:
            valid_conditions += 1
            condition_status = "valid"
        elif not row.proposed_conditions:
            blank_conditions += 1
            condition_status = "blank"
        else:
            invalid_conditions += 1
            condition_status = "invalid"

        rv = (
            db.get(LegalRuleVersion, row.promoted_rule_version_id)
            if row.promoted_rule_version_id
            else None
        )
        citations = _draft_citations(db, row)
        items.append(
            {
                "draft_id": row.legal_rule_draft_candidate_id,
                "version": row.version,
                "classification_code": _classification_code(row),
                "classification_label": _classification_label(row),
                "proposed_rule_code": row.proposed_rule_code,
                "proposed_name": row.proposed_name,
                "proposed_conditions": row.proposed_conditions or {},
                "condition_status": condition_status,
                "condition_error": error,
                "draft_status": row.status,
                "rationale": row.rationale,
                "source_version_id": row.source_legal_document_version_id,
                "source_xml_sha256": _source_sha(row),
                "citations": citations,
                "promoted_rule_id": row.promoted_rule_id,
                "promoted_rule_version_id": row.promoted_rule_version_id,
                "promoted_rule_version_status": rv.status if rv else None,
                "generation_context": row.generation_context or {},
            }
        )

    codes = [x["classification_code"] for x in items if x["classification_code"]]
    unique_codes = set(codes)
    duplicate_codes = sorted(
        {code for code in unique_codes if codes.count(code) > 1}
    )

    return {
        "source_xml_sha256": selected_sha,
        "expected_classification_count": EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT,
        "allowed_condition_fields": sorted(OCCUPANCY_CONDITION_FIELDS),
        "summary": {
            "skeleton_count": len(items),
            "unique_classification_count": len(unique_codes),
            "blank_condition_count": blank_conditions,
            "valid_condition_count": valid_conditions,
            "invalid_condition_count": invalid_conditions,
            "duplicate_classification_codes": duplicate_codes,
        },
        "items": items,
    }


def bulk_author_occupancy_conditions(
    db: Session,
    *,
    source_xml_sha256: str,
    updates: list[dict],
    apply: bool = False,
) -> dict:
    _, rows = _batch_rows(db, source_xml_sha256=source_xml_sha256)
    by_id = {row.legal_rule_draft_candidate_id: row for row in rows}

    results = []
    errors = 0
    seen_draft_ids: set[str] = set()
    for item in updates:
        draft_id = str(item.get("draft_id") or "")
        row = by_id.get(draft_id)
        result = {
            "draft_id": draft_id,
            "classification_code": _classification_code(row) if row else None,
            "valid": False,
            "error": None,
        }
        if draft_id in seen_draft_ids:
            result["error"] = "duplicate draft_id in bulk authoring request"
            errors += 1
            results.append(result)
            continue
        seen_draft_ids.add(draft_id)
        if row is None:
            result["error"] = "draft is not in the selected occupancy catalog batch"
            errors += 1
            results.append(result)
            continue
        if row.status != "pending":
            result["error"] = f"draft status is {row.status}; only pending drafts can be authored"
            errors += 1
            results.append(result)
            continue

        expected_version = item.get("expected_version")
        if expected_version != row.version:
            result["error"] = (
                f"version conflict: expected {expected_version}, current {row.version}"
            )
            errors += 1
            results.append(result)
            continue

        conditions = item.get("proposed_conditions")
        ok, error = validate_occupancy_conditions(conditions)
        if not ok:
            result["error"] = error
            errors += 1
            results.append(result)
            continue

        result["valid"] = True
        results.append(result)

    if apply and errors:
        return {
            "apply": True,
            "applied": False,
            "error_count": errors,
            "updated_count": 0,
            "results": results,
            "note": "No changes were applied because bulk authoring is atomic.",
        }

    updated = 0
    if apply:
        for item in updates:
            row = by_id[str(item["draft_id"])]
            row.proposed_conditions = item["proposed_conditions"]
            if item.get("rationale") is not None:
                row.rationale = str(item["rationale"])
            row.version += 1
            row.updated_at = datetime.now(timezone.utc)
            updated += 1
        db.flush()

    return {
        "apply": apply,
        "applied": bool(apply and errors == 0),
        "error_count": errors,
        "updated_count": updated,
        "results": results,
        "note": (
            "Conditions only. Classification identity, official outcome, citations, "
            "review status and approval status are not changed."
        ),
    }


def occupancy_rule_coverage(
    db: Session,
    *,
    source_xml_sha256: str | None = None,
    evaluation_date: date | None = None,
) -> dict:
    evaluation_date = evaluation_date or date.today()
    worklist = build_occupancy_authoring_worklist(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    selected_sha = worklist["source_xml_sha256"]
    items = worklist["items"]

    approved_effective = 0
    reviewed = 0
    promoted = 0
    citation_valid_count = 0
    valid_condition_count = 0
    codes = []

    coverage_items = []
    for item in items:
        code = item["classification_code"]
        if code:
            codes.append(code)
        if item["condition_status"] == "valid":
            valid_condition_count += 1
        if item["draft_status"] in {"reviewed", "promoted"}:
            reviewed += 1
        if item["draft_status"] == "promoted":
            promoted += 1

        row = db.get(LegalRuleDraftCandidate, item["draft_id"])
        rv = (
            db.get(LegalRuleVersion, row.promoted_rule_version_id)
            if row and row.promoted_rule_version_id
            else None
        )
        rule = (
            db.get(LegalRule, row.promoted_rule_id)
            if row and row.promoted_rule_id
            else None
        )

        rule_citations = []
        citations_valid = False
        if rv:
            citations = db.scalars(
                select(LegalRuleCitation).where(
                    LegalRuleCitation.legal_rule_version_id
                    == rv.legal_rule_version_id
                )
            ).all()
            for citation in citations:
                provision = db.get(LegalProvision, citation.legal_provision_id)
                rule_citations.append(
                    {
                        "legal_provision_id": citation.legal_provision_id,
                        "provision_key": provision.provision_key if provision else None,
                        "present_in_source": bool(
                            provision and provision.present_in_source
                        ),
                        "same_source_version": bool(
                            provision
                            and provision.legal_source_document_version_id
                            == rv.source_legal_document_version_id
                        ),
                    }
                )
            citations_valid = bool(rule_citations) and all(
                x["present_in_source"] and x["same_source_version"]
                for x in rule_citations
            )
        if citations_valid:
            citation_valid_count += 1

        effective = bool(
            rv
            and rule
            and rule.active
            and rv.status == "approved"
            and rv.effective_from <= evaluation_date
            and (rv.effective_to is None or rv.effective_to >= evaluation_date)
            and item["condition_status"] == "valid"
            and citations_valid
        )
        if effective:
            approved_effective += 1

        coverage_items.append(
            {
                "classification_code": code,
                "draft_id": item["draft_id"],
                "draft_status": item["draft_status"],
                "condition_status": item["condition_status"],
                "promoted_rule_id": item["promoted_rule_id"],
                "promoted_rule_version_id": item["promoted_rule_version_id"],
                "rule_version_status": rv.status if rv else None,
                "citations_valid": citations_valid,
                "approved_and_effective": effective,
            }
        )

    unique_codes = set(codes)
    duplicate_codes = sorted(
        {code for code in unique_codes if codes.count(code) > 1}
    )

    catalog_sizes: set[int] = set()
    for item in items:
        raw_size = (item.get("generation_context") or {}).get("catalog_entry_count")
        if raw_size is None:
            continue
        try:
            catalog_sizes.add(int(raw_size))
        except (TypeError, ValueError):
            catalog_sizes.add(-1)
    catalog_batch_valid = catalog_sizes == {EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}

    complete = (
        selected_sha is not None
        and catalog_batch_valid
        and len(items) == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and len(unique_codes) == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and not duplicate_codes
        and valid_condition_count == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and citation_valid_count == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and approved_effective == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
    )

    blockers = []
    if selected_sha is None:
        blockers.append("official occupancy authoring batch is not imported")
    if not catalog_batch_valid:
        blockers.append(
            f"catalog batch size marker is not the verified {EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}: {sorted(catalog_sizes)}"
        )
    if len(items) != EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT:
        blockers.append(
            f"expected {EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT} skeletons, found {len(items)}"
        )
    if duplicate_codes:
        blockers.append(f"duplicate classification codes: {duplicate_codes}")
    if valid_condition_count != EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT:
        blockers.append(
            f"valid conditions {valid_condition_count}/{EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}"
        )
    if citation_valid_count != EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT:
        blockers.append(
            f"valid promoted citations {citation_valid_count}/{EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}"
        )
    if approved_effective != EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT:
        blockers.append(
            f"approved effective Rules {approved_effective}/{EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}"
        )

    return {
        "source_xml_sha256": selected_sha,
        "evaluation_date": evaluation_date.isoformat(),
        "expected_classification_count": EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT,
        "catalog_batch_valid": catalog_batch_valid,
        "catalog_batch_size_markers": sorted(catalog_sizes),
        "skeleton_count": len(items),
        "unique_classification_count": len(unique_codes),
        "valid_condition_count": valid_condition_count,
        "reviewed_count": reviewed,
        "promoted_count": promoted,
        "valid_promoted_citation_count": citation_valid_count,
        "approved_effective_count": approved_effective,
        "duplicate_classification_codes": duplicate_codes,
        "coverage_complete": complete,
        "blockers": blockers,
        "items": coverage_items,
    }
