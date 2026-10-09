"""Generic read-only hazardous pointers with current original/source closure."""
from fastapi import HTTPException
from sqlalchemy import select

from . import hazardous_service as facts, hazardous_evaluation_service as evaluations
from .authz import permission_codes
from .hazardous_models import HazardousInstallation, HazardousRecord
from .hazardous_evaluation_models import HazardousEvaluation
from .inquiries_service import document_permissions
from .models import Facility, LegalRuleVersion

BASE = {'hazardous.read', 'facility.read'}


def source_rights(db, user, data, seen=None):
    """Return live permissions, not private source prose or old frozen ownership."""
    required = set()
    if seen is None:
        seen = set()
    if isinstance(data, list):
        for item in data:
            required.update(source_rights(db, user, item, seen))
    elif isinstance(data, dict):
        required.update(data.get('required_permissions', []))
        documents = data.get('document_ids', []) + ([data['document_id']] if data.get('document_id') else [])
        for identity in documents:
            required.update(document_permissions(db, facts.document_access(db, user, identity)))
        versions = data.get('legal_source_version_ids', []) + ([data['legal_source_version_id']] if data.get('legal_source_version_id') else [])
        if data.get('rule_version_id'):
            required.update(('legal_rule.read', 'legal_source.read'))
            rule = facts.get(db, LegalRuleVersion, data['rule_version_id'])
            if rule.source_legal_document_version_id:
                versions.append(rule.source_legal_document_version_id)
        for identity in versions:
            required.update(('legal_source.read', 'document.read'))
            version, _, _ = facts.legal_access(db, user, identity)
            if version.raw_document_id:
                required.update(document_permissions(db, facts.document_access(db, user, version.raw_document_id)))
        if data.get('inspection_ids') or data.get('inspection_id'):
            required.add('inspection.read')
        cases = data.get('violation_case_ids', []) + ([data['case_id']] if data.get('case_id') else [])
        for identity in cases:
            required.add('violation.read')
            if ('violation', identity) in seen:
                continue
            seen.add(('violation', identity))
            case = facts.violation_access(db, user, identity)
            required.update(source_rights(db, user, facts.violation_snapshot(db, user, case), seen))
        for value in data.values():
            if isinstance(value, (dict, list)):
                required.update(source_rights(db, user, value, seen))
    return required


def active_parent(db, user, identity):
    parent = facts.installation(db, user, identity)
    facility = facts.get(db, Facility, parent.building_id)
    return parent if parent.status == 'active' and facility.status == 'active' and not facility.deleted_at else None


def hazardous_work_items(db, user, as_of, through, make_item):
    current = permission_codes(db, user.user_id)
    if not BASE <= current:
        return
    try:
        facts.authority(db, user)
    except HTTPException as error:
        # This authority function's 503 means disabled/unconfigured hazardous
        # module; other modules' work must remain available.
        if error.status_code == 503:
            return
        raise
    records = select(HazardousRecord).where(HazardousRecord.status.in_(('draft', 'confirmed')))
    for row in db.scalars(records).yield_per(50):
        db.refresh(row)
        if row.status not in ('draft', 'confirmed'):
            continue
        try:
            parent = active_parent(db, user, row.installation_id)
            if parent is None:
                continue
            facts.require_record_visibility(db, user, row)
            required = BASE | source_rights(db, user, facts.serial(row))
            seen = set(); previous = row.supersedes_record_id
            while previous and previous not in seen:
                seen.add(previous)
                ancestor = facts.get(db, HazardousRecord, previous)
                required.update(source_rights(db, user, facts.serial(ancestor)))
                previous = ancestor.supersedes_record_id
            current = permission_codes(db, user.user_id)
            if not required <= current:
                continue
        except HTTPException as error:
            if error.status_code in (403, 404, 409):
                continue
            raise
        relationships = ['created_by_me'] if row.created_by == user.user_id else []
        if row.status == 'draft' and 'hazardous.review' in current:
            relationships.append('available_to_my_role')
            review_required = required | {'hazardous.review'}
            yield make_item(module='hazardous_materials', kind='evidence_review', title='危険物記録の原本・根拠確認',
                source_type='hazardous_record', source=row, status=row.status, as_of=as_of,
                permissions=review_required, relationships=relationships,
                navigation={'surface': 'hazardous_installation', 'id': parent.installation_id},
                source_api='/hazardous/installations/' + parent.installation_id,
                parent=('hazardous_installation', parent.installation_id, parent.version))
        elif row.status == 'draft' and relationships:
            yield make_item(module='hazardous_materials', kind='draft', title='危険物記録の未確認草案',
                source_type='hazardous_record', source=row, status=row.status, as_of=as_of,
                permissions=required, relationships=relationships,
                navigation={'surface': 'hazardous_installation', 'id': parent.installation_id},
                source_api='/hazardous/installations/' + parent.installation_id,
                parent=('hazardous_installation', parent.installation_id, parent.version))
        if row.due_on is not None and row.due_on <= through:
            yield make_item(module='hazardous_materials', kind='hazardous_deadline', title='危険物記録の期限確認',
                source_type='hazardous_record', source=row, status=row.status, as_of=as_of,
                permissions=required, due_on=row.due_on, relationships=relationships + ['shared_deadline'],
                navigation={'surface': 'hazardous_installation', 'id': parent.installation_id},
                source_api='/hazardous/installations/' + parent.installation_id,
                parent=('hazardous_installation', parent.installation_id, parent.version))
    required = BASE | {'legal_rule.read', 'legal_source.read', 'document.read'}
    if not required <= permission_codes(db, user.user_id):
        return
    identities = select(HazardousEvaluation.evaluation_id).where(HazardousEvaluation.status == 'candidate')
    for identity in db.scalars(identities).yield_per(50):
        try:
            row = facts.get(db, HazardousEvaluation, identity)
            if row.status != 'candidate':
                continue
            parent = active_parent(db, user, row.installation_id)
            if parent is None:
                continue
            data = evaluations.output(db, user, row)
            needed = required | source_rights(db, user, row.rules_snapshot)
            current = permission_codes(db, user.user_id)
            if not needed <= current:
                continue
        except HTTPException as error:
            if error.status_code in (403, 404, 409):
                continue
            raise
        relationships = ['created_by_me'] if row.created_by == user.user_id else []
        kind, title = 'draft', '危険物の未確認評価候補'
        if not data['is_stale'] and 'hazardous.review' in current:
            relationships.append('available_to_my_role'); needed.add('hazardous.review')
            kind, title = 'evaluation_review', '危険物評価候補のHuman確認'
        elif data['is_stale'] and 'hazardous.create' in current and 'legal_rule.evaluate' in current:
            relationships.append('available_to_my_role'); needed.update(('hazardous.create', 'legal_rule.evaluate'))
            kind, title = 'evaluation_refresh', '元データ更新・危険物評価候補の再作成'
        if not relationships or not needed <= permission_codes(db, user.user_id):
            continue
        yield make_item(module='hazardous_materials', kind=kind, title=title,
            source_type='hazardous_evaluation', source=row, status=row.status, as_of=as_of,
            permissions=needed, relationships=relationships,
            navigation={'surface': 'hazardous_evaluation', 'id': row.evaluation_id},
            source_api='/hazardous/evaluations/' + row.evaluation_id,
            parent=('hazardous_installation', parent.installation_id, parent.version))
