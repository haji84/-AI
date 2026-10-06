"""Real PostgreSQL transaction races and migration049; synthetic originals only."""
from functools import partial
from sqlalchemy.orm import Session
import pytest
from test_learning import learning_environment
from test_workforce_concurrency import compete
from test_violations import sources,create,action
from test_violation_corrections import correction,event,current

@pytest.fixture
def violation_pg(learning_environment,tmp_path,monkeypatch):
    client,engine=learning_environment
    if engine.dialect.name!='postgresql':pytest.skip('real PostgreSQL row-lock interleaving executes in CI')
    from app.routers import violations,documents
    from app.settings import settings
    monkeypatch.setattr(settings,'storage_root',str(tmp_path/'storage'))
    client.app.include_router(violations.router);client.app.include_router(documents.router)
    refs=sources(client,partial(Session,engine),username='learning-admin')
    return client,engine,refs

def test_competing_case_confirmations_have_one_winner(violation_pg):
    client,engine,refs=violation_pg;case=action(client,create(client,refs),'review')
    request=('/violations/'+case['case_id']+'/confirm',{'expected_version':case['version'],'reason':'Synthetic Human concurrent approval','human_acknowledged':True})
    assert sorted(compete(client,[request,request]))==[200,409]
    final=current(client,case);assert final['confirmed_by'] and final['version']==case['version']+1

def test_case_closure_and_new_correction_cannot_leave_closed_case_with_open_task(violation_pg):
    client,engine,refs=violation_pg;case=action(client,action(client,create(client,refs),'review'),'confirm');task=correction(client,case);task=event(client,case,task,'respond',refs,response_text='Synthetic response');task=event(client,case,task,'verify',refs,passed=True);event(client,case,task,'complete',refs);case=current(client,case)
    close=('/violations/'+case['case_id']+'/complete',{'expected_version':case['version'],'reason':'Synthetic Human closure','human_acknowledged':True})
    add=('/violations/'+case['case_id']+'/corrections',{'expected_case_version':case['version'],'description':'Synthetic concurrent new task'})
    results=compete(client,[close,add]);assert 409 in results and any(x in (200,201) for x in results),results
    final=current(client,case)
    assert final['status']!='completed' or all(c['status'] in ('completed','cancelled') for c in final['corrections'])

def test_competing_responses_append_only_one_event_for_expected_version(violation_pg):
    client,engine,refs=violation_pg;case=action(client,action(client,create(client,refs),'review'),'confirm');task=correction(client,case)
    request=('/violations/'+case['case_id']+'/corrections/'+task['action_id']+'/respond',{'expected_version':task['version'],'reason':'Synthetic response','human_acknowledged':True,'response_text':'Synthetic answer','evidence_document_ids':[refs['proof']]})
    assert sorted(compete(client,[request,request]))==[200,409]
    events=client.get('/violations/'+case['case_id']+'/corrections/'+task['action_id']+'/events').json();assert [e['kind'] for e in events]==['instruction','response']
