from copy import deepcopy
from uuid import UUID
from datetime import date,datetime,timezone
from hashlib import sha256
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select,update
from .audit import write_audit
from .authz import permission_codes
from .models import Facility,Inspection,InspectionFinding,Document,LegalRule,LegalRuleVersion,LegalRuleCitation,LegalProvision,LegalSourceDocumentVersion,LegalSourceDocument,LegalSource,now_utc
from .settings import settings
from .violation_models import ViolationCase
from .legal_structure import ProvisionRecord

def need(db,user,*codes):
    if not set(codes)<=permission_codes(db,user.user_id):raise HTTPException(403,'source/transition permission unavailable')

def get(db,model,key,lock=False):
    try:key=str(UUID(key))
    except (ValueError,TypeError,AttributeError):raise HTTPException(422,'invalid source/record UUID') from None
    stmt=select(model).where(list(model.__table__.primary_key.columns)[0]==key).execution_options(populate_existing=True)
    if lock:stmt=stmt.with_for_update()
    row=db.scalar(stmt)
    if not row:raise HTTPException(404,'violation source/record not found')
    return row

def serial(row):
    def value(v):
        if isinstance(v,datetime):return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
        if isinstance(v,date):return v.isoformat()
        return deepcopy(v)
    return {c.name:value(getattr(row,c.name)) for c in row.__table__.columns}

def redact_sources(value,permissions):
    """Apply source rights recursively, including immutable event before/after snapshots."""
    if isinstance(value,list):return [redact_sources(v,permissions) for v in value]
    if not isinstance(value,dict):return value
    document_keys={'documents','procedure_documents','evidence_document_ids','procedure_document_ids','document_ids','proof_document_ids','source_hashes','raw_document','raw_document_id','original'}
    legal_keys={'rules','rule_version_ids','citations'}
    facility_keys={'facility'}
    inspection_keys={'finding','inspection','finding_id','inspection_id','inspection_version','finding_text'}
    return {k:redact_sources(v,permissions) for k,v in value.items() if not (k in document_keys and 'document.read' not in permissions) and not (k in legal_keys and not {'legal_rule.read','legal_source.read'}<=permissions) and not (k in facility_keys and 'facility.read' not in permissions) and not (k in inspection_keys and not {'inspection.read','facility.read'}<=permissions)}

def case_dict(db,user,row):
    data=redact_sources(serial(row),permission_codes(db,user.user_id))
    data.setdefault('evidence_document_ids',[]);data.setdefault('procedure_document_ids',[])
    return data

def audit(db,user,action,row,before=None):
    write_audit(db,user_id=user.user_id,action='violation.'+action,entity_type=row.__tablename__,entity_id=str(getattr(row,list(row.__table__.primary_key.columns)[0].name)),before=before,after=serial(row))

def bump(db,row,expected,values):
    if row.version!=expected:raise HTTPException(409,'record version changed')
    key=list(row.__table__.primary_key.columns)[0]
    result=db.execute(update(type(row)).where(key==getattr(row,key.name),type(row).version==expected).values(**values,version=expected+1,updated_at=now_utc()).execution_options(synchronize_session=False))
    if result.rowcount!=1:raise HTTPException(409,'concurrent record change')
    db.refresh(row);return row

