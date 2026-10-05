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
