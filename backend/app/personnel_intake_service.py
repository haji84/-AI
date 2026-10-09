"""Exact-code proposals, evidence revalidation and atomic Human application."""
from hashlib import sha256
import json
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update

from .models import Document, Employee, now_utc
from .personnel import OrganizationUnit, EmployeeAssignment, HumanRoleRule
from .personnel_intake_models import PersonnelDocumentProposal
from .personnel_intake_schemas import NoticeFields
from .document_intake import extract_document, _storage_path, MAX_DOCUMENT_BYTES
from .inquiries_service import need, guard_document
from .audit import write_audit
from .routers import administration

MAX_PREVIEW = 32000


def exact_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('ambiguous repeated notice field')
        result[key] = value
    return result


def output(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def original(db, actor, document_id, expected_hash=None):
    need(db, actor, 'personnel.read', 'document.read')
    doc = db.get(Document, str(document_id), populate_existing=True)
    if doc is None:
        raise HTTPException(404, 'notice original unavailable')
    if doc.document_type != 'personnel_notice':
        raise HTTPException(422, 'protected personnel_notice original required')
    guard_document(db, actor, doc)
    try:
        path = _storage_path(doc)
        if not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError('unavailable or oversized original')
        digest = sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except (OSError, ValueError):
        raise HTTPException(409, 'notice original integrity unavailable') from None
    if digest.hexdigest() != doc.sha256 or (expected_hash is not None and doc.sha256 != expected_hash):
        raise HTTPException(409, 'notice original changed')
    return doc


def resolve(db, proposed):
    errors = []
    try:
        values = NoticeFields.model_validate(proposed)
    except ValidationError as exc:
        return {}, {}, ['unsupported or invalid notice fields: '+','.join('.'.join(map(str, e['loc'])) for e in exc.errors())]
    employee = db.scalar(select(Employee).where(Employee.employee_code == values.employee_code).execution_options(populate_existing=True))
    organization = db.scalar(select(OrganizationUnit).where(OrganizationUnit.code == values.organization_code).execution_options(populate_existing=True))
    if employee is None or not employee.active:
        errors.append('unknown or inactive employee_code')
    if organization is None or not organization.active:
        errors.append('unknown or inactive organization_code')
    known = (db.scalar(select(Employee.employee_id).where(Employee.title == values.title).limit(1)) is not None
        or db.scalar(select(EmployeeAssignment.assignment_id).where(EmployeeAssignment.title == values.title).limit(1)) is not None
        or db.scalar(select(HumanRoleRule.rule_id).where(HumanRoleRule.title == values.title).limit(1)) is not None)
    if not known:
        errors.append('unknown title; no code inference permitted')
    if errors:
        return {}, {}, errors
    rows = db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.employee_id == employee.employee_id)
        .order_by(EmployeeAssignment.assignment_id).execution_options(populate_existing=True)).all()
    before = {'employee_id': employee.employee_id, 'employee_version': employee.version,
        'display_name': employee.display_name, 'assignments': [
            {'assignment_id': row.assignment_id, 'version': row.version, 'organization_id': row.organization_id,
             'title': row.title, 'kind': row.kind, 'valid_from': row.valid_from.isoformat(),
             'valid_to': row.valid_to.isoformat() if row.valid_to else None} for row in rows]}
    after = {**values.model_dump(mode='json'), 'employee_id': employee.employee_id,
        'organization_id': organization.organization_id, 'organization_version': organization.version,
        'organization_name': organization.name, 'role_ids': []}
    return before, after, []


def audit(db, actor, action, row):
    # Audit-only access must not disclose notice prose, names or Human reasons.
    write_audit(db, user_id=actor.user_id, action='personnel.intake.'+action,
        entity_type=row.__tablename__, entity_id=row.proposal_id, after={
            'status': row.status, 'version': row.version, 'source_document_id': row.source_document_id,
            'source_sha256': row.source_sha256, 'applied_assignment_id': row.applied_assignment_id,
            'reason_sha256': sha256(row.reason.encode()).hexdigest()})


def get(db, actor, key, locked=False):
    need(db, actor, 'personnel.read', 'document.read')
    statement = select(PersonnelDocumentProposal).where(PersonnelDocumentProposal.proposal_id == str(key))
    if locked:
        statement = statement.with_for_update()
    row = db.scalar(statement.execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, 'notice candidate unavailable')
    original(db, actor, row.source_document_id, row.source_sha256)
    return row