def document_snapshot(db,user,identity):
    need(db,user,'document.read');doc=get(db,Document,identity,True)
    root=Path(settings.storage_root).resolve();path=(root/doc.storage_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise HTTPException(409,'original missing or outside department storage')
    digest=sha256()
    with path.open('rb') as original:
        for part in iter(lambda:original.read(1024*1024),b''):digest.update(part)
    if digest.hexdigest()!=doc.sha256:raise HTTPException(409,'original hash changed')
    return {'document_id':doc.document_id,'sha256':doc.sha256,'filename':doc.original_filename}

def rule_snapshot(db,user,identity,observed_on):
    need(db,user,'legal_rule.read','legal_source.read');rv=get(db,LegalRuleVersion,identity,True);rule=get(db,LegalRule,rv.rule_id,True)
    if not rule.active or rv.status!='approved' or not rv.approved_by or not rv.approved_at or rv.effective_from>observed_on or (rv.effective_to and rv.effective_to<observed_on):raise HTTPException(409,'effective Human-approved Rule required')
    if not rv.source_legal_document_version_id:raise HTTPException(409,'structured primary legal source required')
    version=get(db,LegalSourceDocumentVersion,rv.source_legal_document_version_id,True);doc=get(db,LegalSourceDocument,version.legal_source_document_id,True);source=get(db,LegalSource,doc.legal_source_id,True)
    if not source.enabled or source.trust_level!='official' or not version.source_url:raise HTTPException(409,'enabled official primary source required')
    citations=[]
    for citation in db.scalars(select(LegalRuleCitation).where(LegalRuleCitation.legal_rule_version_id==identity).order_by(LegalRuleCitation.legal_provision_id,LegalRuleCitation.citation_role).with_for_update()):
        provision=get(db,LegalProvision,citation.legal_provision_id,True)
        if not provision.present_in_source or provision.legal_source_document_version_id!=version.legal_source_document_version_id or ProvisionRecord(provision_key=provision.provision_key,parent_key=None,provision_type=provision.provision_type,sequence_no=provision.sequence_no,display_label=provision.display_label,heading_text=provision.heading_text,body_text=provision.body_text).content_sha256!=provision.content_sha256:raise HTTPException(409,'cited provision changed or unavailable')
        canonical_citation='\n'.join(x for x in [provision.display_label,provision.heading_text,provision.body_text] if x)
        if not canonical_citation.strip() or citation.cited_text_snapshot!=canonical_citation:raise HTTPException(409,'approved citation text changed; legal Rule revision/reapproval required')
        citations.append({'provision_id':provision.legal_provision_id,'provision_key':provision.provision_key,'body_text':provision.body_text,'content_sha256':provision.content_sha256,'cited_text_snapshot':citation.cited_text_snapshot,'citation_role':citation.citation_role})
    if not citations:raise HTTPException(409,'structured provision citation required')
    if not version.raw_document_id:raise HTTPException(409,'primary legal original required')
    original=document_snapshot(db,user,version.raw_document_id)
    if original['sha256']!=version.sha256:raise HTTPException(409,'legal original/version hash mismatch')
    return {'rule_version_id':identity,'rule_version':rv.version,'rule_code':rule.rule_code,'conditions':rv.conditions,'outcome':rv.outcome,'approved_by':rv.approved_by,'approved_at':serial(rv)['approved_at'],'source_version_id':version.legal_source_document_version_id,'source_sha256':version.sha256,'source_url':version.source_url,'original':original,'citations':citations}

def source_snapshot(db,user,row,formal=False):
    need(db,user,'facility.read');facility=get(db,Facility,row.building_id,True)
    if facility.status!='active' or facility.deleted_at:raise HTTPException(409,'active source facility required')
    finding=None
    if row.finding_id:
        need(db,user,'inspection.read');f=get(db,InspectionFinding,row.finding_id,True);inspection=get(db,Inspection,f.inspection_id,True)
        if inspection.building_id!=row.building_id:raise HTTPException(409,'finding belongs to another facility')
        finding={'finding_id':f.finding_id,'version':f.version,'inspection_id':inspection.inspection_id,'inspection_version':inspection.version,'finding_text':f.finding_text}
    if formal and not (row.rule_version_ids and row.evidence_document_ids and row.procedure_document_ids):raise HTTPException(409,'Rule/evidence/formal-procedure originals required for Human review')
    if formal:rules=[rule_snapshot(db,user,identity,row.observed_on) for identity in sorted(set(row.rule_version_ids))]
    else:
        rules=[]
        for identity in sorted(set(row.rule_version_ids)):
            need(db,user,'legal_rule.read');rv=get(db,LegalRuleVersion,identity)
            rules.append({'rule_version_id':identity,'version':rv.version,'status':rv.status})
    documents={kind:[document_snapshot(db,user,identity) for identity in sorted(set(getattr(row,kind+'_document_ids')))] for kind in ('evidence','procedure')}
    previous=None
    if row.supersedes_case_id:
        old=get(db,ViolationCase,row.supersedes_case_id,True)
        if formal and row.status in ('candidate','reviewed') and old.status not in ('candidate','reviewed','confirmed','completed','resolved_candidate'):raise HTTPException(409,'revision must replace the current official case')
        previous={'case_id':old.case_id,'version':old.version,'status':old.status}
    return {'predecessor':previous,'facility':{'building_id':facility.building_id,'version':facility.version},'finding':finding,'observed_on':row.observed_on.isoformat(),'rules':rules,'documents':documents}

def create_case(db,user,payload):
    if payload.origin=='ai':
        for identity,digest in payload.ai_provenance['source_hashes'].items():
            if document_snapshot(db,user,identity)['sha256']!=digest:raise HTTPException(409,'AI original source hash changed')
    row=ViolationCase(**payload.model_dump(),created_by=user.user_id);db.add(row);db.flush();source_snapshot(db,user,row);audit(db,user,'candidate.create',row);return row

def patch_case(db,user,key,payload):
    row=get(db,ViolationCase,key,True)
    if row.status!='candidate':raise HTTPException(409,'reviewed/official record immutable; create a revision')
    values=payload.model_dump(exclude={'expected_version'},exclude_unset=True)
    if any(value is None for value in values.values()):raise HTTPException(422,'candidate fields cannot be cleared with null')
    before=serial(row);bump(db,row,payload.expected_version,values);source_snapshot(db,user,row);audit(db,user,'candidate.update',row,before);return row

def case_action(db,user,key,payload,action):
    row=get(db,ViolationCase,key,True)
    if row.version!=payload.expected_version:raise HTTPException(409,'record version changed')
    before=serial(row);values={'last_human_reason':payload.reason}
    if action=='review':
        if row.status!='candidate':raise HTTPException(409,'candidate required')
        values.update(status='reviewed',review_snapshot=source_snapshot(db,user,row,True),reviewed_by=user.user_id,reviewed_at=now_utc())
    elif action=='confirm':
        if row.status!='reviewed':raise HTTPException(409,'separate Human review required')
        if source_snapshot(db,user,row,True)!=row.review_snapshot:raise HTTPException(409,'Human review evidence changed; create/review a revision')
        if row.supersedes_case_id:
            from .violation_corrections import blocks_withdrawal
            previous=get(db,ViolationCase,row.supersedes_case_id,True);blocks_withdrawal(db,previous);previous_before=serial(previous)
            bump(db,previous,previous.version,{'status':'superseded','last_human_reason':payload.reason});audit(db,user,'superseded',previous,previous_before)
        values.update(status='confirmed',confirmed_by=user.user_id,confirmed_at=now_utc())
    elif action=='complete':
        from .violation_corrections import complete_case
        values.update(complete_case(db,user,row))
    elif action=='withdraw':
        from .violation_corrections import blocks_withdrawal
        blocks_withdrawal(db,row)
        if row.status in ('withdrawn','completed','resolved_candidate','superseded'):raise HTTPException(409,'closed case cannot be withdrawn')
        values.update(status='withdrawn')
    else:raise HTTPException(422,'unknown case action')
    bump(db,row,payload.expected_version,values);audit(db,user,action,row,before);return row

def revision(db,user,key,payload):
    row=get(db,ViolationCase,key,True)
    if row.version!=payload.expected_version:raise HTTPException(409,'record version changed')
    data={k:deepcopy(getattr(row,k)) for k in ('building_id','finding_id','observed_on','possible_issue','missing_information','confirmation_steps','rule_version_ids','evidence_document_ids','procedure_document_ids','origin','ai_provenance')}
    new=ViolationCase(**data,supersedes_case_id=row.case_id,created_by=user.user_id,last_human_reason=payload.reason);db.add(new);db.flush();audit(db,user,'revision.create',new);return new
