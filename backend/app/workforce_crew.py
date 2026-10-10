"""Read-only crew admission, coherent capture and fresh private release.

This guard changes no assignments, grants, approvals, pay or dispatch decisions.
"""
from fastapi import HTTPException
from sqlalchemy import select, or_

from .db import Base
from .models import Document, Employee
from .personnel import OrganizationUnit, EmployeeAssignment
from .workforce_models import (
    WorkforceRosterEntry, WorkforceEmployeeQualification, WorkforceShiftType,
    WorkforceLeaveEntry,
)
from . import workforce_service as service
from . import statistics_service as boundary
from .statistics_sources import digest, row_evidence, row_id
from .workforce_source import current_source, original_rights
from .inquiries_service import document_permissions

BASE_RIGHTS = {'workforce.read', 'personnel.read'}


def depend(evidence, row):
    if row is not None:
        # Match Core ownership-edge evidence regardless of which traversal
        # visits the same record last. Version is already in the content hash.
        evidence[row.__tablename__ + ':' + row_id(row)] = {
            'table': row.__tablename__, 'content_hash': row_evidence(row)['content_hash']}


def source_evidence(db, kind, key, evidence, visited):
    from .inquiries_service import SOURCES
    from .finance_models import ProcurementEvent
    from .models import ContractDocument, LegalSourceDocumentVersion
    node = (kind, key)
    if node in visited:
        return
    visited.add(node)
    definition = SOURCES.get(kind)
    row = db.get(ProcurementEvent, key) if kind == 'finance_event' else db.get(definition[0], key) if definition else None
    if row is None:
        raise HTTPException(403, 'Crew original authority is unavailable')
    if kind == 'document':
        document_evidence(db, row, evidence, visited)
        return
    depend(evidence, row)
    for column in row.__table__.columns:
        if any(f.target_fullname == 'documents.document_id' for f in column.foreign_keys):
            value = getattr(row, column.name)
            if value:
                document = db.get(Document, value, populate_existing=True)
                if document is None:
                    raise HTTPException(403, 'Crew original authority is unavailable')
                document_evidence(db, document, evidence, visited)
    edges = []
    if kind in ('finance', 'finance_event'):
        if row.contract_case_id:
            edges.append(('contract', row.contract_case_id))
        if kind == 'finance':
            edges.extend(('finance', value) for value in (row.commitment_id, row.reverses_id) if value)
            if row.invoice_id:
                edges.append(('finance_event', row.invoice_id))
        elif row.related_event_id:
            edges.append(('finance_event', row.related_event_id))
    if kind == 'contract':
        for link in db.scalars(select(ContractDocument).where(ContractDocument.contract_case_id == key)):
            depend(evidence, link)
            edges.append(('document', link.document_id))
    if kind == 'incident':
        edges.extend((source, value) for source, value in (('emergency', row.emergency_case_id), ('fire', row.fire_investigation_case_id)) if value)
    if kind == 'legal':
        revision = db.scalar(select(LegalSourceDocumentVersion).where(LegalSourceDocumentVersion.legal_source_document_id == key).order_by(LegalSourceDocumentVersion.retrieved_at.desc(), LegalSourceDocumentVersion.legal_source_document_version_id).limit(1))
        if revision:
            depend(evidence, revision)
            if revision.raw_document_id:
                edges.append(('document', revision.raw_document_id))
    for source, identity in edges:
        source_evidence(db, source, identity, evidence, visited)


def document_evidence(db, document, evidence, visited):
    """Pin original metadata and incoming permission-bearing ownership edges.

    Existing document_permissions owns authorization; this only pins its input
    edges so relinking ownership cannot silently reuse a previously admitted
    original. Hashes stay private and are never returned to the client.
    """
    if document.document_id in visited:
        return
    visited.add(document.document_id)
    depend(evidence, document)
    for table in Base.metadata.tables.values():
        if table.name.startswith('inquiry_'):
            continue
        columns = [column for column in table.columns
                   if any(f.target_fullname == 'documents.document_id' for f in column.foreign_keys)]
        if not columns:
            continue
        for row in db.execute(select(table).where(or_(*(c == document.document_id for c in columns)))).mappings():
            key = table.name + ':' + ':'.join(str(row[c.name]) for c in table.primary_key)
            evidence[key] = {'table': table.name, 'content_hash': digest(dict(row))}
    # Derived inquiry originals depend on their current template, provenance and
    # linked evidence. Walk their document edges with cycle protection.
    from .inquiries_models import Inquiry, InquiryRenderedForm, InquiryEvidence
    from .models import FormTemplate
    inquiries = list(db.scalars(select(Inquiry)))
    selected = {row.inquiry_id: row for row in inquiries
                if row.provenance.get('source_document_id') == document.document_id}
    linked_documents = set()
    for rendered in db.scalars(select(InquiryRenderedForm).where(InquiryRenderedForm.document_id == document.document_id)):
        depend(evidence, rendered)
        inquiry = db.get(Inquiry, rendered.inquiry_id)
        if inquiry is None:
            raise HTTPException(403, 'Crew original authority is unavailable')
        selected[inquiry.inquiry_id] = inquiry
        if rendered.manifest.get('template_document_id'):
            linked_documents.add(rendered.manifest['template_document_id'])
        template = db.get(FormTemplate, rendered.form_template_id)
        if template is None:
            raise HTTPException(403, 'Crew original authority is unavailable')
        depend(evidence, template)
        linked_documents.add(template.document_id)
    for inquiry in selected.values():
        depend(evidence, inquiry)
        if inquiry.provenance.get('source_document_id'):
            linked_documents.add(inquiry.provenance['source_document_id'])
        links = list(inquiry.provenance.get('security_sources', []))
        for edge in db.scalars(select(InquiryEvidence).where(InquiryEvidence.inquiry_id == inquiry.inquiry_id)):
            depend(evidence, edge)
            links.append({'source_type': edge.source_type, 'source_id': edge.source_id, **edge.snapshot})
        for link in links:
            linked_documents.update(d['document_id'] for d in link.get('documents', []))
            source_evidence(db, link['source_type'], link['source_id'], evidence, visited)
    for key in linked_documents:
        linked = db.get(Document, key, populate_existing=True)
        if linked is None:
            raise HTTPException(403, 'Crew original authority is unavailable')
        document_evidence(db, linked, evidence, visited)


