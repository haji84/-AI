import base64
import hashlib
import json
from pathlib import Path
import zipfile
import pytest


@pytest.fixture
def bundle(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes_raw();kid=hashlib.sha256(public).hexdigest()
    private=tmp_path/'collector.pem';private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));private.chmod(0o600)
    trust=tmp_path/'trust.json';trust.write_text(json.dumps({'format':'fire-ai-legal-trust-v1','keys':{kid:{'public_key':base64.b64encode(public).decode(),'revoked':False,'allowed_hosts':['laws.e-gov.go.jp']}}}))
    incoming=tmp_path/'incoming';incoming.mkdir();archive=incoming/'laws.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('SYN001.xml','<Law><LawTitle>Synthetic law</LawTitle></Law>')
    manifest=incoming/'laws.zip.manifest.json';manifest.write_text(json.dumps({'bundle_format':'fire-ai-legal-update-v1','provider':'e-Gov','authority':'official','mode':'all','update_date':None,'source_url':'https://laws.e-gov.go.jp/bulkdownload?file_section=1','retrieved_at':'2026-10-06T00:00:00Z','archive_file':archive.name,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
    return manifest,private,trust,kid


def verify(manifest,trust,**kwargs):
    from app.legal_update_bundle import stage_verified_bundle
    return stage_verified_bundle(manifest,trust,expected_hosts={'laws.e-gov.go.jp'},expected_adapter='egov_v2',**kwargs)


def sign(manifest,private):
    from app.legal_update_bundle import sign_manifest
    return sign_manifest(manifest,private)


def test_signed_manifest_and_payload_are_staged_immutably(bundle):
    manifest,private,trust,kid=bundle;sign(manifest,private)
    with verify(manifest,trust) as result:
        assert result.provenance['signer_key_id']==kid
        assert result.manifest['archive_file']=='laws.zip'
        copied=result.root/'laws.zip';before=copied.read_bytes()
        (manifest.parent/'laws.zip').write_bytes(b'tampered after verification')
        assert copied.read_bytes()==before
        root=result.root
    assert not root.exists()


@pytest.mark.parametrize('mutation',['manifest','payload','signature','unknown','revoked','host'])
def test_untrusted_or_changed_bundle_is_rejected_before_staging(bundle,mutation):
    manifest,private,trust,kid=bundle;signature=sign(manifest,private)
    if mutation=='manifest':manifest.write_text(manifest.read_text()+' ')
    elif mutation=='payload':(manifest.parent/'laws.zip').write_bytes(b'bad')
    elif mutation=='signature':
        data=json.loads(signature.read_text());data['signature']=base64.b64encode(b'0'*64).decode();signature.write_text(json.dumps(data))
    else:
        data=json.loads(trust.read_text())
        if mutation=='unknown':data['keys']={}
        elif mutation=='revoked':data['keys'][kid]['revoked']=True
        else:data['keys'][kid]['allowed_hosts']=['other.invalid']
        trust.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass


def test_unsigned_refuses_unless_explicit_development_compatibility(bundle):
    manifest,private,trust,_=bundle
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass
    with verify(manifest,None,allow_unsigned=True) as result:assert result.provenance['signature_status']=='unsigned-development-only'


@pytest.mark.parametrize('path',['../outside.zip','/tmp/absolute.zip','files\\escape.zip'])
def test_payload_path_escape_rejected_even_if_signed(bundle,path):
    manifest,private,trust,_=bundle;data=json.loads(manifest.read_text());data['archive_file']=path;manifest.write_text(json.dumps(data));sign(manifest,private)
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass


def test_symlink_payload_and_bundle_embedded_trust_rejected(bundle):
    manifest,private,trust,_=bundle;archive=manifest.parent/'laws.zip';outside=manifest.parent.parent/'outside.zip';outside.write_bytes(archive.read_bytes());archive.unlink();archive.symlink_to(outside);sign(manifest,private)
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass
    embedded=manifest.parent/'trust.json';embedded.write_bytes(trust.read_bytes())
    with pytest.raises(ValueError):
        with verify(manifest,embedded):pass


def test_duplicate_json_keys_and_unprotected_signing_key_refused(bundle):
    manifest,private,trust,_=bundle;manifest.write_text('{"bundle_format":"fire-ai-legal-update-v1","bundle_format":"other"}')
    with pytest.raises(ValueError):sign(manifest,private)
    manifest.write_text('{}');private.chmod(0o644)
    with pytest.raises(ValueError):sign(manifest,private)


@pytest.mark.parametrize('adapter',['egov_v2','official_html_crawl'])
def test_production_importer_verifies_then_creates_only_review_candidates(bundle,tmp_path,monkeypatch,capsys,adapter):
    import importlib.util
    from sqlalchemy import create_engine,select,func
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.db import Base
    from app.models import LegalJurisdiction,LegalSource,LegalUpdateCandidate,LegalSourceDocumentVersion,LegalRuleVersion,AuditLog
    manifest,private,trust,kid=bundle
    if adapter=='official_html_crawl':
        payload=manifest.parent/'source.html';payload.write_bytes(b'<html><title>Synthetic regulation</title><p>Human review required</p></html>')
        manifest.write_text(json.dumps({'bundle_format':'fire-ai-local-regulation-snapshot-v1','retrieved_at':'2026-10-06T00:00:00Z','index_url':'https://laws.e-gov.go.jp/synthetic.html','allowed_host':'laws.e-gov.go.jp','captured_count':1,'complete_candidate':True,'documents':[{'url':'https://laws.e-gov.go.jp/synthetic.html','file':payload.name,'sha256':hashlib.sha256(payload.read_bytes()).hexdigest(),'content_type':'text/html'}]}))
    sign(manifest,private)
    filename='import_egov_xml_bundle.py' if adapter=='egov_v2' else 'import_official_regulation_snapshot.py'
    spec=importlib.util.spec_from_file_location('synthetic_legal_import',Path(__file__).resolve().parents[2]/'scripts'/filename)
    importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
    engine=create_engine('sqlite+pysqlite:///:memory:');Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    with sessions() as db:
        jurisdiction=LegalJurisdiction(code='SYN',name='Synthetic jurisdiction',jurisdiction_type='national');db.add(jurisdiction);db.flush()
        source=LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id,source_code='SYN',name='Synthetic source',source_type='national_law',adapter_type=adapter,base_url='https://laws.e-gov.go.jp/',update_mode='bundle')
        db.add(source);db.commit();sid=source.legal_source_id
    monkeypatch.setattr(importer,'SessionLocal',sessions)
    from types import SimpleNamespace
    monkeypatch.setattr(importer,'settings',SimpleNamespace(production_mode=True,tenant_id=None,storage_root=str(tmp_path/'originals'),legal_update_trust_file=str(trust)))
    import sys
    arguments=['importer','--source-id',sid,'--manifest',str(manifest)]
    if adapter=='egov_v2':arguments+=['--archive',str(manifest.parent/'laws.zip')]
    monkeypatch.setattr(sys,'argv',arguments)
    importer.main()
    with sessions() as db:
        candidate=db.scalar(select(LegalUpdateCandidate));assert candidate.status=='review_required'
        version=db.scalar(select(LegalSourceDocumentVersion))
        assert version.structured_content['bundle_verification']['signer_key_id']==kid
        assert db.scalar(select(func.count()).select_from(LegalRuleVersion))==0
        assert db.scalar(select(AuditLog).where(AuditLog.action=='legal.bundle.import'))
    importer.main()
    with sessions() as db:assert db.scalar(select(func.count()).select_from(LegalSourceDocumentVersion))==1
    before=sorted(p.relative_to(tmp_path/'originals') for p in (tmp_path/'originals').rglob('*'))
    data=json.loads(manifest.read_text());data['retrieved_at']='2026-10-05T00:00:00Z'
    manifest.write_text(json.dumps(data));Path(str(manifest)+'.signature.json').unlink();sign(manifest,private)
    with pytest.raises(ValueError):importer.main()
    signature=Path(str(manifest)+'.signature.json');signature.write_text('{}')
    with pytest.raises(ValueError):importer.main()
    assert sorted(p.relative_to(tmp_path/'originals') for p in (tmp_path/'originals').rglob('*'))==before
    with sessions() as db:assert db.scalar(select(func.count()).select_from(LegalSourceDocumentVersion))==1
    engine.dispose()


def test_signed_archive_with_unsafe_members_is_rejected(bundle):
    manifest,private,trust,_=bundle;archive=manifest.parent/'laws.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../unsafe.xml','<Law/>')
    data=json.loads(manifest.read_text());data['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();manifest.write_text(json.dumps(data));sign(manifest,private)
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass


def test_egov_collector_can_sign_its_original_manifest(bundle,tmp_path,monkeypatch):
    import importlib.util
    import shutil
    manifest,private,trust,_=bundle
    spec=importlib.util.spec_from_file_location('synthetic_collector',Path(__file__).resolve().parents[2]/'scripts/collect_egov_update_bundle.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    original=manifest.parent/'laws.zip'
    monkeypatch.setattr(collector,'download',lambda url,dest:shutil.copyfile(original,dest))
    output=tmp_path/'collected';result=collector.collect('all',output,signing_key_file=private)
    with verify(output/(result['archive_file']+'.manifest.json'),trust) as verified:assert verified.provenance['signature_status']=='verified'


def test_official_html_collector_signs_all_source_files(bundle,tmp_path,monkeypatch):
    import importlib.util
    manifest,private,trust,_=bundle
    spec=importlib.util.spec_from_file_location('synthetic_html_collector',Path(__file__).resolve().parents[2]/'scripts/collect_official_regulation_snapshot.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    monkeypatch.setattr(collector,'fetch',lambda url:(b'<html><title>Synthetic regulation</title><p>Human review required</p></html>','text/html'))
    output=tmp_path/'html-collected'
    result=collector.collect(index_url='https://laws.e-gov.go.jp/synthetic.html',allowed_host='laws.e-gov.go.jp',include_regex='.*',crawl_regex='.*',output_dir=output,max_pages=1,max_depth=0,signing_key_file=private)
    from app.legal_update_bundle import stage_verified_bundle
    with stage_verified_bundle(output/'manifest.json',trust,expected_hosts={'laws.e-gov.go.jp'},expected_adapter='official_html_crawl') as verified:
        assert verified.provenance['signature_status']=='verified'
        assert len(verified.manifest['documents'])==1


def test_signed_collector_does_not_rewrite_an_existing_manifest(bundle,tmp_path,monkeypatch):
    import importlib.util,shutil
    manifest,private,trust,_=bundle
    spec=importlib.util.spec_from_file_location('synthetic_repeat_collector',Path(__file__).resolve().parents[2]/'scripts/collect_egov_update_bundle.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    monkeypatch.setattr(collector,'download',lambda url,dest:shutil.copyfile(manifest.parent/'laws.zip',dest))
    output=tmp_path/'repeated';result=collector.collect('all',output,signing_key_file=private)
    original=output/(result['archive_file']+'.manifest.json');before=original.read_bytes()
    with pytest.raises(ValueError):collector.collect('all',output,signing_key_file=private)
    assert original.read_bytes()==before
    with verify(original,trust):pass


def test_update_folder_verifies_before_dispatch_and_records_receipt(bundle,tmp_path):
    from types import SimpleNamespace
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import LegalJurisdiction,LegalSource
    from app.db import Base
    from app.main import app
    manifest,private,trust,_=bundle;sign(manifest,private)
    engine=create_engine('sqlite+pysqlite:///:memory:');Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
    with sessions() as db:
        jurisdiction=LegalJurisdiction(code='SYN',name='Synthetic',jurisdiction_type='national');db.add(jurisdiction);db.flush()
        source=LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id,source_code='SYN',name='Synthetic',source_type='law',adapter_type='egov_v2',base_url='https://laws.e-gov.go.jp/',update_mode='bundle');db.add(source);db.commit();sid=source.legal_source_id
    config=SimpleNamespace(production_mode=True,tenant_id=None,legal_update_trust_file=str(trust),storage_root=str(tmp_path/'originals'))
    calls=[]
    def runner(command):calls.append(command);return {'inserted_versions':1,'failure_count':0}
    from app.legal_update_folder import process_update_folder
    result=process_update_folder(manifest.parent,sid,sessions,config,runner=runner)
    assert result['imported']==1 and len(calls)==1
    assert '--source-id' in calls[0] and sid in calls[0]
    second=process_update_folder(manifest.parent,sid,sessions,config,runner=runner)
    assert second['already_processed']==1 and len(calls)==1
    Path(str(manifest)+'.signature.json').write_text('{}')
    refused=process_update_folder(manifest.parent,sid,sessions,config,runner=runner)
    assert refused['rejected']==1 and len(calls)==1
    engine.dispose()


def test_all_xml_is_validated_before_a_signed_bundle_can_be_imported(bundle):
    manifest,private,trust,_=bundle;archive=manifest.parent/'laws.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('GOOD.xml','<Law><LawTitle>Synthetic law</LawTitle></Law>');z.writestr('BAD.xml','<Law>')
    data=json.loads(manifest.read_text());data['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();manifest.write_text(json.dumps(data));sign(manifest,private)
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass


def test_shared_html_payload_keeps_both_document_urls(bundle):
    manifest,private,trust,_=bundle;files=manifest.parent/'files';files.mkdir();body=b'<html>Synthetic shared regulation</html>';(files/'shared.html').write_bytes(body)
    digest=hashlib.sha256(body).hexdigest();data={'bundle_format':'fire-ai-local-regulation-snapshot-v1','retrieved_at':'2026-10-06T00:00:00Z','index_url':'https://laws.e-gov.go.jp/a.html','allowed_host':'laws.e-gov.go.jp','documents':[{'url':'https://laws.e-gov.go.jp/'+name+'.html','file':'files/shared.html','sha256':digest} for name in ['a','b']]}
    manifest.write_text(json.dumps(data));sign(manifest,private)
    from app.legal_update_bundle import stage_verified_bundle
    with stage_verified_bundle(manifest,trust,expected_hosts={'laws.e-gov.go.jp'},expected_adapter='official_html_crawl') as result:
        assert len(result.manifest['documents'])==2
        assert (result.root/'files/shared.html').read_bytes()==body


def test_malformed_signature_identifier_is_a_bounded_rejection(bundle):
    manifest,private,trust,_=bundle;signature=sign(manifest,private);data=json.loads(signature.read_text());data['key_id']=[];signature.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        with verify(manifest,trust):pass


@pytest.mark.parametrize('target',['http://laws.e-gov.go.jp/unsafe','https://unapproved.invalid/raw'])
def test_collector_blocks_redirect_before_following_other_origin(target):
    import importlib.util
    import urllib.request
    spec=importlib.util.spec_from_file_location('synthetic_download',Path(__file__).resolve().parents[2]/'scripts/official_download.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    guard=module.OfficialRedirectHandler({'laws.e-gov.go.jp'})
    request=urllib.request.Request('https://laws.e-gov.go.jp/bulkdownload')
    with pytest.raises(ValueError):guard.redirect_request(request,None,302,'redirect',{},target)
    assert guard.redirect_request(request,None,302,'redirect',{},'https://laws.e-gov.go.jp/approved').full_url.endswith('/approved')
