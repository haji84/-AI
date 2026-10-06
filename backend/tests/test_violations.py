"""Synthetic formal workflow tests; no assertion about any real law."""
import os
os.environ['FIRE_AI_DATABASE_URL']='sqlite+pysqlite:///:memory:'
from datetime import date
from hashlib import sha256
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import (User,Employee,Role,Permission,RolePermission,UserRole,Facility,Inspection,InspectionFinding,Document,LegalRule,LegalRuleVersion,LegalJurisdiction,LegalSource,LegalSourceDocument,LegalSourceDocumentVersion,LegalProvision,LegalRuleCitation,UserSession,now_utc)
from app.rbac_seed import PERMISSIONS
from app.settings import settings
from app.security import hash_password
from app.legal_structure import ProvisionRecord

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'storage_root',str(tmp_path/'storage'))
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with SessionLocal() as db:
        employee=Employee(display_name='Synthetic Human');db.add(employee);db.flush()
        user=User(username='violation',employee_id=employee.employee_id,password_hash=hash_password('synthetic-password'));role=Role(code='synthetic-violation',name='Synthetic');db.add_all([user,role]);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
        for code in set(PERMISSIONS)|{f'violation.{a}' for a in ('read','create','update','review','approve','export')}:
            p=Permission(code=code);db.add(p);db.flush();db.add(RolePermission(role_id=role.role_id,permission_id=p.permission_id))
        db.commit()
    with TestClient(app) as c:
        assert c.post('/auth/login',json={'username':'violation','password':'synthetic-password'}).status_code==200
        yield c

def sources(client,session_factory=SessionLocal,username='violation'):
    def upload(name,content):
        r=client.post('/documents/upload',files={'file':(name,content,'text/plain')});assert r.status_code==201,r.text;return r.json()['document_id']
    proof=upload('synthetic-proof.txt',b'Synthetic observation evidence');procedure=upload('synthetic-procedure.txt',b'Synthetic Human formal procedure');raw=upload('synthetic-rule.txt',b'Synthetic Rule article')
    with session_factory() as db:
        user=db.scalar(select(User).where(User.username==username))
        facility=Facility(name='Synthetic facility');db.add(facility);db.flush()
        inspection=Inspection(building_id=facility.building_id,inspected_at=date(2026,10,1));db.add(inspection);db.flush()
        finding=InspectionFinding(inspection_id=inspection.inspection_id,finding_text='Synthetic observation, not a formal violation');db.add(finding)
        jurisdiction=LegalJurisdiction(code='SYN',name='Synthetic',jurisdiction_type='local');db.add(jurisdiction);db.flush()
        source=LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id,source_code='SYN',name='Synthetic source',source_type='regulation',adapter_type='manual',base_url='https://synthetic.invalid/',trust_level='official');db.add(source);db.flush()
        doc=LegalSourceDocument(legal_source_id=source.legal_source_id,external_id='SYN',document_type='regulation',title='Synthetic fixture only');db.add(doc);db.flush()
        version=LegalSourceDocumentVersion(legal_source_document_id=doc.legal_source_document_id,raw_document_id=raw,normalized_text='Synthetic Rule article',sha256=sha256(b'Synthetic Rule article').hexdigest(),source_url='https://synthetic.invalid/rule',structure_status='parsed');db.add(version);db.flush()
        provision=LegalProvision(legal_source_document_version_id=version.legal_source_document_version_id,provision_type='article',provision_key='SYN-1',sequence_no=1,body_text='Synthetic Rule article',content_sha256=ProvisionRecord(provision_key='SYN-1',parent_key=None,provision_type='article',sequence_no=1,body_text='Synthetic Rule article').content_sha256);rule=LegalRule(rule_code='SYN-1',name='Synthetic fixture rule',domain='inspection');db.add_all([provision,rule]);db.flush()
        rv=LegalRuleVersion(rule_id=rule.rule_id,version_no=1,effective_from=date(2026,1,1),conditions={'all':[{'field':'status','op':'eq','value':'active'}]},outcome={'synthetic':True},source_legal_document_version_id=version.legal_source_document_version_id,status='approved',approved_by=user.user_id,approved_at=now_utc());db.add(rv);db.flush();db.add(LegalRuleCitation(legal_rule_version_id=rv.legal_rule_version_id,legal_provision_id=provision.legal_provision_id,cited_text_snapshot='Synthetic Rule article'));db.commit()
        return dict(building_id=facility.building_id,finding_id=finding.finding_id,rule_id=rv.legal_rule_version_id,provision_id=provision.legal_provision_id,legal_source_version_id=version.legal_source_document_version_id,proof=proof,procedure=procedure)

