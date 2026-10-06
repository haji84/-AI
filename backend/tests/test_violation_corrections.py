from sqlalchemy import select
from test_violations import client,sources,create,action,SessionLocal

def confirmed(client,refs):return action(client,action(client,create(client,refs),'review'),'confirm')
def current(client,case):return client.get('/violations/'+case['case_id']).json()
def measure(client,case,refs,kind='guidance',**changes):
    data={'expected_case_version':current(client,case)['version'],'kind':kind,'instruction':'Synthetic Human instruction','document_ids':[refs['proof']],'procedure_document_ids':[refs['procedure']],'due_on':'2026-10-10'};data.update(changes)
    r=client.post('/violations/'+case['case_id']+'/measures',json=data);assert r.status_code==201,r.text;return r.json()
def measure_action(client,case,row,verb,status=200):
    r=client.post('/violations/'+case['case_id']+'/measures/'+row['measure_id']+'/'+verb,json={'expected_version':row['version'],'reason':'Synthetic Human procedure checked','human_acknowledged':True});assert r.status_code==status,r.text;return r.json()
def correction(client,case,**changes):
    data={'expected_case_version':current(client,case)['version'],'description':'Synthetic correction instruction','due_on':'2026-10-10'};data.update(changes)
    r=client.post('/violations/'+case['case_id']+'/corrections',json=data);assert r.status_code==201,r.text;return r.json()
def event(client,case,row,verb,refs,status=200,**changes):
    data={'expected_version':row['version'],'reason':'Synthetic Human response/verification','human_acknowledged':True,'evidence_document_ids':[refs['proof']]};data.update(changes)
    r=client.post('/violations/'+case['case_id']+'/corrections/'+row['action_id']+'/'+verb,json=data);assert r.status_code==status,r.text;return r.json()

def test_formal_measure_requires_separate_review_procedure_and_confirmation(client):
    refs=sources(client);case=confirmed(client,refs)
    for kind in ('guidance','order','disposition'):
        row=measure(client,case,refs,kind);assert row['status']=='draft';measure_action(client,case,row,'confirm',409)
        row=measure_action(client,case,row,'review');row=measure_action(client,case,row,'confirm');assert row['status']=='confirmed'
    incomplete=measure(client,case,refs,'order',procedure_document_ids=[]);measure_action(client,case,incomplete,'review',409)

def test_correction_response_verification_completion_and_immutable_history(client):
    refs=sources(client);case=confirmed(client,refs);action(client,current(client,case),'complete',409)
    row=correction(client,case);action(client,current(client,case),'complete',409)
    event(client,case,row,'complete',refs,409)
    row=event(client,case,row,'respond',refs,response_text='Synthetic response evidence')
    row=event(client,case,row,'verify',refs,passed=False);event(client,case,row,'complete',refs,409)
    row=event(client,case,row,'verify',refs,passed=True);row=event(client,case,row,'complete',refs);assert row['status']=='completed'
    timeline=client.get('/violations/'+case['case_id']+'/corrections/'+row['action_id']+'/events').json()
    assert [x['kind'] for x in timeline]==['instruction','response','verification','verification','completion']
    assert timeline[1]['source_snapshot']['documents'][0]['document_id']==refs['proof']
    assert [x['sequence_no'] for x in timeline]==list(range(1,6))
    assert client.patch('/violations/'+case['case_id']+'/corrections/'+row['action_id']+'/events/'+timeline[1]['event_id'],json={'text':'Overwrite'}).status_code in (404,405)
    case=action(client,current(client,case),'complete');assert case['status']=='completed'

def test_advisory_guidance_does_not_require_or_create_formal_violation(client):
    refs=sources(client);case=create(client,refs,rule_version_ids=[])
    row=measure(client,case,refs,'guidance',procedure_document_ids=[]);row=measure_action(client,case,row,'review');row=measure_action(client,case,row,'confirm')
    task=correction(client,case,measure_id=row['measure_id']);task=event(client,case,task,'respond',refs,response_text='Synthetic advisory response');task=event(client,case,task,'verify',refs,passed=True);event(client,case,task,'complete',refs)
    case=action(client,current(client,case),'complete');assert case['status']=='resolved_candidate' and case['confirmed_by'] is None
    order=client.post('/violations/'+case['case_id']+'/measures',json={'expected_case_version':case['version'],'kind':'order','instruction':'Synthetic','document_ids':[refs['proof']],'procedure_document_ids':[refs['procedure']]});assert order.status_code==409

def test_changed_measure_original_and_correction_version_are_rejected(client):
    refs=sources(client);case=confirmed(client,refs);row=measure_action(client,case,measure(client,case,refs,'order'),'review')
    from app.models import Document
    with SessionLocal() as db:db.get(Document,refs['procedure']).sha256='0'*64;db.commit()
    measure_action(client,case,row,'confirm',409)
    task=correction(client,case);task=event(client,case,task,'respond',refs,response_text='Synthetic')
    event(client,case,{**task,'version':1},'verify',refs,409,passed=True)

