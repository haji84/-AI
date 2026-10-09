"""Actual team endpoints reuse canonical employee/assignment history and Human CAS."""
from sqlalchemy.orm import Session
from datetime import date
import pytest
from test_statistics_workforce import statistics_api, grant, revoke
from test_observed_statistics_postgres import statistics_pg


def setup_team(client, engine, refs):
    from app.routers.workforce import router
    client.app.include_router(router)
    with Session(engine) as db:
        from app.models import Employee
        from app.personnel import OrganizationUnit, EmployeeAssignment
        grant(db, refs, 'workforce.read', 'workforce.admin', 'personnel.read')
        employee=Employee(display_name='Synthetic team member');organization=OrganizationUnit(code='SYN-TEAM',name='Synthetic team station')
        db.add_all([employee,organization]);db.flush()
        assignment=EmployeeAssignment(employee_id=employee.employee_id,organization_id=organization.organization_id,title='Synthetic member',kind='primary',valid_from=date(2026,1,1))
        db.add(assignment);db.flush()
        member = {'employee_id':employee.employee_id, 'assignment_id':assignment.assignment_id,
                  'expected_assignment_version':assignment.version,
                  'valid_from':'2026-01-01', 'reason':'Synthetic Human team membership'}
        organization_id = organization.organization_id
        db.commit()
    response = client.post('/workforce/teams', json={'code':'SYNTHETIC', 'name':'Synthetic team',
        'organization_id':organization_id, 'reason':'Synthetic Human team setup'})
    assert response.status_code == 201, response.text
    return response.json(), member


def test_team_membership_is_versioned_and_never_a_role_or_roster_grant(statistics_api):
    client, engine, refs = statistics_api
    team, member = setup_team(client, engine, refs)
    response = client.post('/workforce/teams/'+team['team_id']+'/members',
        json={**member,'expected_team_version':team['version']})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['team_version'] == team['version']+1
    assert data['membership']['assignment_version'] >= 1
    assert data['membership']['operational_status'] == 'current'
    assert data['formal_crew_assignment'] is False
    stale = client.post('/workforce/teams/'+team['team_id']+'/members',
        json={**member,'expected_team_version':team['version']})
    assert stale.status_code == 409, stale.text
    listed = client.get('/workforce/teams/'+team['team_id']+'/members')
    assert listed.status_code == 200 and len(listed.json()['items']) == 1, listed.text
    assert listed.headers.get('cache-control') == 'no-store'


def test_team_individual_reads_require_current_personnel_permission(statistics_api):
    client, engine, refs = statistics_api
    team, _ = setup_team(client, engine, refs)
    revoke(engine, refs, 'personnel.read')
    response = client.get('/workforce/teams/'+team['team_id']+'/members')
    assert response.status_code == 403 and 'Synthetic team' not in response.text
    assert response.headers.get('cache-control')=='no-store'


def test_assignment_revision_marks_history_unavailable_without_rewriting_snapshot(statistics_api):
    from app.personnel import EmployeeAssignment
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1})
    assert response.status_code==201,response.text
    before=response.json()['membership']
    with Session(engine) as db:
        assignment=db.get(EmployeeAssignment,member['assignment_id']);assignment.version+=1;assignment.title='Synthetic changed title';db.commit()
    response=client.get('/workforce/teams/'+team['team_id']+'/members')
    assert response.status_code==200,response.text
    after=response.json()['items'][0]
    assert after['operational_status']=='unavailable'
    assert after['assignment_snapshot']==before['assignment_snapshot']
    assert after['version']==before['version']


def test_overlapping_memberships_and_stale_team_changes_do_not_mutate(statistics_api):
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    first=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1})
    assert first.status_code==201,first.text
    repeated=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'valid_from':'2026-01-02','expected_team_version':2})
    assert repeated.status_code==409,repeated.text
    changed=client.patch('/workforce/teams/'+team['team_id'],json={'expected_version':1,'active':False,'reason':'Synthetic Human deactivation'})
    assert changed.status_code==409,changed.text
    data=client.get('/workforce/teams/'+team['team_id']+'/members').json()
    assert data['team']['version']==2 and len(data['items'])==1