def create(client,refs,**changes):
    data={'building_id':refs['building_id'],'finding_id':refs['finding_id'],'observed_on':'2026-10-01','possible_issue':'Synthetic possible issue','missing_information':['Human confirmation required'],'confirmation_steps':['Compare original evidence'],'rule_version_ids':[refs['rule_id']],'evidence_document_ids':[refs['proof']],'procedure_document_ids':[refs['procedure']]};data.update(changes)
    r=client.post('/violations',json=data);assert r.status_code==201,r.text;return r.json()

def action(client,row,verb,status=200):
    r=client.post('/violations/'+row['case_id']+'/'+verb,json={'expected_version':row['version'],'reason':'Synthetic Human reason','human_acknowledged':True});assert r.status_code==status,r.text;return r.json()

def test_separate_candidate_review_and_formal_human_confirmation(client):
    refs=sources(client);row=create(client,refs)
    assert row['status']=='candidate';action(client,row,'confirm',409)
    row=action(client,row,'review');assert row['review_snapshot']['rules'][0]['citations'][0]['provision_key']=='SYN-1'
    row=action(client,row,'confirm');assert row['status']=='confirmed' and row['confirmed_by']
    with SessionLocal() as db:assert db.get(InspectionFinding,refs['finding_id']).corrective_status=='open'
    assert client.patch('/violations/'+row['case_id'],json={'expected_version':row['version'],'possible_issue':'Overwrite'}).status_code==409
    assert client.post('/violations/'+row['case_id']+'/revisions',json={'expected_version':row['version'],'reason':'Human correction'}).status_code==201

@pytest.mark.parametrize('changed',['facility','finding','rule','citation','original'])
def test_changed_review_source_blocks_formal_confirmation(client,changed):
    refs=sources(client);row=action(client,create(client,refs),'review')
    with SessionLocal() as db:
        if changed=='facility':db.get(Facility,refs['building_id']).version+=1
        elif changed=='finding':db.get(InspectionFinding,refs['finding_id']).version+=1
        elif changed=='rule':db.get(LegalRuleVersion,refs['rule_id']).version+=1
        elif changed=='citation':db.get(LegalProvision,refs['provision_id']).body_text='Changed synthetic source'
        else:
            doc=db.get(Document,refs['proof']);(Path(settings.storage_root)/doc.storage_path).write_text('Changed synthetic bytes')
        db.commit()
    action(client,row,'confirm',409)

@pytest.mark.parametrize('missing',['rule_version_ids','evidence_document_ids','procedure_document_ids'])
def test_incomplete_candidate_cannot_enter_formal_review(client,missing):
    refs=sources(client);row=create(client,refs,**{missing:[]});action(client,row,'review',409)

def test_formal_confirmation_requires_ack_and_fresh_version(client):
    refs=sources(client);row=action(client,create(client,refs),'review')
    assert client.post('/violations/'+row['case_id']+'/confirm',json={'expected_version':row['version'],'reason':'Synthetic','human_acknowledged':False}).status_code==422
    action(client,{**row,'version':1},'confirm',409)

def test_queued_session_revocation_blocks_candidate_write(client,monkeypatch):
    refs=sources(client)
    from app import authz
    original=authz.account_change_lock
    def revoked(db):
        original(db)
        for session in db.scalars(select(UserSession)):session.revoked_at=now_utc()
        db.flush()
    monkeypatch.setattr(authz,'account_change_lock',revoked)
    r=client.post('/violations',json={'building_id':refs['building_id'],'observed_on':'2026-10-01','possible_issue':'Synthetic'});assert r.status_code==401,r.text


def test_formal_revision_preserves_old_decision_and_has_only_one_current_tip(client):
    refs=sources(client);old=action(client,action(client,create(client,refs),'review'),'confirm')
    def revision():
        r=client.post('/violations/'+old['case_id']+'/revisions',json={'expected_version':old['version'],'reason':'Synthetic correction'});assert r.status_code==201,r.text;return action(client,r.json(),'review')
    first,second=revision(),revision();first=action(client,first,'confirm')
    previous=client.get('/violations/'+old['case_id']).json();assert previous['status']=='superseded' and previous['confirmed_by']==old['confirmed_by']
    action(client,second,'confirm',409)


def test_ai_candidate_keeps_confidence_and_verified_source_lineage(client):
    refs=sources(client)
    with SessionLocal() as db:digest=db.get(Document,refs['proof']).sha256
    provenance={'job_id':'synthetic-job','engine_version':'synthetic-engine','model_version':'synthetic-model','confidence':0.4,'source_hashes':{refs['proof']:digest}}
    assert client.post('/violations',json={'building_id':refs['building_id'],'observed_on':'2026-10-01','possible_issue':'Synthetic AI issue','origin':'ai','ai_provenance':{k:v for k,v in provenance.items() if k!='confidence'}}).status_code==422
    row=create(client,refs,origin='ai',ai_provenance=provenance);assert row['status']=='candidate' and row['ai_provenance']['confidence']==0.4 and row['confirmed_by'] is None
    assert client.post('/violations',json={'building_id':refs['building_id'],'observed_on':'2026-10-01','possible_issue':'Synthetic AI issue','origin':'ai','ai_provenance':{**provenance,'source_hashes':{refs['proof']:'0'*64}}}).status_code==409


