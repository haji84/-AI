"""Canonical workforce source details require independent private-source authority."""
import json
import pytest
from sqlalchemy.orm import Session
from app.models import Document, FeatureFlag
from app.routers.workforce import router
from test_statistics_workforce import statistics_api, seed_workforce, grant, revoke
from test_observed_statistics_postgres import statistics_pg


@pytest.mark.parametrize('kind,index', [('roster',0),('attendance',1),('time',2)])
def test_exact_current_source_detail_and_live_transitive_original_rights(statistics_api, kind, index):
    client, engine, refs = statistics_api
    client.app.include_router(router)
    with Session(engine) as db:
        grant(db,refs,'workforce.read','personnel.read','document.read','hazardous.read')
        records = seed_workforce(db,refs['user_id'])
        original = Document(storage_path='synthetic-protected-source',original_filename='PRIVATE protected evidence',sha256='2'*64,document_type='hazardous_evidence')
        db.add(original);db.flush();records[0][0].document_id=original.document_id;db.commit()
        source = records[index][0]
        key = getattr(source, {'roster':'roster_entry_id','attendance':'attendance_id','time':'time_entry_id'}[kind])
    url = '/workforce/source-records/'+kind+'/'+key
    response = client.get(url)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['kind'] == kind and data['record_id'] == key and data['version'] == 1
    assert data['employee']['display_name'] == 'PRIVATE workforce employee'
    assert data['record']['status'] == 'approved'
    assert response.headers['cache-control'] == 'no-store'
    revoke(engine,refs,'hazardous.read')
    denied = client.get(url)
    unknown = client.get('/workforce/source-records/'+kind+'/00000000-0000-4000-8000-000000000001')
    assert denied.status_code == unknown.status_code == 404 and 'PRIVATE' not in denied.text
    assert denied.json() == unknown.json()


def test_individual_authority_precedes_source_id_lookup_and_disable_blocks_detail(statistics_api):
    client, engine, refs = statistics_api
    client.app.include_router(router)
    paths = ['/workforce/source-records/roster/00000000-0000-4000-8000-000000000001',
             '/workforce/source-records/roster/not-a-uuid']
    for path in paths:
        assert client.get(path).status_code == 403
    with Session(engine) as db:
        grant(db,refs,'workforce.read','personnel.read')
        rows = seed_workforce(db,refs['user_id'])
        key = rows[0][0].roster_entry_id
        db.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False));db.commit()
    response = client.get('/workforce/source-records/roster/'+key)
    assert response.status_code == 503 and 'PRIVATE' not in response.text


@pytest.mark.parametrize('change,status', [('permissions',403),('session',401),('version',409)])
def test_change_while_preparing_source_blocks_private_release(statistics_api,monkeypatch,change,status):
    from app import workforce_source
    from app.models import UserSession, now_utc, AuditLog
    from app.workforce_models import WorkforceRosterEntry
    client, engine, refs = statistics_api
    client.app.include_router(router)
    with Session(engine) as db:
        grant(db,refs,'workforce.read','personnel.read')
        rows=seed_workforce(db,refs['user_id']);key=rows[0][0].roster_entry_id
    original=workforce_source.source_payload
    def changed(*args):
        data=original(*args)
        if change=='permissions':revoke(engine,refs,'personnel.read')
        else:
            with Session(engine) as db:
                if change=='session':db.query(UserSession).filter_by(user_id=refs['user_id']).update({'revoked_at':now_utc()})
                else:db.get(WorkforceRosterEntry,key).version+=1
                db.commit()
        return data
    monkeypatch.setattr(workforce_source,'source_payload',changed)
    response=client.get('/workforce/source-records/roster/'+key)
    assert response.status_code==status,response.text
    assert 'PRIVATE' not in response.text
    with Session(engine) as db:
        assert db.query(AuditLog).filter_by(action='workforce.source.read').count()==0


@pytest.mark.parametrize('change,status', [('permissions',403),('session',401),('version',409)])
def test_postgresql_private_source_release_rechecks_concurrent_change(statistics_pg,monkeypatch,change,status):
    # A separate PostgreSQL writer changes authority/version after payload creation.
    # The disposable database has all actual migrations; a local skip is not PASS.
    test_change_while_preparing_source_blocks_private_release(statistics_pg,monkeypatch,change,status)
