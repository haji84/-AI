"""Explicit approved stored observations, never salaries or a complete population."""
from datetime import date, datetime, time, timezone
import json
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_observed_statistics_sources import source_db, capture, observed
from test_observed_statistics_api import statistics_api, save, revoke
from app.models import Employee, User, Permission, RolePermission
from app.personnel import OrganizationUnit
from app.workforce_models import WorkforceShiftType, WorkforceRosterEntry, WorkforceAttendance, WorkforceTimeEntry

KEYS = ['workforce.approved_rosters', 'workforce.approved_worked_minutes', 'workforce.approved_overtime_minutes']


def seed_workforce(db, user_id):
    employee = Employee(display_name='PRIVATE workforce employee', active=False)
    organization = OrganizationUnit(code='SYN-STAT', name='PRIVATE historical station', active=False)
    shift = WorkforceShiftType(code='SYN-STAT', name='Synthetic shift', start_time=time(8), end_time=time(17), payable_minutes=480)
    db.add_all([employee, organization, shift]); db.flush()
    rosters, attendance, entries = [], [], []
    for index, (day, state, minutes) in enumerate([
        (date(2026,1,1),'approved',480), (date(2026,1,31),'approved',510),
        (date(2026,2,1),'approved',600), (date(2026,1,2),'draft',900),
        (date(2026,1,3),'reviewed',900), (date(2026,1,4),'cancelled',900),
        (date(2026,1,5),'approved',None),
    ]):
        start = datetime.combine(day, time(8), timezone.utc)
        end = datetime.combine(day, time(17), timezone.utc)
        roster = WorkforceRosterEntry(employee_id=employee.employee_id, organization_id=organization.organization_id,
            shift_type_id=shift.shift_type_id, work_date=day, starts_at=start, ends_at=end,
            payable_minutes=480, status=state, note='PRIVATE roster reason', created_by=user_id)
        db.add(roster); db.flush(); rosters.append(roster)
        row = WorkforceAttendance(employee_id=employee.employee_id, roster_entry_id=roster.roster_entry_id,
            work_date=day, check_in_at=start, check_out_at=end, worked_minutes=minutes,
            calculation={'private':'PRIVATE calculation'}, status=state, created_by=user_id)
        db.add(row); db.flush(); attendance.append(row)
        overtime = WorkforceTimeEntry(employee_id=employee.employee_id, attendance_id=row.attendance_id,
            kind='overtime', minutes=31+index, occurred_on=day, status=state,
            note='PRIVATE overtime reason', created_by=user_id)
        db.add(overtime); entries.append(overtime)
    db.add(WorkforceTimeEntry(employee_id=employee.employee_id, kind='comp_grant', minutes=999,
        occurred_on=date(2026,1,1), status='approved', created_by=user_id))
    db.commit()
    return rosters, attendance, entries


def test_approved_workforce_period_integer_units_and_private_lineage(source_db):
    db = source_db
    rosters, attendance, entries = seed_workforce(db, db.info['synthetic_user_id'])
    result = capture(db, KEYS)
    assert [observed(result, key)['value'] for key in KEYS] == ['3', '990', '100']
    assert [observed(result, key)['unit'] for key in KEYS] == ['記録','分','分']
    assert result.public['coverage_status'] == 'unknown'
    public = json.dumps(result.public)
    assert 'PRIVATE' not in public and attendance[0].attendance_id not in public
    assert len(result.evidence['metrics'][KEYS[0]]['selected']) == 3
    assert observed(result, KEYS[1])['exclusions'][0]['reason'] == 'approved_minutes_missing'
    old = result.fingerprint
    attendance[0].worked_minutes = 481; attendance[0].version += 1; db.commit()
    assert capture(db, KEYS).fingerprint != old
    assert observed(capture(db, KEYS), KEYS[1])['value'] == '991'


def test_empty_workforce_zero_does_not_mean_population_complete(source_db):
    result = capture(source_db, KEYS)
    assert [row['value'] for row in result.public['metrics']] == ['0','0','0']
    assert all(row['coverage_status']=='unknown' and row['denominator'] is None for row in result.public['metrics'])


def test_approved_but_uncalculated_minutes_are_unavailable_not_zero(source_db):
    seed_workforce(source_db, source_db.info['synthetic_user_id'])
    result = capture(source_db, [KEYS[1]], start='2026-01-05', end='2026-01-05')
    metric = observed(result, KEYS[1])
    assert metric['status'] == 'unavailable' and metric['value'] is None
    assert metric['coverage_status'] == 'unknown'


def grant(db, refs, *codes):
    for code in codes:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        db.add(RolePermission(role_id=refs['role_id'], permission_id=permission.permission_id))
    db.commit()


