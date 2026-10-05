from __future__ import annotations

from datetime import date
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .equipment_authoring_batch import equipment_requirement_batch_coverage
from .equipment_placement_batch import equipment_placement_batch_coverage
from .equipment_placement_engine import evaluate_placement_candidates
from .legal_requirement_engine import (
    evaluate_approved_rules_for_snapshot,
    required_input_fields_for_domain,
)
from .models import (
    Document,
    DrawingAnalysis,
    DrawingAnnotationSet,
    DrawingConsultation,
    EquipmentType,
    LegalProvision,
)
from .occupancy_authoring_workbench import occupancy_rule_coverage


COVERAGE_FIELDS = {
    "occupancy_classification_rule_coverage",
    "equipment_requirement_rule_coverage",
    "equipment_placement_rule_coverage",
}


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _missing_equipment_inputs(
    db: Session,
    *,
    snapshot: dict,
    evaluation_date: date,
) -> list[dict]:
    fields = required_input_fields_for_domain(
        db,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
    )
    missing = []
    for field in sorted(fields):
        value = snapshot.get(field)
        if value in (None, "", [], {}):
            missing.append(
                {
                    "field": field,
                    "reason": (
                        "required by an effective equipment requirement Rule "
                        "but not supplied"
                    ),
                }
            )
    return missing


def _required_equipment(
    db: Session,
    *,
    snapshot: dict,
    evaluation_date: date,
) -> list[dict]:
    matches = evaluate_approved_rules_for_snapshot(
        db,
        snapshot=snapshot,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
    )
    by_code: dict[str, dict] = {}
    for match in matches:
        outcome = match.get("outcome") or {}
        if outcome.get("decision") != "required":
            continue
        code = str(outcome.get("equipment_type_code") or "").strip()
        if not code:
            continue
        equipment = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == code,
                EquipmentType.active.is_(True),
            )
        )
        row = by_code.setdefault(
            code,
            {
                "equipment_type_code": code,
                "equipment_type_name": equipment.name if equipment else None,
                "rule_matches": [],
            },
        )
        row["rule_matches"].append(
            {
                "rule_code": match.get("rule_code"),
                "rule_name": match.get("rule_name"),
                "legal_rule_version_id": match.get("legal_rule_version_id"),
                "outcome": outcome,
                "citations": match.get("citations") or [],
                "source_reference": match.get("source_reference"),
                "evidence": match.get("evidence") or {},
            }
        )
    return [by_code[key] for key in sorted(by_code)]


def _existing_equipment(annotation: DrawingAnnotationSet) -> list[dict]:
    rows = []
    seen = set()
    for candidate in (annotation.payload or {}).get(
        "equipment_candidates", []
    ):
        if not isinstance(candidate, dict):
            continue
        code = str(
            candidate.get("equipment_type_code")
            or candidate.get("suggested_equipment_type_code")
            or ""
        ).strip()
        if not code:
            continue
        key = (
            code,
            candidate.get("drawing_element_ref"),
            candidate.get("floor_number"),
            candidate.get("location_text"),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "equipment_type_code": code,
                "drawing_element_ref":
                    candidate.get("drawing_element_ref"),
                "floor_number": candidate.get("floor_number"),
                "location_text": candidate.get("location_text"),
                "quantity": candidate.get("quantity"),
            }
        )
    return rows


def _collect_citations(
    required: list[dict],
    placement: list[dict],
) -> list[dict]:
    dedup = {}
    for equipment in required:
        for rule in equipment.get("rule_matches") or []:
            for citation in rule.get("citations") or []:
                key = (
                    citation.get("legal_provision_id"),
                    citation.get("provision_key"),
                    rule.get("legal_rule_version_id"),
                    "equipment_requirement",
                )
                dedup[key] = {
                    **citation,
                    "domain": "equipment_requirement",
                    "rule_code": rule.get("rule_code"),
                    "legal_rule_version_id":
                        rule.get("legal_rule_version_id"),
                }
    for group in placement:
        for constraint in group.get("constraints") or []:
            for citation in constraint.get("citations") or []:
                key = (
                    citation.get("legal_provision_id"),
                    citation.get("provision_key"),
                    constraint.get("legal_rule_version_id"),
                    "equipment_placement",
                )
                dedup[key] = {
                    **citation,
                    "domain": "equipment_placement",
                    "rule_code": constraint.get("rule_code"),
                    "legal_rule_version_id":
                        constraint.get("legal_rule_version_id"),
                }
    return list(dedup.values())


