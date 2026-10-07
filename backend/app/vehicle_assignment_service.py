"""Current placement is derived from immutable Human-recorded registry changes.

Source evidence here is a Human-entered reference, never verified original-document
evidence. Pausing a vehicle or organization does not move it or rewrite history.
"""
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update

from .audit import write_audit
from .models import now_utc
from .operations_models import Vehicle, VehicleAssignmentChange
from .personnel import OrganizationUnit
from . import operations_service as ops


def organization_snapshot(row):
    return {field: getattr(row, field) for field in ('organization_id', 'code', 'name', 'version', 'active')}


def list_organizations(db, q, limit, offset):
    statement = select(OrganizationUnit).where(OrganizationUnit.active.is_(True))
    if q:
        statement = statement.where(or_(OrganizationUnit.code.contains(q, autoescape=True), OrganizationUnit.name.contains(q, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(OrganizationUnit.code, OrganizationUnit.organization_id).offset(offset).limit(limit))
    return {'items': [{field: getattr(row, field) for field in ('organization_id', 'code', 'name', 'version')} for row in rows],
            'total': total, 'limit': limit, 'offset': offset}


def changes_for(vehicle):
    # A read uses the observed Vehicle version as its consistent history boundary,
    # even if another transaction commits between the detail queries.
    return select(VehicleAssignmentChange).where(
        VehicleAssignmentChange.vehicle_id == vehicle.vehicle_id,
        VehicleAssignmentChange.vehicle_version_after <= vehicle.version)


def latest_change(db, vehicle):
    return db.scalar(changes_for(vehicle).order_by(VehicleAssignmentChange.vehicle_version_after.desc()).limit(1))


def change_dict(row):
    changed_at = ops.utc(row.changed_at).isoformat()
    return {**{field: ops.scalar(getattr(row, field)) for field in (
        'assignment_change_id', 'action', 'before_organization', 'after_organization',
        'vehicle_version_before', 'vehicle_version_after', 'changed_by', 'reason', 'source_evidence')},
        'changed_at': changed_at,
        'human_confirmation': {'acknowledged': row.human_acknowledged, 'user_id': row.changed_by, 'at': changed_at}}


def current_dict(db, row):
    if row is None:
        return None
    organization = db.get(OrganizationUnit, row.after_organization_id, populate_existing=True) if row.after_organization_id else None
    change = change_dict(row)
    return {**{field: change[field] for field in (
        'assignment_change_id', 'vehicle_version_after', 'changed_by', 'changed_at', 'reason', 'source_evidence', 'human_confirmation')},
        'state': 'assigned' if row.action == 'assign' else 'unassigned',
        'organization': organization_snapshot(organization) if organization else None,
        'recorded_organization': row.after_organization}


def history(db, key, limit, offset):
    vehicle = ops.get_row(db, Vehicle, key)
    statement = changes_for(vehicle)
    current = latest_change(db, vehicle)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(VehicleAssignmentChange.vehicle_version_after.desc()).offset(offset).limit(limit))
    return {'vehicle_id': vehicle.vehicle_id, 'vehicle_version': vehicle.version,
            'current': current_dict(db, current), 'items': [change_dict(row) for row in rows],
            'total': total, 'limit': limit, 'offset': offset}


def change_assignment(db, user, key, payload):
    # Router's mutation guard owns the account lock before any source lock.
    ops.need(db, user, 'fleet.read')
    vehicle = ops.get_row(db, Vehicle, key, True)
    ops.check_version(vehicle, payload.expected_version)
    previous = latest_change(db, vehicle)
    before = previous.after_organization if previous else None
    after = None
    if payload.action == 'assign':
        target = ops.get_row(db, OrganizationUnit, payload.organization_id, True)
        ops.check_version(target, payload.expected_organization_version)
        if not target.active:
            raise HTTPException(409, 'organization is inactive; reload available organizations')
        after = organization_snapshot(target)
    if previous and before == after and previous.reason == payload.reason and previous.source_evidence == payload.source_evidence:
        raise HTTPException(409, 'assignment and confirmation are unchanged')
    changed_at = now_utc()
    updated = db.execute(update(Vehicle).where(Vehicle.vehicle_id == vehicle.vehicle_id,
        Vehicle.version == payload.expected_version).values(version=payload.expected_version + 1, updated_at=changed_at))
    if updated.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'record version conflict; reload latest record')
    row = VehicleAssignmentChange(vehicle_id=vehicle.vehicle_id, action=payload.action,
        before_organization_id=before['organization_id'] if before else None,
        after_organization_id=after['organization_id'] if after else None,
        before_organization=before, after_organization=after,
        vehicle_version_before=payload.expected_version, vehicle_version_after=payload.expected_version + 1,
        changed_by=user.user_id, changed_at=changed_at, reason=payload.reason,
        source_evidence=payload.source_evidence, human_acknowledged=True)
    db.add(row)
    ops.flush(db)
    # Fleet history retains full references; generic audit readers see only metadata.
    write_audit(db, user_id=user.user_id, action='fleet.assignment.' + payload.action,
        entity_type=VehicleAssignmentChange.__tablename__, entity_id=row.assignment_change_id,
        before={'vehicle_id': vehicle.vehicle_id, 'vehicle_version': payload.expected_version,
                'state': 'unknown' if previous is None else ('assigned' if before else 'unassigned'),
                'organization_id': row.before_organization_id},
        after={'assignment_change_id': row.assignment_change_id, 'vehicle_id': vehicle.vehicle_id,
               'vehicle_version': row.vehicle_version_after, 'organization_id': row.after_organization_id,
               'state': 'assigned' if after else 'unassigned', 'human_acknowledged': True,
               'reason_sha256': sha256(payload.reason.encode()).hexdigest(),
               'source_evidence_sha256': sha256(payload.source_evidence.encode()).hexdigest()})
    return {'vehicle_version': row.vehicle_version_after, 'current': current_dict(db, row), 'change': change_dict(row)}