def test_bad_source_ids_and_blank_human_reason_are_controlled_errors(client):
    assert client.post('/violations',json={'building_id':'bad-id','observed_on':'2026-10-01','possible_issue':'Synthetic'}).status_code==422
    refs=sources(client);row=create(client,refs)
    assert client.post('/violations/'+row['case_id']+'/review',json={'expected_version':1,'reason':'   ','human_acknowledged':True}).status_code==422


def test_unapproved_rule_can_be_a_candidate_link_but_cannot_be_formal_basis(client):
    refs=sources(client)
    with SessionLocal() as db:db.get(LegalRuleVersion,refs['rule_id']).status='draft';db.commit()
    row=create(client,refs);assert row['status']=='candidate';action(client,row,'review',409)


def test_violation_sources_are_paged_and_require_their_own_read_rights(client):
    refs=sources(client)
    for kind in ('facilities','documents','rules','findings'):
        path='/violations/sources/'+kind
        if kind=='findings':path+='?building_id='+refs['building_id']+'&limit=1'
        else:path+='?limit=1'
        response=client.get(path);assert response.status_code==200,response.text
        assert len(response.json())==1
    with SessionLocal() as db:
        permission=db.scalar(select(Permission).where(Permission.code=='document.read'))
        for link in db.scalars(select(RolePermission).where(RolePermission.permission_id==permission.permission_id)):db.delete(link)
        db.commit()
    assert client.get('/violations/sources/documents').status_code==403


def test_search_and_export_keep_candidate_status_and_source_rights(client):
    refs=sources(client);row=create(client,refs,possible_issue='=Synthetic export')
    response=client.get('/search?q=Synthetic&modules=violations');assert response.status_code==200,response.text
    assert any(hit['source_id']==row['case_id'] and hit['evidence']['status']=='candidate' for hit in response.json()['hits'])
    exported=client.get('/violations/export/cases');assert exported.status_code==200,exported.text
    assert exported.headers['cache-control']=='no-store'
    assert "'=Synthetic export" in exported.text
    assert 'candidate' in exported.text and refs['proof'] in exported.text


def test_violation_roles_keep_formal_human_authority_separate():
    from app.rbac_seed import ROLE_POLICY
    editor=ROLE_POLICY['violation_editor']['permissions'];reviewer=ROLE_POLICY['violation_reviewer']['permissions']
    assert {'violation.create','violation.update','violation.export'}<=editor
    assert not {'violation.review','violation.approve'}&editor
    assert {'violation.review','violation.approve','document.read','legal_source.read'}<=reviewer
    assert 'violation.create' not in reviewer


@pytest.mark.parametrize('change',['canonical_reparse','missing_primary_original'])
def test_new_formal_review_rejects_stale_citation_and_missing_primary_original(client,change):
    refs=sources(client);case=create(client,refs)
    with SessionLocal() as db:
        if change=='canonical_reparse':
            p=db.get(LegalProvision,refs['provision_id']);p.body_text='Changed canonical synthetic law';p.content_sha256=ProvisionRecord(provision_key=p.provision_key,parent_key=None,provision_type=p.provision_type,sequence_no=p.sequence_no,display_label=p.display_label,heading_text=p.heading_text,body_text=p.body_text).content_sha256
        else:db.get(LegalSourceDocumentVersion,refs['legal_source_version_id']).raw_document_id=None
        db.commit()
    action(client,case,'review',409)


def test_revoked_facility_inspection_rights_redact_all_source_snapshots(client):
    refs=sources(client);case=action(client,action(client,create(client,refs),'review'),'confirm')
    with SessionLocal() as db:
        for permission in db.scalars(select(Permission).where(Permission.code.in_(['facility.read','inspection.read']))):
            for link in db.scalars(select(RolePermission).where(RolePermission.permission_id==permission.permission_id)):db.delete(link)
        db.commit()
    detail=client.get('/violations/'+case['case_id']);assert detail.status_code==200
    assert not detail.json()['review_snapshot'].get('facility')
    assert not detail.json()['review_snapshot'].get('finding')
    assert 'Synthetic observation, not a formal violation' not in detail.text
    exported=client.get('/violations/export/cases');assert exported.status_code==200
    assert 'Synthetic observation, not a formal violation' not in exported.text
