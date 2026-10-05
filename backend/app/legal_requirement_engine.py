from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Facility,
    FacilityDetail,
    FacilityFloor,
    LegalProvision,
    LegalRule,
    LegalRuleCitation,
    LegalRuleVersion,
)


def facility_snapshot(db: Session, facility: Facility) -> dict:
    detail = db.get(FacilityDetail, facility.building_id)
    floor_count = db.scalar(
        select(func.count())
        .select_from(FacilityFloor)
        .where(FacilityFloor.building_id == facility.building_id)
    ) or 0

    def val(name: str):
        value = getattr(detail, name, None) if detail else None
        if hasattr(value, "as_integer_ratio"):
            return float(value)
        return value

    return {
        "status": facility.status,
        "classification_code": val("classification_code"),
        "structure": val("structure"),
        "above_ground_floors": val("above_ground_floors"),
        "basement_floors": val("basement_floors"),
        "building_area": val("building_area"),
        "total_floor_area": val("total_floor_area"),
        "occupancy_total": val("occupancy_total"),
        "employee_total": val("employee_total"),
        "floor_count": int(floor_count),
    }


def clause_result(clause: dict, snapshot: dict) -> dict:
    field = clause["field"]
    op = clause["op"]
    expected = clause.get("value")
    actual = snapshot.get(field)
    matched = False
    try:
        if op == "exists":
            matched = actual not in (None, "", [], {})
        elif op == "eq":
            matched = actual == expected
        elif op == "ne":
            matched = actual != expected
        elif op == "in":
            matched = actual in expected if isinstance(expected, list) else False
        elif op == "contains":
            if isinstance(actual, (list, tuple, set)):
                matched = expected in actual
            else:
                matched = str(expected) in str(actual) if actual is not None else False
        elif op == "contains_any":
            matched = (
                isinstance(actual, (list, tuple, set))
                and isinstance(expected, list)
                and any(x in actual for x in expected)
            )
        elif op == "contains_all":
            matched = (
                isinstance(actual, (list, tuple, set))
                and isinstance(expected, list)
                and all(x in actual for x in expected)
            )
        elif op == "gte":
            matched = actual is not None and actual >= expected
        elif op == "lte":
            matched = actual is not None and actual <= expected
        elif op == "gt":
            matched = actual is not None and actual > expected
        elif op == "lt":
            matched = actual is not None and actual < expected
    except (TypeError, ValueError):
        matched = False
    return {
        "field": field,
        "op": op,
        "expected": expected,
        "actual": actual,
        "matched": matched,
    }


def match_conditions(conditions: dict, snapshot: dict) -> tuple[bool, dict]:
    all_results = [clause_result(x, snapshot) for x in conditions.get("all", [])]
    any_results = [clause_result(x, snapshot) for x in conditions.get("any", [])]
    all_ok = all(x["matched"] for x in all_results) if all_results else True
    any_ok = any(x["matched"] for x in any_results) if any_results else True
    return all_ok and any_ok, {"all": all_results, "any": any_results}


def _active_version(
    db: Session,
    *,
    rule_id: str,
    evaluation_date: date,
) -> LegalRuleVersion | None:
    versions = db.scalars(
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
            x
            for x in versions
            if x.effective_to is None or x.effective_to >= evaluation_date
        ),
        None,
    )


def approved_rule_count(
    db: Session,
    *,
    domain: str,
    evaluation_date: date,
) -> int:
    rules = db.scalars(
        select(LegalRule).where(
            LegalRule.active.is_(True),
            LegalRule.domain == domain,
        )
    ).all()
    return sum(
        1
        for rule in rules
        if _active_version(db, rule_id=rule.rule_id, evaluation_date=evaluation_date)
    )


def required_input_fields_for_domain(
    db: Session,
    *,
    domain: str,
    evaluation_date: date,
) -> set[str]:
    fields: set[str] = set()
    rules = db.scalars(
        select(LegalRule).where(
            LegalRule.active.is_(True),
            LegalRule.domain == domain,
        )
    ).all()
    for rule in rules:
        version = _active_version(
            db,
            rule_id=rule.rule_id,
            evaluation_date=evaluation_date,
        )
        if not version:
            continue
        conditions = version.conditions or {}
        for clause in list(conditions.get("all") or []) + list(conditions.get("any") or []):
            field = clause.get("field")
            if field:
                fields.add(str(field))
    return fields


def evaluate_approved_rules_for_snapshot(
    db: Session,
    *,
    snapshot: dict,
    domain: str,
    evaluation_date: date,
) -> list[dict]:
    rules = db.scalars(
        select(LegalRule)
        .where(
            LegalRule.active.is_(True),
            LegalRule.domain == domain,
        )
        .order_by(LegalRule.rule_code)
    ).all()

    results: list[dict] = []
    for rule in rules:
        version = _active_version(
            db,
            rule_id=rule.rule_id,
            evaluation_date=evaluation_date,
        )
        if not version:
            continue

        matched, evidence = match_conditions(version.conditions, snapshot)
        if not matched:
            continue

        citations = db.scalars(
            select(LegalRuleCitation).where(
                LegalRuleCitation.legal_rule_version_id
                == version.legal_rule_version_id
            )
        ).all()
        citation_payload: list[dict] = []
        for citation in citations:
            provision = db.get(LegalProvision, citation.legal_provision_id)
            if provision:
                citation_payload.append(
                    {
                        "role": citation.citation_role,
                        "legal_provision_id": provision.legal_provision_id,
                        "provision_key": provision.provision_key,
                        "display_label": provision.display_label,
                        "heading_text": provision.heading_text,
                        "body_text": provision.body_text,
                    }
                )

        results.append(
            {
                "rule_id": rule.rule_id,
                "rule_code": rule.rule_code,
                "rule_name": rule.name,
                "legal_rule_version_id": version.legal_rule_version_id,
                "version_no": version.version_no,
                "source_document_id": version.source_document_id,
                "source_reference": version.source_reference,
                "source_legal_document_version_id": version.source_legal_document_version_id,
                "citations": citation_payload,
                "outcome": version.outcome,
                "evidence": evidence,
                "decision_status": "candidate",
            }
        )
    return results


def evaluate_approved_requirement_rules(
    db: Session,
    *,
    facility: Facility,
    domain: str,
    evaluation_date: date,
) -> tuple[dict, list[dict]]:
    snapshot = facility_snapshot(db, facility)
    results = evaluate_approved_rules_for_snapshot(
        db,
        snapshot=snapshot,
        domain=domain,
        evaluation_date=evaluation_date,
    )
    return snapshot, results
