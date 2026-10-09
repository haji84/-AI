"""Current source lineage for separately authorized, read-only workforce details."""
from uuid import UUID
from fastapi import HTTPException
from .authz import revalidate_session, permission_codes, current_user
from .models import Document, Employee
from .inquiries_service import document_permissions
from .statistics_sources import require_workforce_available
from .workforce_models import WorkforceRosterEntry, WorkforceAttendance, WorkforceTimeEntry
from . import workforce_service as service

MODELS = {'roster':WorkforceRosterEntry, 'attendance':WorkforceAttendance, 'time':WorkforceTimeEntry}


def source_lineage(db, row):
    attendance = row if isinstance(row, WorkforceAttendance) else None
    if isinstance(row, WorkforceTimeEntry) and row.attendance_id:
        attendance = db.get(WorkforceAttendance, row.attendance_id, populate_existing=True)
        if attendance is None: raise HTTPException(409, 'Linked workforce attendance is unavailable')
    roster = row if isinstance(row, WorkforceRosterEntry) else None
    if attendance and attendance.roster_entry_id:
        roster = db.get(WorkforceRosterEntry, attendance.roster_entry_id, populate_existing=True)
        if roster is None: raise HTTPException(409, 'Linked workforce roster is unavailable')
    return attendance, roster


def original_rights(db, row):
    _, roster = source_lineage(db, row)
    required = set()
    if roster and roster.document_id:
        document = db.get(Document, roster.document_id, populate_existing=True)
        if document is None: raise HTTPException(403, 'Workforce source original is unavailable')
        required.update(document_permissions(db, document))
    return required


def current_source(db, user, kind, key):
    # Baseline and module authority precede UUID/record existence lookup.
    revalidate_session(db, user.user_id)
    current_user(user)
    service.need(db, user, 'workforce.read', 'personnel.read')
    require_workforce_available(db)
    if kind not in MODELS: raise HTTPException(404, 'Workforce source not found')
    try: key = str(UUID(key))
    except (ValueError, TypeError): raise HTTPException(404, 'Workforce source not found') from None
    row = db.get(MODELS[kind], key, populate_existing=True)
    if row is None: raise HTTPException(404, 'Workforce source not found')
    try:
        required = original_rights(db, row)
    except HTTPException as error:
        if error.status_code not in (403,409): raise
        raise HTTPException(404, 'Workforce source not found') from None
    if not required.issubset(permission_codes(db, user.user_id)):
        raise HTTPException(404, 'Workforce source not found')
    return row


def source_payload(db, row, kind):
    key = getattr(row, list(row.__table__.primary_key)[0].name)
    employee = db.get(Employee, row.employee_id, populate_existing=True)
    if employee is None: raise HTTPException(409, 'Historical employee record is unavailable')
    return {'kind':kind, 'record_id':key, 'version':row.version,
            'required_permissions':sorted({'workforce.read','personnel.read',*original_rights(db,row)}),
            'employee':{'employee_id':employee.employee_id, 'display_name':employee.display_name, 'active':employee.active},
            'record':service.row_dict(row), 'formal_salary_decision':False}
