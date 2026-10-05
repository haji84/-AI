from __future__ import annotations

from datetime import date
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_requirement_engine import evaluate_approved_rules_for_snapshot
from .models import LegalProvision, LegalRule, LegalRuleCitation, LegalRuleVersion


PLACEMENT_DOMAIN = "equipment_placement"


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def geometry_center(geometry: dict) -> dict | None:
    if not isinstance(geometry, dict):
        return None
    try:
        if all(k in geometry for k in ("x", "y", "width", "height")):
            return {
                "x": float(geometry["x"]) + float(geometry["width"]) / 2,
                "y": float(geometry["y"]) + float(geometry["height"]) / 2,
            }
        if all(k in geometry for k in ("x1", "y1", "x2", "y2")):
            return {
                "x": (float(geometry["x1"]) + float(geometry["x2"])) / 2,
                "y": (float(geometry["y1"]) + float(geometry["y2"])) / 2,
            }
        bbox = geometry.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            return {
                "x": float(bbox[0]) + float(bbox[2]) / 2,
                "y": float(bbox[1]) + float(bbox[3]) / 2,
            }
        points = geometry.get("points")
        if isinstance(points, list) and points:
            coords = []
            for point in points:
                if isinstance(point, dict) and "x" in point and "y" in point:
                    coords.append((float(point["x"]), float(point["y"])))
                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                    coords.append((float(point[0]), float(point[1])))
            if coords:
                return {
                    "x": sum(x for x, _ in coords) / len(coords),
                    "y": sum(y for _, y in coords) / len(coords),
                }
    except (TypeError, ValueError):
        return None
    return None


def evaluate_placement_candidates(
    db: Session,
    *,
    input_snapshot: dict,
    classification_code: str,
    rooms: list[dict],
    equipment_type_codes: list[str],
    evaluation_date: date,
) -> list[dict]:
    room_rows = [
        x for x in rooms
        if isinstance(x, dict) and str(x.get("element_type") or "") == "room"
    ]
    results: list[dict] = []

    for code in equipment_type_codes:
        snapshot = {
            **(input_snapshot or {}),
            "classification_code": classification_code,
            "equipment_type_code": code,
        }
        rules = evaluate_approved_rules_for_snapshot(
            db,
            snapshot=snapshot,
            domain=PLACEMENT_DOMAIN,
            evaluation_date=evaluation_date,
        )
        if not rules:
            results.append(
                {
                    "equipment_type_code": code,
                    "state": "approved_placement_rule_missing",
                    "markers": [],
                    "constraints": [],
                    "note": (
                        "No effective Approved placement Rule matched. "
                        "Do not auto-place this equipment."
                    ),
                }
            )
            continue

        markers: list[dict] = []
        constraints: list[dict] = []
        for rule in rules:
            outcome = rule.get("outcome") or {}
            mode = outcome.get("placement_mode") or "manual_with_constraints"
            constraints.append(
                {
                    "rule_code": rule.get("rule_code"),
                    "legal_rule_version_id": rule.get("legal_rule_version_id"),
                    "placement_mode": mode,
                    "constraints": outcome.get("constraints") or {},
                    "citations": rule.get("citations") or [],
                    "source_reference": rule.get("source_reference"),
                }
            )
            if mode != "room_candidate":
                continue

            target = outcome.get("target_room_use")
            targets = set(
                target if isinstance(target, list)
                else [target] if target
                else []
            )
            for room in room_rows:
                extracted = room.get("extracted_data") or {}
                use_name = (
                    str(extracted.get("use_name") or "")
                    if isinstance(extracted, dict)
                    else ""
                )
                if targets and use_name not in targets:
                    continue
                center = geometry_center(room.get("geometry") or {})
                if not center:
                    continue
                markers.append(
                    {
                        "page_no": room.get("page_no", 1),
                        "floor_number": room.get("floor_number"),
                        "room_ref": room.get("client_ref"),
                        "room_label": room.get("label"),
                        "room_use": use_name or None,
                        "geometry": center,
                        "status": "candidate",
                        "source_rule_version_id": rule.get("legal_rule_version_id"),
                    }
                )

        dedup = {}
        for marker in markers:
            key = (
                marker.get("room_ref"),
                marker.get("source_rule_version_id"),
                json.dumps(marker.get("geometry"), sort_keys=True),
            )
            dedup[key] = marker
        markers = list(dedup.values())

        results.append(
            {
                "equipment_type_code": code,
                "state": (
                    "placement_candidate"
                    if markers
                    else "manual_placement_with_constraints"
                ),
                "markers": markers,
                "constraints": constraints,
                "note": (
                    "Placement remains a Human-reviewed candidate and is not "
                    "an approved design."
                ),
            }
        )

    return results


def placement_rule_engine_fingerprint(
    db: Session,
    *,
    evaluation_date: date,
) -> str:
    rules = db.scalars(
        select(LegalRule)
        .where(
            LegalRule.domain == PLACEMENT_DOMAIN,
            LegalRule.active.is_(True),
        )
        .order_by(LegalRule.rule_code)
    ).all()
    payload = []
    for rule in rules:
        versions = db.scalars(
            select(LegalRuleVersion)
            .where(
                LegalRuleVersion.rule_id == rule.rule_id,
                LegalRuleVersion.status == "approved",
                LegalRuleVersion.effective_from <= evaluation_date,
            )
            .order_by(LegalRuleVersion.version_no.desc())
        ).all()
        version = next(
            (
                row for row in versions
                if row.effective_to is None or row.effective_to >= evaluation_date
            ),
            None,
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
                    if version.effective_to else None
                ),
                "conditions": version.conditions or {},
                "outcome": version.outcome or {},
                "source_legal_document_version_id":
                    version.source_legal_document_version_id,
                "citations": citation_payload,
            }
        )
    return _canonical_sha(payload)