def test_assignment_change_after_human_selection_cannot_be_silently_adopted(statistics_api):
    from app.personnel import EmployeeAssignment
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    with Session(engine) as db:
        assignment=db.get(EmployeeAssignment,member['assignment_id']);assignment.version+=1;assignment.title='Synthetic changed after selection';db.commit()
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1})
    assert response.status_code==409,response.text
    assert client.get('/workforce/teams/'+team['team_id']+'/members').json()['items']==[]


def test_explicit_inactivation_allows_same_period_new_assignment_revision(statistics_api):
    from app.personnel import EmployeeAssignment
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1})
    assert response.status_code==201,response.text
    old=response.json()['membership']
    response=client.patch('/workforce/teams/'+team['team_id']+'/members/'+old['membership_id'],json={
        'expected_team_version':2,'expected_version':1,'active':False,'reason':'Synthetic Human supersession'})
    assert response.status_code==200,response.text
    with Session(engine) as db:
        assignment=db.get(EmployeeAssignment,member['assignment_id']);assignment.version+=1;assignment.title='Synthetic revised assignment';db.commit()
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':3,'expected_assignment_version':2})
    assert response.status_code==201,response.text
    data=client.get('/workforce/teams/'+team['team_id']+'/members').json()
    assert len(data['items'])==2 and data['team']['version']==4
    inactive=next(row for row in data['items'] if row['membership_id']==old['membership_id'])
    assert inactive['assignment_snapshot']==old['assignment_snapshot'] and not inactive['active']


def test_duplicate_team_code_is_conflict_without_server_failure(statistics_api):
    client,engine,refs=statistics_api;team,_=setup_team(client,engine,refs)
    response=client.post('/workforce/teams',json={'organization_id':team['organization_id'],'code':team['code'],
        'name':'Synthetic duplicate','reason':'Synthetic Human attempt'})
    assert response.status_code==409,response.text


def test_audit_only_does_not_disclose_private_team_reason_or_assignment_snapshot(statistics_api):
    from app.routers.administration import router
    client,engine,refs=statistics_api;client.app.include_router(router)
    team,member=setup_team(client,engine,refs)
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1,
        'reason':'PRIVATE new team membership withdrawal rationale'})
    assert response.status_code==201,response.text
    for code in ('personnel.read','workforce.read','workforce.admin'):revoke(engine,refs,code)
    with Session(engine) as db:grant(db,refs,'audit.read')
    assert client.get('/workforce/teams/'+team['team_id']+'/members').status_code==403
    response=client.get('/administration/audit',params={'action':'workforce.team.membership.create'})
    assert response.status_code==200,response.text
    assert 'PRIVATE new team membership withdrawal rationale' not in response.text
    assert 'Synthetic member' not in response.text and 'assignment_snapshot"' not in response.text


def test_protected_history_retains_original_team_names_and_human_reasons(statistics_api):
    client,engine,refs=statistics_api;team,_=setup_team(client,engine,refs)
    response=client.patch('/workforce/teams/'+team['team_id'],json={'expected_version':1,'name':'Synthetic revised team','reason':'PRIVATE revised Human reason'})
    assert response.status_code==200,response.text
    response=client.get('/workforce/teams/'+team['team_id']+'/history')
    assert response.status_code==200,response.text
    rows=response.json()['items'];assert len(rows)==2
    changed=next(row for row in rows if row['action']=='workforce.team.update')
    assert changed['before_data']['name']=='Synthetic team'
    assert changed['after_data']['name']=='Synthetic revised team'
    assert changed['reason']=='PRIVATE revised Human reason'
    revoke(engine,refs,'personnel.read')
    response=client.get('/workforce/teams/'+team['team_id']+'/history')
    assert response.status_code==403 and 'PRIVATE' not in response.text


def test_protected_history_revocation_after_payload_discards_private_reason(statistics_api,monkeypatch):
    from app import workforce_service as common
    from app.workforce_models import WorkforceTeamChange
    client,engine,refs=statistics_api;team,_=setup_team(client,engine,refs)
    original=common.row_dict;changed=False
    def late(record):
        nonlocal changed
        data=original(record)
        if isinstance(record,WorkforceTeamChange) and not changed:
            changed=True;revoke(engine,refs,'personnel.read')
        return data
    monkeypatch.setattr(common,'row_dict',late)
    response=client.get('/workforce/teams/'+team['team_id']+'/history')
    assert response.status_code==403 and 'Synthetic Human team setup' not in response.text
    assert response.headers.get('cache-control')=='no-store'


