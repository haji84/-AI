from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EquipmentType, SubmissionType


def validate_rule_outcome_references(
    db: Session,
    *,
    domain: str,
    outcome: dict,
) -> None:
    if not isinstance(outcome, dict) or not outcome:
        raise ValueError("outcome must be a non-empty object")

    if domain == "equipment_requirement":
        code = outcome.get("equipment_type_code")
        if code:
            row = db.scalar(
                select(EquipmentType).where(
                    EquipmentType.code == str(code),
                    EquipmentType.active.is_(True),
                )
            )
            if row is None:
                raise ValueError(f"unknown or inactive equipment_type_code: {code}")


    if domain == "occupancy_classification":
        decision = outcome.get("decision")
        if decision != "classification_candidate":
            raise ValueError("occupancy classification outcome decision must be classification_candidate")
        code = str(outcome.get("classification_code") or "").strip()
        label = str(outcome.get("classification_label") or "").strip()
        if not code:
            raise ValueError("classification_code is required for occupancy classification")
        if not label:
            raise ValueError("classification_label is required for occupancy classification")

    if domain == "equipment_placement":
        code = str(outcome.get("equipment_type_code") or "").strip()
        if code:
            row = db.scalar(
                select(EquipmentType).where(
                    EquipmentType.code == code,
                    EquipmentType.active.is_(True),
                )
            )
            if row is None:
                raise ValueError(f"unknown or inactive equipment_type_code: {code}")
        placement_mode = outcome.get("placement_mode")
        if placement_mode is not None and placement_mode not in {
            "manual_with_constraints",
            "room_candidate",
            "floor_candidate",
        }:
            raise ValueError(f"unsupported placement_mode: {placement_mode}")

    if domain == "submission_requirement":
        code = outcome.get("submission_type_code")
        if code:
            row = db.scalar(
                select(SubmissionType).where(
                    SubmissionType.code == str(code),
                    SubmissionType.active.is_(True),
                )
            )
            if row is None:
                raise ValueError(f"unknown or inactive submission_type_code: {code}")

    mode = outcome.get("comparison_mode")
    if mode is not None and mode not in {"presence", "periodic", "quantity", "manual"}:
        raise ValueError(f"unsupported comparison_mode: {mode}")
