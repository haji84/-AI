"""Source-backed Human register; confirmation verifies evidence, never legal compliance."""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from .audit import write_audit
from .authz import permission_codes
from .hazardous_models import HazardousHistory, HazardousInstallation, HazardousRecord
from .inquiries_service import document_permissions, guard_document
from .models import (Document, Facility, FeatureFlag, Inspection, InspectionFinding, LegalRuleVersion, LegalSource,
                     LegalSourceDocument, LegalSourceDocumentVersion, now_utc, uuid_str)
from .settings import settings
from .violation_models import ViolationCase


RECORD_FIELDS = ('kind', 'title', 'reference_no', 'recorded_on', 'due_on', 'notes', 'document_ids',
                 'legal_source_version_ids', 'inspection_ids', 'violation_case_ids')


def need(db, user, *codes):
    if not set(codes) <= permission_codes(db, user.user_id):
        raise HTTPException(403, 'source/transition permission unavailable')


def authority(db, user):
    need(db, user, 'hazardous.read', 'facility.read')
    flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.hazardous_materials.enabled'))
    if (flag is None and settings.production_mode) or (flag is not None and not flag.enabled):
        raise HTTPException(503, 'hazardous materials module disabled')


def get(db, model, key, lock=False):
    try:
        key = str(UUID(key))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'invalid source/record UUID') from None
    statement = select(model).where(list(model.__table__.primary_key.columns)[0] == key).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise HTTPException(404, 'hazardous source/record not found')
    return row


def serial(row):
    def value(item):
        if isinstance(item, datetime):
            return (item if item.tzinfo else item.replace(tzinfo=timezone.utc)).isoformat()
        return item.isoformat() if isinstance(item, date) else deepcopy(item)
    return {column.name: value(getattr(row, column.name)) for column in row.__table__.columns}