@pytest.mark.parametrize('change',[{'valid_from':'2025-12-31'},{'valid_to':'2025-12-31'},{'expected_team_version':0},{'reason':''},{'ai_approved':True}])
def test_membership_rejects_invalid_period_version_reason_or_ai_approval(statistics_api,change):
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1,**change})
    assert response.status_code==422,response.text
    assert response.headers.get('cache-control')=='no-store'
    assert client.get('/workforce/teams/'+team['team_id']+'/members').json()['items']==[]


@pytest.mark.parametrize('change,status',[('permissions',403),('session',401),('module',503)])
def test_team_response_checks_current_authority_after_private_payload(statistics_api,monkeypatch,change,status):
    from app import workforce_teams as service
    from app.models import UserSession, FeatureFlag, now_utc
    client,engine,refs=statistics_api;team,member=setup_team(client,engine,refs)
    response=client.post('/workforce/teams/'+team['team_id']+'/members',json={**member,'expected_team_version':1})
    assert response.status_code==201,response.text
    original=service.membership_payload;changed=False
    def late(db,*args):
        nonlocal changed
        data=original(db,*args)
        if not changed:
            changed=True
            if change=='permissions':revoke(engine,refs,'personnel.read')
            else:
                with Session(engine) as other:
                    if change=='session':other.query(UserSession).filter_by(user_id=refs['user_id']).update({'revoked_at':now_utc()})
                    else:other.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False))
                    other.commit()
        return data
    monkeypatch.setattr(service,'membership_payload',late)
    response=client.get('/workforce/teams/'+team['team_id']+'/members')
    assert response.status_code==status,response.text
    assert 'Synthetic team member' not in response.text
    assert response.headers.get('cache-control')=='no-store'


def test_real_postgres_migrated_team_and_stale_membership(statistics_pg):
    from app.models import UserRole
    from app.workforce_models import WorkforceRosterEntry
    from sqlalchemy import select, func
    client,engine,refs=statistics_pg
    with Session(engine) as db:
        before=(db.scalar(select(func.count()).select_from(UserRole)),db.scalar(select(func.count()).select_from(WorkforceRosterEntry)))
    test_assignment_revision_marks_history_unavailable_without_rewriting_snapshot(statistics_pg)
    with Session(engine) as db:
        after=(db.scalar(select(func.count()).select_from(UserRole)),db.scalar(select(func.count()).select_from(WorkforceRosterEntry)))
    assert before==after,'team membership must not create roles or duty rosters'


def test_real_postgres_competing_membership_versions_have_one_winner(statistics_pg):
    from test_workforce_concurrency import compete
    client,engine,refs=statistics_pg;team,member=setup_team(client,engine,refs)
    request=('/workforce/teams/'+team['team_id']+'/members',{**member,'expected_team_version':1})
    assert sorted(compete(client,[request,request]))==[201,409]
    result=client.get('/workforce/teams/'+team['team_id']+'/members')
    assert result.status_code==200,result.text
    assert result.json()['team']['version']==2 and len(result.json()['items'])==1


def test_real_postgres_protected_team_change_is_append_only(statistics_pg):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    client,engine,refs=statistics_pg;team,_=setup_team(client,engine,refs)
    before=client.get('/workforce/teams/'+team['team_id']+'/history').json()['items']
    assert len(before)==1
    for sql in ('UPDATE workforce_team_changes SET reason=\'Synthetic prohibited rewrite\' WHERE change_id=:key',
                'DELETE FROM workforce_team_changes WHERE change_id=:key'):
        with Session(engine) as db:
            with pytest.raises(IntegrityError,match='history is immutable'):
                db.execute(text(sql),{'key':before[0]['change_id']});db.commit()
            db.rollback()
    after=client.get('/workforce/teams/'+team['team_id']+'/history').json()['items']
    assert after==before