def create(db, actor, document_id):
    need(db, actor, 'personnel.manage')
    doc = original(db, actor, document_id)
    descriptor = {key: getattr(doc, key) for key in ('document_id','sha256','storage_path','original_filename','mime_type','document_type')}
    # Extraction/OCR may be slow. Hold neither the account advisory lock nor
    # a read transaction while it executes, then reauthorize before any write.
    db.rollback()
    try:
        text, method, _, _ = extract_document(SimpleNamespace(**descriptor))
    except (OSError, ValueError):
        raise HTTPException(422, 'notice extraction unavailable') from None
    if len(text) > MAX_PREVIEW:
        raise HTTPException(422, 'notice exceeds bounded preview; split and verify original first')
    try:
        proposed = json.loads(text, object_pairs_hook=exact_fields)
        if not isinstance(proposed, dict):
            proposed = {}
    except (ValueError, TypeError):
        proposed = {}
    administration.administration_lock(db, actor, 'personnel.manage')
    doc = original(db, actor, document_id, descriptor['sha256'])
    if any(getattr(doc, key) != value for key, value in descriptor.items()):
        raise HTTPException(409, 'notice extraction descriptor changed')
    before, after, errors = resolve(db, proposed)
    row = PersonnelDocumentProposal(source_document_id=doc.document_id, source_sha256=doc.sha256,
        source_text=text, source_quote=text, extraction_method=method, proposed=proposed, errors=errors,
        before_snapshot=before, after_snapshot=after, employee_id=after.get('employee_id'),
        organization_id=after.get('organization_id'), created_by=actor.user_id)
    db.add(row); db.flush(); audit(db, actor, 'create', row)
    original(db, actor, row.source_document_id, row.source_sha256)
    administration.commit(db)
    return output(row)


def change(db, row, expected_version, values):
    changed = db.execute(update(PersonnelDocumentProposal).where(
        PersonnelDocumentProposal.proposal_id == row.proposal_id, PersonnelDocumentProposal.version == expected_version)
        .values(**values, version=expected_version+1)).rowcount
    if changed != 1:
        raise HTTPException(409, 'notice candidate version changed')
    db.refresh(row)


def patch(db, actor, key, payload):
    administration.administration_lock(db, actor, 'personnel.manage')
    row = get(db, actor, key, locked=True)
    if row.status != 'candidate':
        raise HTTPException(409, 'only unapplied candidate may be revised')
    if payload.source_quote not in row.source_text or not payload.source_quote.strip():
        raise HTTPException(422, 'exact original extraction quote required')
    proposed = payload.proposed.model_dump(mode='json')
    before, after, errors = resolve(db, proposed)
    change(db, row, payload.expected_version, dict(proposed=proposed, source_quote=payload.source_quote,
        before_snapshot=before, after_snapshot=after, errors=errors, employee_id=after.get('employee_id'),
        organization_id=after.get('organization_id'), reason=payload.reason))
    audit(db, actor, 'revise', row); administration.commit(db)
    return output(row)


def decision(db, actor, key, payload, action):
    administration.administration_lock(db, actor, 'personnel.manage')
    row = get(db, actor, key, locked=True)
    if row.version != payload.expected_version:
        raise HTTPException(409, 'notice candidate version changed')
    if action == 'reject':
        if row.status not in ('candidate', 'reviewed'):
            raise HTTPException(409, 'notice candidate already final')
        values = dict(status='rejected', reason=payload.reason)
    else:
        expected_status = 'candidate' if action == 'review' else 'reviewed'
        if row.status != expected_status:
            raise HTTPException(409, 'separate Human review and apply required')
        before, after, errors = resolve(db, row.proposed)
        if errors or row.errors:
            raise HTTPException(422, 'unknown notice codes must be resolved by Human')
        if before != row.before_snapshot or after != row.after_snapshot:
            raise HTTPException(409, 'notice personnel or organization evidence changed')
        if action == 'review':
            values = dict(status='reviewed', reason=payload.reason, reviewed_by=actor.user_id, reviewed_at=now_utc())
        else:
            fields = NoticeFields.model_validate(row.proposed)
            payload_assignment = administration.AssignmentInput(expected_version=before['employee_version'],
                organization_id=after['organization_id'], title=fields.title, kind=fields.kind,
                valid_from=fields.valid_from, valid_to=fields.valid_to, role_ids=[],
                reason='Human personnel notice '+row.proposal_id+'; reason_sha256='+sha256(payload.reason.encode()).hexdigest())
            assigned = administration.assign(db, actor, before['employee_id'], payload_assignment,
                transfer=fields.mode == 'transfer', commit_result=False)
            administration.retain_administrator(db)
            values = dict(status='applied', reason=payload.reason, applied_by=actor.user_id,
                applied_at=now_utc(), applied_assignment_id=assigned['assignment_id'])
    change(db, row, payload.expected_version, values)
    original(db, actor, row.source_document_id, row.source_sha256)
    audit(db, actor, action, row); administration.commit(db)
    return output(row)
