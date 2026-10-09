"""Private workforce search must preserve exact source individual/original rights."""
from sqlalchemy.orm import Session
import pytest
from app.models import Document,FeatureFlag
from app.routers.search import router
from test_statistics_workforce import statistics_api,seed_workforce,grant,revoke
from test_observed_statistics_postgres import statistics_pg


def search(client,**extra):
    return client.get('/search',params={'q':'PRIVATE','modules':'workforce',**extra})


def test_workforce_search_needs_individual_personnel_authority(statistics_api):
    client,engine,refs=statistics_api;client.app.include_router(router)
    with Session(engine) as db:
        grant(db,refs,'search.use','workforce.read');seed_workforce(db,refs['user_id'])
    response=search(client)
    assert response.status_code==403,response.text
    assert response.headers.get('cache-control')=='no-store'
    assert 'PRIVATE' not in response.text


def test_workforce_search_filters_current_original_before_limit_and_disable(statistics_api):
    client,engine,refs=statistics_api;client.app.include_router(router)
    with Session(engine) as db:
        grant(db,refs,'search.use','workforce.read','personnel.read','document.read','hazardous.read')
        rows=seed_workforce(db,refs['user_id'])
        doc=Document(storage_path='synthetic-search-source',original_filename='PRIVATE original',sha256='3'*64,document_type='hazardous_evidence')
        db.add(doc);db.flush()
        # Protect every newest row, leaving the oldest visible row beyond limit1.
        for row in rows[0][1:]:row.document_id=doc.document_id
        oldest=rows[0][0].roster_entry_id;db.commit()
    revoke(engine,refs,'hazardous.read')
    response=search(client,per_module_limit=1)
    assert response.status_code==200,response.text
    assert response.headers.get('cache-control')=='no-store'
    data=response.json()
    assert data['total_hits']==1 and data['hits'][0]['source_id']==oldest,response.text
    assert data['hits'][0]['navigation']=={'surface':'workforce_roster','record_id':oldest}
    with Session(engine) as db:
        db.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False));db.commit()
    response=search(client)
    assert response.status_code==200,response.text
    assert response.headers.get('cache-control')=='no-store'
    assert response.json()['total_hits']==0 and 'PRIVATE workforce employee' not in response.text


@pytest.mark.parametrize('change,status',[('permissions',403),('session',401),('version',409),('original',200),('disable',200)])
def test_private_search_release_rechecks_live_source(statistics_api,monkeypatch,change,status):
    from app.routers import search as unified
    from app.models import UserSession,now_utc,AuditLog
    from app.workforce_models import WorkforceRosterEntry
    client,engine,refs=statistics_api;client.app.include_router(router)
    with Session(engine) as db:
        grant(db,refs,'search.use','workforce.read','personnel.read','document.read','hazardous.read')
        rows=seed_workforce(db,refs['user_id']);key=rows[0][0].roster_entry_id
        doc=Document(storage_path='synthetic-live-search-source',original_filename='PRIVATE original',sha256='4'*64,document_type='hazardous_evidence')
        db.add(doc);db.flush()
        for row in rows[0]:row.document_id=doc.document_id
        db.commit()
    original=unified.SEARCHERS['workforce']
    def changed(*args):
        hits=original(*args)
        if change in ('permissions','original'):
            revoke(engine,refs,'personnel.read' if change=='permissions' else 'hazardous.read')
        else:
            with Session(engine) as db:
                if change=='session':db.query(UserSession).filter_by(user_id=refs['user_id']).update({'revoked_at':now_utc()})
                elif change=='version':db.get(WorkforceRosterEntry,key).version+=1
                else:db.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False))
                db.commit()
        return hits
    monkeypatch.setitem(unified.SEARCHERS,'workforce',changed)
    response=search(client)
    assert response.status_code==status,response.text
    assert 'PRIVATE workforce employee' not in response.text
    if status==200:assert response.json()['total_hits']==0
    else:
        with Session(engine) as db:
            assert db.query(AuditLog).filter_by(action='unified_search.query').count()==0


@pytest.mark.parametrize('change,status',[('permissions',403),('session',401),('version',409),('original',200),('disable',200)])
def test_postgresql_search_release_checks_separate_writer(statistics_pg,monkeypatch,change,status):
    test_private_search_release_rechecks_live_source(statistics_pg,monkeypatch,change,status)