def test_cancelled_only_tasks_do_not_claim_completion_and_overdue_is_explicit(client):
    refs=sources(client);case=confirmed(client,refs);task=correction(client,case)
    overdue=client.get('/violations/corrections?overdue_on=2026-10-11').json();assert any(x['action_id']==task['action_id'] for x in overdue)
    event(client,case,task,'cancel',refs);action(client,current(client,case),'complete',409)
    assert not client.get('/violations/corrections?overdue_on=2026-10-11').json()

def test_cross_case_correction_measure_and_pending_order_withdrawal_are_blocked(client):
    refs=sources(client);first=confirmed(client,refs);second=confirmed(client,refs)
    order=measure(client,first,refs,'order');order=measure_action(client,first,measure_action(client,first,order,'review'),'confirm')
    r=client.post('/violations/'+second['case_id']+'/corrections',json={'expected_case_version':current(client,second)['version'],'description':'Wrong case','measure_id':order['measure_id']});assert r.status_code==409
    action(client,current(client,first),'withdraw',409)


def test_changed_instruction_and_response_original_invalidate_verification(client):
    refs=sources(client);case=confirmed(client,refs);task=correction(client,case);task=event(client,case,task,'respond',refs,response_text='Synthetic response');task=event(client,case,task,'verify',refs,passed=True)
    r=client.patch('/violations/'+case['case_id']+'/corrections/'+task['action_id'],json={'expected_version':task['version'],'description':'Changed Human instruction','reason':'Synthetic correction'});assert r.status_code==200,r.text;task=r.json();event(client,case,task,'complete',refs,409)
    task=event(client,case,task,'respond',refs,response_text='Synthetic revised response')
    from app.models import Document
    from app.settings import settings
    from pathlib import Path
    new=client.post('/documents/upload',files={'file':('synthetic-new.txt',b'New verification proof','text/plain')}).json()['document_id']
    with SessionLocal() as db:
        doc=db.get(Document,refs['proof']);(Path(settings.storage_root)/doc.storage_path).write_text('Tampered old response')
    event(client,case,task,'verify',refs,409,passed=True,evidence_document_ids=[new])


def test_stale_review_can_be_revised_without_becoming_formal_automatically(client):
    refs=sources(client);case=action(client,create(client,refs),'review')
    with SessionLocal() as db:
        from app.models import Facility
        db.get(Facility,refs['building_id']).version+=1;db.commit()
    action(client,case,'confirm',409)
    revised=client.post('/violations/'+case['case_id']+'/revisions',json={'expected_version':case['version'],'reason':'Synthetic updated basis'}).json()
    revised=action(client,revised,'review');revised=action(client,revised,'confirm');assert revised['status']=='confirmed'
    assert client.get('/violations/'+case['case_id']).json()['confirmed_by'] is None


def test_source_permission_loss_redacts_nested_measure_and_verification_proof(client):
    refs=sources(client);case=confirmed(client,refs)
    m=measure_action(client,case,measure(client,case,refs,'order'),'review')
    task=correction(client,case);task=event(client,case,task,'respond',refs,response_text='Synthetic');task=event(client,case,task,'verify',refs,passed=True)
    with SessionLocal() as db:
        from app.models import Permission,RolePermission
        permissions=list(db.scalars(select(Permission).where(Permission.code.in_(['document.read','legal_rule.read','legal_source.read']))))
        for permission in permissions:
            for link in db.scalars(select(RolePermission).where(RolePermission.permission_id==permission.permission_id)):db.delete(link)
        db.commit()
    data=current(client,case)
    assert 'verification_snapshot' not in data['corrections'][0]
    assert 'review_snapshot' not in data['measures'][0]
    assert not data['review_snapshot'].get('procedure_documents')
    assert not data['review_snapshot'].get('rules')


def test_completed_case_retains_order_obligation_until_explicit_evidenced_withdrawal(client):
    refs=sources(client);case=confirmed(client,refs);m=measure_action(client,case,measure_action(client,case,measure(client,case,refs,'order'),'review'),'confirm')
    task=correction(client,case);task=event(client,case,task,'respond',refs,response_text='Synthetic response');task=event(client,case,task,'verify',refs,passed=True);event(client,case,task,'complete',refs);case=action(client,current(client,case),'complete')
    revised=client.post('/violations/'+case['case_id']+'/revisions',json={'expected_version':case['version'],'reason':'Synthetic revision'}).json();revised=action(client,revised,'review');action(client,revised,'confirm',409)
    withdrawn=client.post('/violations/'+case['case_id']+'/measures/'+m['measure_id']+'/withdraw',json={'expected_version':m['version'],'reason':'Synthetic explicit legal resolution','human_acknowledged':True,'proof_document_ids':[refs['procedure']]});assert withdrawn.status_code==200,withdrawn.text
    assert withdrawn.json()['status']=='withdrawn' and withdrawn.json()['withdrawal_snapshot']['documents']
    revised=action(client,revised,'confirm');assert revised['status']=='confirmed'