def require_original(db, user, key, evidence, rights, visited):
    if key is None:
        return
    document = db.get(Document, key, populate_existing=True)
    if document is None:
        raise HTTPException(403, 'Crew original authority is unavailable')
    required = document_permissions(db, document)
    service.need(db, user, *required)
    rights.update(required)
    document_evidence(db, document, evidence, visited)


def capture(db, identity, on_date, organization_id=None, shift_type_id=None, *, project=True):
    user = boundary.authorize(db, identity, BASE_RIGHTS)
    evidence = {}
    rights = set(BASE_RIGHTS)
    visited = set()
    query = select(WorkforceRosterEntry, Employee).join(Employee, Employee.employee_id == WorkforceRosterEntry.employee_id).where(
        WorkforceRosterEntry.work_date == on_date, WorkforceRosterEntry.status == 'approved', Employee.active.is_(True))
    if organization_id:
        query = query.where(WorkforceRosterEntry.organization_id == organization_id)
    if shift_type_id:
        query = query.where(WorkforceRosterEntry.shift_type_id == shift_type_id)
    for roster, employee in db.execute(query).all():
        depend(evidence, roster)
        depend(evidence, employee)
        depend(evidence, db.get(OrganizationUnit, roster.organization_id))
        depend(evidence, db.get(WorkforceShiftType, roster.shift_type_id))
        depend(evidence, service.effective_assignment(db, roster.employee_id, roster.work_date))
        depend(evidence, db.get(EmployeeAssignment, roster.assignment_id) if roster.assignment_id else None)
        leaves = db.scalars(select(WorkforceLeaveEntry).where(
            WorkforceLeaveEntry.employee_id == employee.employee_id,
            WorkforceLeaveEntry.status == 'approved', WorkforceLeaveEntry.kind == 'use',
            WorkforceLeaveEntry.leave_start_at < roster.ends_at, WorkforceLeaveEntry.leave_end_at > roster.starts_at)).all()
        for leave in leaves:
            depend(evidence, leave)
        if not service.current_roster_evidence(db, roster):
            continue
        if service.approved_leave_overlaps(db, employee.employee_id, roster.starts_at, roster.ends_at):
            continue
        try:
            current_source(db, user, 'roster', roster.roster_entry_id)
        except HTTPException as error:
            if error.status_code == 404:
                raise HTTPException(403, 'Crew original authority is unavailable') from None
            raise
        rights.update(original_rights(db, roster))
        require_original(db, user, roster.document_id, evidence, rights, visited)
        qualifications = db.scalars(select(WorkforceEmployeeQualification).where(
            WorkforceEmployeeQualification.employee_id == employee.employee_id,
            WorkforceEmployeeQualification.active.is_(True), WorkforceEmployeeQualification.valid_from <= on_date,
            or_(WorkforceEmployeeQualification.valid_to.is_(None), WorkforceEmployeeQualification.valid_to >= on_date))).all()
        for qualification in qualifications:
            depend(evidence, qualification)
            require_original(db, user, qualification.document_id, evidence, rights, visited)
    # Existing eligibility/projection remains the source of the wire contract.
    # All admitted originals have been checked before this private projection.
    items = service.available_crew(db, on_date, organization_id, shift_type_id) if project else None
    return {'items': items, 'rights': sorted(rights), 'fingerprint': digest(evidence)}


def available_crew(db, user, on_date, organization_id=None, shift_type_id=None):
    identity = boundary.preflight(db, user, BASE_RIGHTS)
    with boundary.bound_transaction(identity, capture=True) as snapshot:
        captured = capture(snapshot, identity, on_date, organization_id, shift_type_id)
    with boundary.final_session(identity, captured['rights']) as final:
        current = capture(final, identity, on_date, organization_id, shift_type_id, project=False)
        if current['fingerprint'] != captured['fingerprint'] or current['rights'] != captured['rights']:
            raise HTTPException(409, 'Crew source changed while preparing the response; reload')
        # Recheck fresh current authority after all source reads, including rights
        # newly required by a changed original closure, before private release.
        boundary.authorize(final, identity, current['rights'])
    return captured['items']