def bump(db, row, expected, values):
    if row.version != expected:
        raise HTTPException(409, 'record version changed')
    key = list(row.__table__.primary_key.columns)[0]
    result = db.execute(update(type(row)).where(key == getattr(row, key.name), type(row).version == expected)
                        .values(**values, version=expected + 1, updated_at=now_utc()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, 'concurrent record change')
    db.refresh(row)
    return row


def history(db, user, row, action, reason, before=None):
    after = serial(row)
    db.add(HazardousHistory(installation_id=row.installation_id,
                           record_id=row.record_id if isinstance(row, HazardousRecord) else None,
                           action=action, reason=reason, before=before, after=after, created_by=user.user_id))
    # audit.read does not grant hazardous/source access. Full facts and identifiers
    # remain in the guarded append-only domain history, not in the generic log.
    def metadata(value):
        return {'schema_version': 'hazardous-audit-v1',
                'change_sha256': sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()}
    write_audit(db, user_id=user.user_id, action='hazardous.' + action, entity_type=row.__tablename__,
                entity_id=None, before=metadata(before) if before is not None else None, after=metadata(after))
    db.flush()


def document_access(db, user, identity, lock=False):
    need(db, user, 'document.read')
    doc = get(db, Document, identity, lock)
    guard_document(db, user, doc)
    need(db, user, *document_permissions(db, doc))
    return doc


def document_snapshot(db, user, identity, lock=False):
    doc = document_access(db, user, identity, lock)
    root = Path(settings.storage_root).resolve()
    path = (root / doc.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(409, 'original missing or outside managed storage')
    digest = sha256()
    try:
        with path.open('rb') as original:
            for part in iter(lambda: original.read(1024 * 1024), b''):
                digest.update(part)
    except OSError:
        raise HTTPException(409, 'original unavailable') from None
    if digest.hexdigest() != doc.sha256:
        raise HTTPException(409, 'original hash changed')
    return {'document_id': doc.document_id, 'sha256': doc.sha256, 'filename': doc.original_filename,
            'required_permissions': sorted(document_permissions(db, doc))}


def legal_access(db, user, identity, lock=False):
    need(db, user, 'legal_source.read', 'document.read')
    version = get(db, LegalSourceDocumentVersion, identity, lock)
    document = get(db, LegalSourceDocument, version.legal_source_document_id, lock)
    source = get(db, LegalSource, document.legal_source_id, lock)
    if version.raw_document_id:
        document_access(db, user, version.raw_document_id, lock)
    return version, document, source


def legal_snapshot(db, user, identity, lock=False):
    version, document, source = legal_access(db, user, identity, lock)
    if not source.enabled or not version.raw_document_id or not version.source_url:
        raise HTTPException(409, 'versioned legal source with original and URL required')
    original = document_snapshot(db, user, version.raw_document_id, lock)
    if original['sha256'] != version.sha256:
        raise HTTPException(409, 'legal version/original hash mismatch')
    return {'legal_source_version_id': version.legal_source_document_version_id,
            'legal_source_document_id': document.legal_source_document_id, 'legal_source_id': source.legal_source_id,
            'sha256': version.sha256, 'source_url': version.source_url, 'version_label': version.version_label,
            'effective_from': str(version.effective_from) if version.effective_from else None,
            'effective_to': str(version.effective_to) if version.effective_to else None,
            'title': document.title, 'trust_level': source.trust_level, 'original': original}


def violation_access(db, user, identity, lock=False):
    need(db, user, 'violation.read')
    row = get(db, ViolationCase, identity, lock)
    if row.finding_id:
        need(db, user, 'inspection.read')
    for identity in sorted(set(row.evidence_document_ids + row.procedure_document_ids)):
        document_access(db, user, identity, lock)
    for identity in sorted(set(row.rule_version_ids)):
        need(db, user, 'legal_rule.read', 'legal_source.read')
        rule = get(db, LegalRuleVersion, identity, lock)
        if rule.source_legal_document_version_id:
            legal_access(db, user, rule.source_legal_document_version_id, lock)
    return row


def violation_snapshot(db, user, row, lock=False):
    rules = []
    for identity in sorted(set(row.rule_version_ids)):
        rule = get(db, LegalRuleVersion, identity, lock)
        rules.append({'rule_version_id': identity, 'version': rule.version, 'status': rule.status,
                      'legal_source': legal_snapshot(db, user, rule.source_legal_document_version_id, lock)
                      if rule.source_legal_document_version_id else None})
    finding = None
    if row.finding_id:
        source = get(db, InspectionFinding, row.finding_id, lock)
        inspected = get(db, Inspection, source.inspection_id, lock)
        if inspected.building_id != row.building_id:
            raise HTTPException(409, 'linked violation finding belongs to another building')
        finding = {'finding_id': source.finding_id, 'version': source.version,
                   'inspection_id': inspected.inspection_id, 'inspection_version': inspected.version}
    return {'case_id': row.case_id, 'version': row.version, 'status': row.status, 'finding': finding, 'rules': rules,
            'documents': [document_snapshot(db, user, identity, lock)
                          for identity in sorted(set(row.evidence_document_ids + row.procedure_document_ids))]}


def visible_sources(db, user, data):
    """Check current and historical source references before returning any row or count."""
    if isinstance(data, list):
        for value in data:
            visible_sources(db, user, value)
    elif isinstance(data, dict):
        if data.get('required_permissions'):
            need(db, user, *data['required_permissions'])
        documents = data.get('document_ids', []) + ([data['document_id']] if data.get('document_id') else [])
        for identity in documents:
            document_access(db, user, identity)
        versions = data.get('legal_source_version_ids', []) + ([data['legal_source_version_id']] if data.get('legal_source_version_id') else [])
        for identity in versions:
            legal_access(db, user, identity)
        if data.get('inspection_ids') or data.get('inspection_id'):
            need(db, user, 'inspection.read')
        if data.get('rule_version_id'):
            need(db, user, 'legal_rule.read', 'legal_source.read')
        for identity in data.get('violation_case_ids', []):
            violation_access(db, user, identity)
        if data.get('case_id'):
            violation_access(db, user, data['case_id'])
        for value in data.values():
            if isinstance(value, (dict, list)):
                visible_sources(db, user, value)


def can_see(db, user, data):
    try:
        visible_sources(db, user, data)
        return True
    except HTTPException as error:
        if error.status_code in (403, 404):
            return False
        raise


def require_record_visibility(db, user, row):
    visible_sources(db, user, serial(row))
    # Revision lineage itself is evidence: don't expose a hidden predecessor ID.
    seen = set()
    previous = row.supersedes_record_id
    while previous and previous not in seen:
        seen.add(previous)
        ancestor = get(db, HazardousRecord, previous)
        visible_sources(db, user, serial(ancestor))
        previous = ancestor.supersedes_record_id


def record_is_visible(db, user, row):
    try:
        require_record_visibility(db, user, row)
        return True
    except HTTPException as error:
        if error.status_code in (403, 404):
            return False
        raise


def installation(db, user, identity, expected=None):
    authority(db, user)
    row = get(db, HazardousInstallation, identity, expected is not None)
    facility = get(db, Facility, row.building_id, expected is not None)
    if expected is not None:
        if row.version != expected:
            raise HTTPException(409, 'installation version changed')
        if row.status != 'active' or facility.status != 'active' or facility.deleted_at:
            raise HTTPException(409, 'active installation and facility required')
    return row


def snapshot(db, user, parent, row, lock=False, record_version=None):
    facility = get(db, Facility, parent.building_id, lock)
    if facility.status != 'active' or facility.deleted_at or parent.status != 'active':
        raise HTTPException(409, 'active installation and facility required')
    inspections = []
    for identity in sorted(set(row.inspection_ids)):
        need(db, user, 'inspection.read')
        source = get(db, Inspection, identity, lock)
        if source.building_id != parent.building_id:
            raise HTTPException(409, 'inspection belongs to another building')
        inspections.append({'inspection_id': source.inspection_id, 'version': source.version, 'status': source.status})
    violations = []
    for identity in sorted(set(row.violation_case_ids)):
        source = violation_access(db, user, identity, lock)
        if source.building_id != parent.building_id:
            raise HTTPException(409, 'violation belongs to another building')
        violations.append(violation_snapshot(db, user, source, lock))
    documents = []
    for identity in sorted(set(row.document_ids)):
        doc = document_access(db, user, identity, lock)
        if doc.building_id and doc.building_id != parent.building_id:
            raise HTTPException(409, 'original belongs to another building')
        documents.append(document_snapshot(db, user, identity, lock))
    facts = serial(row)
    return {'record': {'record_id': row.record_id, 'version': row.version if record_version is None else record_version},
            'installation': {'installation_id': parent.installation_id, 'version': parent.version,
                             'name': parent.name, 'category_label': parent.category_label,
                             'location_detail': parent.location_detail, 'notes': parent.notes, 'materials': deepcopy(parent.materials)},
            'facility': {'building_id': facility.building_id, 'version': facility.version},
            'record_facts': {key: facts[key] for key in RECORD_FIELDS},
            'documents': documents,
            'legal_sources': [legal_snapshot(db, user, identity, lock) for identity in sorted(set(row.legal_source_version_ids))],
            'inspections': inspections, 'violations': violations}


def choice(db, user, kind, row):
    if kind == 'facilities':
        return {'id': row.building_id, 'label': row.name}
    if kind == 'documents':
        document_access(db, user, row.document_id)
        return {'id': row.document_id, 'label': row.original_filename, 'sha256': row.sha256}
    if kind == 'legal':
        version, document, _ = legal_access(db, user, row.legal_source_document_version_id)
        return {'id': version.legal_source_document_version_id, 'label': document.title + ' / ' + (version.version_label or version.sha256[:12]), 'sha256': version.sha256, 'source_url': version.source_url, 'raw_document_id': version.raw_document_id}
    if kind == 'inspections':
        need(db, user, 'inspection.read')
        return {'id': row.inspection_id, 'label': f'{row.inspected_at} / {row.inspection_type} / {row.status}'}
    violation_access(db, user, row.case_id)
    return {'id': row.case_id, 'label': row.possible_issue}


def record_dict(db, user, parent, row):
    require_record_visibility(db, user, row)
    data = serial(row)
    data['confirmation_current'] = False
    if row.status == 'confirmed':
        try:
            data['confirmation_current'] = snapshot(db, user, parent, row) == row.source_snapshot
        except HTTPException as error:
            if error.status_code not in (404, 409):
                raise
    data['sources'] = {
        'documents': [choice(db, user, 'documents', get(db, Document, key)) for key in row.document_ids],
        'legal': [choice(db, user, 'legal', get(db, LegalSourceDocumentVersion, key)) for key in row.legal_source_version_ids],
        'inspections': [choice(db, user, 'inspections', get(db, Inspection, key)) for key in row.inspection_ids],
        'violations': [choice(db, user, 'violations', get(db, ViolationCase, key)) for key in row.violation_case_ids],
    }
    return data


def installation_dict(db, row):
    return {**serial(row), 'building_name': get(db, Facility, row.building_id).name}


def list_installations(db, user, q='', building_id=None, status=None, limit=100, offset=0):
    authority(db, user)
    statement = select(HazardousInstallation).join(Facility, HazardousInstallation.building_id == Facility.building_id)
    if q:
        statement = statement.where(or_(HazardousInstallation.name.contains(q), HazardousInstallation.category_label.contains(q), HazardousInstallation.location_detail.contains(q)))
    if building_id:
        statement = statement.where(HazardousInstallation.building_id == str(UUID(building_id)))
    if status:
        statement = statement.where(HazardousInstallation.status == status)
    return [installation_dict(db, row) for row in db.scalars(statement.order_by(HazardousInstallation.created_at.desc(), HazardousInstallation.installation_id).offset(offset).limit(limit))]


def detail(db, user, identity):
    row = installation(db, user, identity)
    data = installation_dict(db, row)
    records = db.scalars(select(HazardousRecord).where(HazardousRecord.installation_id == identity).order_by(HazardousRecord.created_at, HazardousRecord.record_id))
    data['evidence_records'] = [record_dict(db, user, row, record) for record in records if record_is_visible(db, user, record)]
    events = db.scalars(select(HazardousHistory).where(HazardousHistory.installation_id == identity).order_by(HazardousHistory.created_at, HazardousHistory.history_id))
    data['history'] = [serial(event) for event in events if can_see(db, user, serial(event)) and (not event.record_id or record_is_visible(db, user, get(db, HazardousRecord, event.record_id)))]
    return data


def create_installation(db, user, payload):
    authority(db, user)
    facility = get(db, Facility, payload.building_id, True)
    if facility.status != 'active' or facility.deleted_at:
        raise HTTPException(409, 'active facility required')
    row = HazardousInstallation(**payload.model_dump(), created_by=user.user_id)
    db.add(row)
    db.flush()
    history(db, user, row, 'installation.create', 'Human register entry')
    return row


def patch_installation(db, user, identity, payload, retire=False):
    row = installation(db, user, identity, payload.expected_version)
    before = serial(row)
    values = {'status': 'retired'} if retire else payload.model_dump(exclude={'expected_version', 'reason'}, exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(422, 'installation fields cannot be null')
    bump(db, row, payload.expected_version, values)
    history(db, user, row, 'installation.retire' if retire else 'installation.update', payload.reason, before)
    return row


def record_child(db, user, parent, identity, expected):
    row = get(db, HazardousRecord, identity, True)
    if row.installation_id != parent.installation_id:
        raise HTTPException(404, 'record not found')
    require_record_visibility(db, user, row)
    if row.version != expected:
        raise HTTPException(409, 'record version changed')
    return row


def create_record(db, user, identity, payload):
    parent = installation(db, user, identity, payload.expected_installation_version)
    row = HazardousRecord(**payload.model_dump(exclude={'expected_installation_version'}), installation_id=parent.installation_id,
                          record_id=uuid_str(), version=1, status='draft', created_by=user.user_id)
    row.source_snapshot = snapshot(db, user, parent, row, True)
    db.add(row)
    db.flush()
    history(db, user, row, 'record.create', 'Human evidence entry')
    return parent, row


def patch_record(db, user, identity, record_id, payload):
    parent = installation(db, user, identity, payload.expected_installation_version)
    row = record_child(db, user, parent, record_id, payload.expected_version)
    if row.status != 'draft':
        raise HTTPException(409, 'confirmed evidence is immutable; create a revision')
    values = payload.model_dump(exclude={'expected_installation_version', 'expected_version', 'reason'}, exclude_unset=True)
    if any(value is None and key not in ('reference_no', 'due_on') for key, value in values.items()):
        raise HTTPException(422, 'required record fields cannot be null')
    before = serial(row)
    candidate = HazardousRecord(**{column.name: deepcopy(getattr(row, column.name)) for column in row.__table__.columns})
    for key, value in values.items():
        setattr(candidate, key, value)
    candidate.version = payload.expected_version + 1
    values['source_snapshot'] = snapshot(db, user, parent, candidate, True)
    bump(db, row, payload.expected_version, values)
    history(db, user, row, 'record.update', payload.reason, before)
    return parent, row


def record_action(db, user, identity, record_id, payload, action):
    parent = installation(db, user, identity, payload.expected_installation_version)
    row = record_child(db, user, parent, record_id, payload.expected_version)
    before = serial(row)
    if action == 'revisions':
        if row.status != 'confirmed':
            raise HTTPException(409, 'only current confirmed evidence can be revised')
        data = {key: deepcopy(getattr(row, key)) for key in RECORD_FIELDS}
        revised = HazardousRecord(**data, installation_id=parent.installation_id, supersedes_record_id=row.record_id,
                                   record_id=uuid_str(), version=1, status='draft', created_by=user.user_id, last_human_reason=payload.reason)
        try:
            revised.source_snapshot = snapshot(db, user, parent, revised, True)
        except HTTPException as error:
            if error.status_code != 409:
                raise
            # Preserve the ability to correct a missing/changed original via a new draft.
            revised.source_snapshot = {}
        db.add(revised)
        db.flush()
        history(db, user, revised, 'record.revision', payload.reason)
        return parent, revised
    if action == 'confirm':
        if row.status != 'draft' or not row.document_ids:
            raise HTTPException(409, 'draft and at least one verified original required')
        if snapshot(db, user, parent, row, True) != row.source_snapshot:
            raise HTTPException(409, 'draft evidence changed; recheck originals and save the draft before Human confirmation')
        source_snapshot = snapshot(db, user, parent, row, True, record_version=row.version + 1)
        if row.supersedes_record_id:
            old = get(db, HazardousRecord, row.supersedes_record_id, True)
            require_record_visibility(db, user, old)
            if old.installation_id != parent.installation_id or old.status != 'confirmed':
                raise HTTPException(409, 'revision predecessor is no longer current')
            old_before = serial(old)
            bump(db, old, old.version, {'status': 'superseded', 'last_human_reason': payload.reason})
            history(db, user, old, 'record.supersede', payload.reason, old_before)
        values = {'status': 'confirmed', 'source_snapshot': source_snapshot, 'confirmed_by': user.user_id,
                  'confirmed_at': now_utc(), 'last_human_reason': payload.reason}
    else:
        if row.status not in ('draft', 'confirmed'):
            raise HTTPException(409, 'closed evidence cannot be cancelled again')
        values = {'status': 'cancelled', 'last_human_reason': payload.reason}
    bump(db, row, payload.expected_version, values)
    history(db, user, row, 'record.' + action, payload.reason, before)
    return parent, row


def deadlines(db, user, due_before=None, limit=100, offset=0):
    authority(db, user)
    statement = select(HazardousRecord, HazardousInstallation).join(HazardousInstallation).where(
        HazardousInstallation.status == 'active', HazardousRecord.status.in_(('draft', 'confirmed')), HazardousRecord.due_on.is_not(None))
    if due_before:
        statement = statement.where(HazardousRecord.due_on <= due_before)
    rows = [(row, parent) for row, parent in db.execute(statement.order_by(HazardousRecord.due_on, HazardousRecord.record_id)) if record_is_visible(db, user, row)]
    return [{**record_dict(db, user, parent, row), 'installation_name': parent.name, 'building_id': parent.building_id}
            for row, parent in rows[offset:offset + limit]]


def source_choices(db, user, kind, building_id=None, q='', limit=100, offset=0):
    authority(db, user)
    permissions = {'facilities': ('facility.read',), 'documents': ('document.read',),
                   'legal': ('legal_source.read', 'document.read'), 'inspections': ('inspection.read',), 'violations': ('violation.read',)}
    if kind not in permissions:
        raise HTTPException(404, 'unknown source kind')
    need(db, user, *permissions[kind])
    if kind in ('inspections', 'violations') and not building_id:
        raise HTTPException(422, 'building_id required')
    facility = get(db, Facility, building_id) if building_id else None
    models = {'facilities': Facility, 'documents': Document, 'legal': LegalSourceDocumentVersion, 'inspections': Inspection, 'violations': ViolationCase}
    model = models[kind]
    statement = select(model)
    if kind == 'facilities':
        statement = statement.where(Facility.status == 'active', Facility.deleted_at.is_(None))
    elif kind == 'documents' and facility:
        statement = statement.where(or_(Document.building_id == facility.building_id, Document.building_id.is_(None)))
    elif kind in ('inspections', 'violations'):
        statement = statement.where(model.building_id == facility.building_id)
    rows = []
    for row in db.scalars(statement.order_by(list(model.__table__.primary_key.columns)[0])):
        try:
            item = choice(db, user, kind, row)
        except HTTPException as error:
            if error.status_code in (403, 404):
                continue
            raise
        if q.casefold() in item['label'].casefold():
            rows.append(item)
    return rows[offset:offset + limit]
