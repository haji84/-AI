from __future__ import annotations

ALLOWED_RULE_FIELDS = {
    "status",
    "classification_code",
    "structure",
    "above_ground_floors",
    "basement_floors",
    "building_area",
    "total_floor_area",
    "occupancy_total",
    "employee_total",
    "floor_count",
}

ALLOWED_RULE_OPS = {"eq", "ne", "in", "contains", "gte", "lte", "gt", "lt", "exists"}


def validate_rule_conditions(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("conditions must be an object")
    unexpected = set(payload) - {"all", "any"}
    if unexpected:
        raise ValueError(f"unsupported condition groups: {sorted(unexpected)}")
    clauses = list(payload.get("all") or []) + list(payload.get("any") or [])
    if not clauses:
        raise ValueError("at least one condition clause is required")
    for clause in clauses:
        if not isinstance(clause, dict):
            raise ValueError("condition clause must be an object")
        field = clause.get("field")
        op = clause.get("op")
        if field not in ALLOWED_RULE_FIELDS:
            raise ValueError(f"unsupported rule field: {field}")
        if op not in ALLOWED_RULE_OPS:
            raise ValueError(f"unsupported rule operator: {op}")
        if op != "exists" and "value" not in clause:
            raise ValueError(f"value is required for operator: {op}")