def test_aggregate_only_workforce_report_export_and_live_revocation(statistics_api):
    client, engine, refs = statistics_api
    with Session(engine) as db:
        grant(db, refs, 'workforce.aggregate', 'workforce.export')
        seed_workforce(db, refs['user_id'])
    query = {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':KEYS}
    row = save(client, query); key = row['report_id']
    assert [m['value'] for m in row['snapshot']['metrics']] == ['3','990','100']
    assert 'PRIVATE' not in json.dumps(row)
    assert client.get('/statistics/reports/'+key+'/drilldown', params={'metric_key':KEYS[0]}).status_code == 403
    response = client.post('/statistics/reports/'+key+'/confirm', json={
        'expected_version':1,'acknowledged':True,'review_note':'Synthetic observed-source Human review'})
    assert response.status_code == 200, response.text
    exported = client.get('/statistics/reports/'+key+'/export?format=csv')
    assert exported.status_code == 200, exported.text
    assert 'PRIVATE' not in exported.text and '990' in exported.text
    revoke(engine, refs, 'workforce.aggregate')
    assert client.post('/statistics/query', json=query).status_code == 403
    assert client.get('/statistics/reports/'+key).status_code == 403
    assert client.get('/statistics/reports/'+key+'/export?format=csv').status_code == 403


def test_disabled_workforce_blocks_new_capture_and_saved_release(statistics_api):
    from app.models import FeatureFlag
    client, engine, refs = statistics_api
    with Session(engine) as db:
        grant(db, refs, 'workforce.aggregate', 'workforce.export')
    query = {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':KEYS}
    row = save(client, query)
    ordinary = save(client)
    mixed = save(client, {**query, 'metric_keys':KEYS+['emergency.cases']})
    with Session(engine) as db:
        db.add(FeatureFlag(key='module.workforce.enabled', module_code='workforce', enabled=False)); db.commit()
    assert client.post('/statistics/query', json=query).status_code == 503
    assert client.get('/statistics/reports/'+row['report_id']).status_code == 503
    assert client.get('/statistics/reports/'+row['report_id']+'/export?format=csv').status_code == 503
    listing = client.get('/statistics/reports?limit=1').json()
    assert listing['total'] == 1 and listing['items'][0]['report_id'] == ordinary['report_id']
    assert row['report_id'] not in json.dumps(listing) and mixed['report_id'] not in json.dumps(listing)
    assert 'workforce.' not in json.dumps(listing)
    from app.module_seed import seed_modules
    with Session(engine) as db:
        seed_modules(db); db.commit()
        assert not db.scalar(select(FeatureFlag).where(FeatureFlag.key=='module.workforce.enabled')).enabled
    assert client.post('/statistics/query', json=query).status_code == 503
    catalog = client.get('/statistics/metrics').json()
    assert all(not m['available'] for m in catalog['metrics'] if m['key'] in KEYS)


def test_postgresql_workforce_observations_use_readonly_coherent_snapshot(statistics_pg, monkeypatch):
    from app import statistics_service as service
    from sqlalchemy import text
    client, engine, refs = statistics_pg
    with Session(engine) as db:
        grant(db, refs, 'workforce.aggregate', 'workforce.export')
        seed_workforce(db, refs['user_id'])
    original = service.capture_sources
    transactions = []
    def inspected(db, period, keys):
        transactions.append((db.scalar(text('SHOW transaction_isolation')), db.scalar(text('SHOW transaction_read_only'))))
        return original(db, period, keys)
    monkeypatch.setattr(service, 'capture_sources', inspected)
    row = save(client, {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':KEYS})
    assert [m['value'] for m in row['snapshot']['metrics']] == ['3','990','100']
    assert transactions == [('repeatable read','on')]
    confirmed = client.post('/statistics/reports/'+row['report_id']+'/confirm', json={
        'expected_version':1,'acknowledged':True,'review_note':'Synthetic PostgreSQL stored work review'})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['snapshot'] == row['snapshot']


@pytest.mark.parametrize('metric', KEYS)
def test_workforce_lineage_pointers_require_live_individual_and_linked_original_rights(statistics_api, metric):
    from app.models import Document
    client, engine, refs = statistics_api
    with Session(engine) as db:
        grant(db, refs, 'workforce.aggregate', 'workforce.read', 'personnel.read', 'document.read', 'hazardous.read')
        rosters, _, _ = seed_workforce(db, refs['user_id'])
        original = Document(storage_path='synthetic-protected-roster', original_filename='PRIVATE attachment',
            sha256='1'*64, document_type='hazardous_evidence')
        db.add(original); db.flush(); rosters[0].document_id=original.document_id; db.commit()
    row = save(client, {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':[metric]})
    url = '/statistics/reports/'+row['report_id']+'/drilldown'
    response = client.get(url, params={'metric_key':metric})
    assert response.status_code == 200, response.text
    assert response.json()['total'] > 0
    assert all(item['navigation'] is None for item in response.json()['items'])
    assert 'PRIVATE' not in response.text and 'employee_id' not in response.text
    revoke(engine, refs, 'hazardous.read')
    denied = client.get(url, params={'metric_key':metric,'limit':1})
    assert denied.status_code == 403 and 'items' not in denied.json()
    assert client.get('/statistics/reports/'+row['report_id']).status_code == 200


@pytest.mark.parametrize('phase', ['capture','export'])
def test_flag_change_during_capture_or_export_blocks_the_response(statistics_api, monkeypatch, phase):
    from app import statistics_service as service, statistics_exports
    from app.models import FeatureFlag
    client, engine, refs = statistics_api
    with Session(engine) as db:
        grant(db, refs, 'workforce.aggregate', 'workforce.export')
        seed_workforce(db, refs['user_id'])
    query = {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':KEYS}
    row = save(client, query)
    def disable():
        with Session(engine) as db:
            db.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False)); db.commit()
    if phase == 'capture':
        original = service.capture_in_snapshot
        def revoked(*args):
            value = original(*args); disable(); return value
        monkeypatch.setattr(service,'capture_in_snapshot',revoked)
        response = client.post('/statistics/query',json=query)
    else:
        original = statistics_exports.render_export
        def revoked(*args):
            value = original(*args); disable(); return value
        monkeypatch.setattr(statistics_exports,'render_export',revoked)
        response = client.get('/statistics/reports/'+row['report_id']+'/export?format=csv')
    assert response.status_code == 503, response.text
    assert '990' not in response.text and 'PRIVATE' not in response.text


# Explicitly reuse the real disposable PostgreSQL fixture; skip is not acceptance.
from test_observed_statistics_postgres import statistics_pg
