from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SubmissionType

DEFAULT_SUBMISSION_TYPES = {
    "equipment_inspection_report": {
        "name": "消防用設備等点検結果報告",
        "category": "equipment",
        "requires_document": True,
        "rules": {"dashboard": True, "requirement_status": "not_evaluated", "specialized_model": "equipment_inspection_report"},
    },
    "fire_manager_appointment": {
        "name": "防火管理者選任・解任関係",
        "category": "fire_management",
        "requires_document": True,
        "rules": {"dashboard": True, "requirement_status": "not_evaluated", "specialized_model": "fire_management_assignment"},
    },
    "fire_plan": {
        "name": "消防計画",
        "category": "fire_management",
        "requires_document": True,
        "rules": {"dashboard": True, "requirement_status": "not_evaluated", "specialized_model": "fire_plan"},
    },
    "other_submission": {
        "name": "その他届出・申請",
        "category": "other",
        "requires_document": True,
        "rules": {"dashboard": False, "requirement_status": "not_evaluated"},
    },
}


def seed_submission_types(db: Session) -> dict[str, SubmissionType]:
    out: dict[str, SubmissionType] = {}
    for code, cfg in DEFAULT_SUBMISSION_TYPES.items():
        row = db.scalar(select(SubmissionType).where(SubmissionType.code == code))
        if row is None:
            row = SubmissionType(code=code, **cfg)
            db.add(row)
            db.flush()
        else:
            row.name = cfg["name"]
            row.category = cfg["category"]
            row.requires_document = cfg["requires_document"]
            row.rules = cfg["rules"]
            row.active = True
        out[code] = row
    db.flush()
    return out