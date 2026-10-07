"""Dashboard reads must preserve each source endpoint's authorization boundary."""
from datetime import date

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from test_personnel import environment
from app.models import (
    Facility, FirePlan, Inspection, InspectionFinding, Permission,
    RolePermission, Submission, SubmissionType,
)


@pytest.fixture
def dashboard_environment(environment):
    from app.routers import facilities, inspections, submissions
    from app.submission_seed import seed_submission_types

    client, engine, roles, app = environment
    for router in (facilities.router, inspections.router, submissions.router):
        app.include_router(router)
    with Session(engine) as db:
        seed_submission_types(db)
        facility = Facility(name='Synthetic dashboard facility')
        empty = Facility(name='Synthetic empty facility')
        db.add_all([facility, empty]); db.flush()
        inspection = Inspection(building_id=facility.building_id, inspected_at=date(2026, 10, 2))
        db.add(inspection); db.flush()
        db.add(InspectionFinding(inspection_id=inspection.inspection_id, finding_text='PRIVATE finding'))
        kind = db.scalar(select(SubmissionType).where(SubmissionType.code == 'equipment_inspection_report'))
        submission = Submission(building_id=facility.building_id, submission_type_id=kind.submission_type_id,
                                status='reviewed', submitted_at=date(2026, 10, 1))
        db.add(submission)
        db.add(FirePlan(building_id=facility.building_id, source_kind='legacy', raw_submission_text='PRIVATE legacy filing'))
        db.commit()
        ids = dict(building=facility.building_id, empty=empty.building_id,
                   inspection=inspection.inspection_id, submission=submission.submission_id)

    def permissions(*codes):
        with Session(engine) as db:
            db.execute(delete(RolePermission).where(RolePermission.role_id == roles['system_admin']))
            for permission in db.scalars(select(Permission).where(Permission.code.in_(codes))):
                db.add(RolePermission(role_id=roles['system_admin'], permission_id=permission.permission_id))
            db.commit()

    return client, engine, ids, permissions


def test_facility_only_dashboard_never_reads_or_discloses_protected_sources(dashboard_environment):
    client, engine, ids, permissions = dashboard_environment
    permissions('facility.read')
    assert client.get('/inspections', params={'building_id': ids['building']}).status_code == 403
    assert client.get('/submissions', params={'building_id': ids['building']}).status_code == 403
    statements = []
    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(engine, 'before_cursor_execute', record_sql)
    try:
        populated = client.get(f"/facilities/{ids['building']}/dashboard")
        empty = client.get(f"/facilities/{ids['empty']}/dashboard")
    finally:
        event.remove(engine, 'before_cursor_execute', record_sql)
    assert populated.status_code == empty.status_code == 200
    restricted = populated.json()
    assert restricted == {
        'building_id': ids['building'], 'inspections_total': None, 'open_findings': None,
        'latest_inspection_at': None, 'submission_statuses': None,
    }
    assert {**restricted, 'building_id': ids['empty']} == empty.json()
    for secret in (ids['inspection'], ids['submission'], 'reviewed', 'PRIVATE', '2026-10-02'):
        assert secret not in populated.text
    for table in ('inspections', 'inspection_findings', 'submissions', 'submission_types',
                  'equipment_inspection_reports', 'fire_management_assignments', 'fire_plans'):
        assert not any(f'from {table}' in sql or f'join {table}' in sql for sql in statements), table


@pytest.mark.parametrize('source', ['inspection', 'submission'])
def test_dashboard_sources_are_authorized_independently(dashboard_environment, source):
    client, _, ids, permissions = dashboard_environment
    permissions('facility.read', source + '.read')
    response = client.get(f"/facilities/{ids['building']}/dashboard")
    assert response.status_code == 200
    data = response.json()
    if source == 'inspection':
        assert data['inspections_total'] == data['open_findings'] == 1
        assert data['latest_inspection_at'] == '2026-10-02'
        assert data['submission_statuses'] is None
        assert ids['submission'] not in response.text and 'PRIVATE legacy filing' not in response.text
    else:
        assert data['inspections_total'] is data['open_findings'] is data['latest_inspection_at'] is None
        statuses = {item['code']: item for item in data['submission_statuses']}
        assert statuses['equipment_inspection_report']['latest_submission_id'] == ids['submission']
        assert statuses['equipment_inspection_report']['state'] == 'reviewed'
        assert statuses['fire_plan']['state'] == 'legacy_recorded'


def test_authorized_zero_and_no_record_are_distinct_from_unavailable(dashboard_environment):
    client, _, ids, permissions = dashboard_environment
    permissions('facility.read', 'inspection.read', 'submission.read')
    data = client.get(f"/facilities/{ids['empty']}/dashboard").json()
    assert data['inspections_total'] == data['open_findings'] == 0
    assert data['latest_inspection_at'] is None
    assert data['submission_statuses']
    assert all(item['state'] == 'not_submitted' for item in data['submission_statuses'])


def test_dashboard_rechecks_changed_rights_in_same_session(dashboard_environment):
    client, _, ids, permissions = dashboard_environment
    url = f"/facilities/{ids['building']}/dashboard"
    assert client.get(url).json()['inspections_total'] == 1
    permissions('facility.read')
    changed = client.get(url).json()
    assert changed['inspections_total'] is None and changed['submission_statuses'] is None
    permissions('inspection.read', 'submission.read')
    assert client.get(url).status_code == 403