def _source_provision_hashes(
    db: Session,
    citations: list[dict],
) -> list[dict]:
    rows = []
    seen = set()
    for citation in citations:
        provision_id = citation.get("legal_provision_id")
        if not provision_id or provision_id in seen:
            continue
        seen.add(provision_id)
        provision = db.get(LegalProvision, provision_id)
        rows.append(
            {
                "legal_provision_id": provision_id,
                "provision_key":
                    provision.provision_key if provision else None,
                "content_sha256":
                    provision.content_sha256 if provision else None,
                "present_in_source": bool(
                    provision and provision.present_in_source
                ),
            }
        )
    return rows


def build_consultation_response_package(
    db: Session,
    *,
    consultation: DrawingConsultation,
    evaluation_date: date,
) -> dict:
    analysis = db.get(
        DrawingAnalysis,
        consultation.drawing_analysis_id,
    )
    annotation = db.get(
        DrawingAnnotationSet,
        consultation.drawing_annotation_set_id,
    )
    document = (
        db.get(Document, analysis.document_id)
        if analysis else None
    )

    blockers = []
    if analysis is None:
        blockers.append("drawing analysis is missing")
    if annotation is None or annotation.status != "reviewed":
        blockers.append(
            "Human-reviewed drawing annotation is missing"
        )
    if not consultation.confirmed_classification_code:
        blockers.append(
            "occupancy classification is not Human-confirmed"
        )

    snapshot = dict(consultation.input_snapshot or {})
    if consultation.confirmed_classification_code:
        snapshot["classification_code"] = (
            consultation.confirmed_classification_code
        )

    occupancy_coverage = occupancy_rule_coverage(
        db,
        evaluation_date=evaluation_date,
    )
    requirement_coverage = equipment_requirement_batch_coverage(
        db,
        evaluation_date=evaluation_date,
    )
    placement_coverage = equipment_placement_batch_coverage(
        db,
        evaluation_date=evaluation_date,
    )

    missing_inputs = (
        _missing_equipment_inputs(
            db,
            snapshot=snapshot,
            evaluation_date=evaluation_date,
        )
        if consultation.confirmed_classification_code
        else []
    )

    required = (
        _required_equipment(
            db,
            snapshot=snapshot,
            evaluation_date=evaluation_date,
        )
        if consultation.confirmed_classification_code
        else []
    )

    rooms = (
        (annotation.payload or {}).get("elements", [])
        if annotation and annotation.status == "reviewed"
        else []
    )
    placement = (
        evaluate_placement_candidates(
            db,
            input_snapshot=consultation.input_snapshot or {},
            classification_code=(
                consultation.confirmed_classification_code
                or ""
            ),
            rooms=rooms,
            equipment_type_codes=[
                x["equipment_type_code"] for x in required
            ],
            evaluation_date=evaluation_date,
        )
        if consultation.confirmed_classification_code
        else []
    )

    existing = (
        _existing_equipment(annotation)
        if annotation and annotation.status == "reviewed"
        else []
    )
    existing_codes = {
        x["equipment_type_code"] for x in existing
    }
    required_codes = {
        x["equipment_type_code"] for x in required
    }

    placement_by_code = {
        x["equipment_type_code"]: x for x in placement
    }
    equipment_actions = []
    for row in required:
        code = row["equipment_type_code"]
        placement_row = placement_by_code.get(code)
        equipment_actions.append(
            {
                "equipment_type_code": code,
                "equipment_type_name":
                    row.get("equipment_type_name"),
                "action": (
                    "present_in_drawing"
                    if code in existing_codes
                    else "add_candidate"
                ),
                "rule_matches": row.get("rule_matches") or [],
                "placement": placement_row,
            }
        )
    for row in existing:
        code = row["equipment_type_code"]
        if code in required_codes:
            continue
        equipment_actions.append(
            {
                "equipment_type_code": code,
                "equipment_type_name": None,
                "action": "existing_unmatched",
                "existing": row,
                "note": (
                    "Not matched by the current required-equipment "
                    "result. Do not infer that removal is allowed."
                ),
            }
        )

    overlay_markers = []
    for group in placement:
        for marker in group.get("markers") or []:
            overlay_markers.append(
                {
                    **marker,
                    "equipment_type_code":
                        group.get("equipment_type_code"),
                }
            )

    placement_missing = [
        x["equipment_type_code"]
        for x in placement
        if x.get("state")
        == "approved_placement_rule_missing"
    ]

    current_noncoverage_missing = [
        x for x in (consultation.missing_information or [])
        if x.get("field") not in COVERAGE_FIELDS
        and x.get("field") != "approved_rule_set"
    ]
    unresolved_questions = (
        current_noncoverage_missing + missing_inputs
    )

    coverage_summary = {
        "occupancy_classification": {
            "complete": bool(
                occupancy_coverage.get("coverage_complete")
            ),
            "accepted_regression_run_id":
                occupancy_coverage.get(
                    "accepted_regression_run_id"
                ),
            "blockers":
                occupancy_coverage.get("blockers") or [],
        },
        "equipment_requirement": {
            "complete": bool(
                requirement_coverage.get("coverage_complete")
            ),
            "worklist_sha256":
                requirement_coverage.get("worklist_sha256"),
            "accepted_regression_run_id":
                requirement_coverage.get(
                    "accepted_regression_run_id"
                ),
            "blockers":
                requirement_coverage.get("blockers") or [],
        },
        "equipment_placement": {
            "complete": bool(
                placement_coverage.get("coverage_complete")
            ),
            "worklist_sha256":
                placement_coverage.get("worklist_sha256"),
            "accepted_regression_run_id":
                placement_coverage.get(
                    "accepted_regression_run_id"
                ),
            "blockers":
                placement_coverage.get("blockers") or [],
        },
    }
    coverage_complete = all(
        x["complete"] for x in coverage_summary.values()
    )

    if missing_inputs:
        blockers.append(
            f"required consultation inputs missing: "
            f"{len(missing_inputs)}"
        )
    if placement_missing:
        blockers.append(
            "Approved placement Rule is missing for: "
            + ", ".join(sorted(placement_missing))
        )

    citations = _collect_citations(required, placement)
    provision_hashes = _source_provision_hashes(
        db,
        citations,
    )
    if any(not x["present_in_source"] for x in provision_hashes):
        blockers.append(
            "one or more cited legal provisions are no longer "
            "present in source"
        )

    base_state = "blocked"
    if (
        consultation.confirmed_classification_code
        and annotation
        and annotation.status == "reviewed"
    ):
        base_state = "partial"
    if (
        base_state == "partial"
        and coverage_complete
        and not unresolved_questions
        and not placement_missing
        and not blockers
    ):
        base_state = "review_ready"

    core = {
        "response_format":
            "fire-ai-drawing-consultation-response-v1",
        "evaluation_date": evaluation_date.isoformat(),
        "consultation_id":
            consultation.drawing_consultation_id,
        "source": {
            "drawing_analysis_id":
                consultation.drawing_analysis_id,
            "drawing_annotation_set_id":
                consultation.drawing_annotation_set_id,
            "annotation_version":
                annotation.version if annotation else None,
            "document_id":
                document.document_id if document else None,
            "filename":
                document.original_filename if document else None,
            "document_sha256":
                document.sha256 if document else None,
        },
        "classification": {
            "code":
                consultation.confirmed_classification_code,
            "label":
                consultation.confirmed_classification_label,
            "confirmed_rule_version_id":
                consultation
                .confirmed_classification_rule_version_id,
            "confirmed_at": (
                consultation
                .classification_confirmed_at.isoformat()
                if consultation.classification_confirmed_at
                else None
            ),
        },
        "input_snapshot": snapshot,
        "existing_equipment": existing,
        "required_equipment": required,
        "equipment_actions": equipment_actions,
        "placement_results": placement,
        "overlay_markers": overlay_markers,
        "citations": citations,
        "cited_provision_hashes": provision_hashes,
        "unresolved_questions": unresolved_questions,
        "coverage": coverage_summary,
        "coverage_complete": coverage_complete,
        "blockers": blockers,
    }
    response_sha = _canonical_sha(core)

    saved_sha = consultation.response_sha256
    saved_review_current = bool(
        consultation.status == "reviewed"
        and saved_sha
        and saved_sha == response_sha
    )
    saved_review_stale = bool(
        consultation.status == "reviewed"
        and saved_sha
        and saved_sha != response_sha
    )

    state = base_state
    if saved_review_current:
        state = "reviewed"
    elif saved_review_stale:
        state = "review_stale"

    return {
        **core,
        "answer_state": state,
        "reviewable": base_state == "review_ready",
        "response_sha256": response_sha,
        "saved_response_sha256": saved_sha,
        "review_current": saved_review_current,
        "review_stale": saved_review_stale,
        "reviewed_at": (
            consultation.reviewed_at.isoformat()
            if consultation.reviewed_at else None
        ),
        "response_review_notes":
            consultation.response_review_notes,
    }
