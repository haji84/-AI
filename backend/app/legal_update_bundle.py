"""Detached signatures and bounded immutable staging; never approves legal rules."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DOMAIN=b'fire-ai-legal-update-signature-v1\0'
MAX_MANIFEST=8*1024*1024
MAX_PAYLOAD=4*1024*1024*1024
MAX_TOTAL=8*1024*1024*1024
FORMATS={'fire-ai-legal-update-v1':'egov_v2','fire-ai-local-regulation-snapshot-v1':'official_html_crawl'}


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def parse_json(raw):
    try:
        value=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        if not isinstance(value,dict):raise ValueError('JSON object required')
        return value
    except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError('invalid JSON') from exc


def bounded_read(path,limit):
    try:
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):raise ValueError('regular file required')
            body=file.read(limit+1)
            if len(body)>limit:raise ValueError('file exceeds bound')
            return body
    except OSError as exc:raise ValueError('required file missing or unsafe') from exc


def signature_path(manifest):return Path(str(manifest)+'.signature.json')


def sign_manifest(manifest_path,private_key_path,*,password=None):
    manifest_path,private_key_path=Path(manifest_path),Path(private_key_path)
    raw=bounded_read(manifest_path,MAX_MANIFEST);parse_json(raw)
    if private_key_path.is_symlink():raise ValueError('signing key symlink forbidden')
    info=private_key_path.stat()
    if info.st_mode & 0o077 or info.st_uid!=os.getuid():raise ValueError('signing key must be owner-only and owned by collector')
    key=serialization.load_pem_private_key(bounded_read(private_key_path,16384),password=password)
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('Ed25519 signing key required')
    kid=hashlib.sha256(key.public_key().public_bytes_raw()).hexdigest()
    envelope={'format':'fire-ai-legal-signature-v1','algorithm':'Ed25519','key_id':kid,
              'manifest_sha256':hashlib.sha256(raw).hexdigest(),
              'signature':base64.b64encode(key.sign(DOMAIN+raw)).decode('ascii')}
    destination=signature_path(manifest_path)
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as file:json.dump(envelope,file,sort_keys=True)
    return destination


def trusted_signer(raw,manifest_path,trust_file,allow_unsigned):
    sig=signature_path(manifest_path)
    if not sig.exists() and not sig.is_symlink():
        if allow_unsigned:return {'signature_status':'unsigned-development-only','manifest_sha256':hashlib.sha256(raw).hexdigest()},None
        raise ValueError('signed legal update required')
    if not trust_file:raise ValueError('operator-installed trust required')
    trust_file=Path(trust_file)
    if trust_file.resolve().is_relative_to(manifest_path.parent.resolve()):raise ValueError('bundle-embedded trust forbidden')
    envelope=parse_json(bounded_read(sig,65536));trust=parse_json(bounded_read(trust_file,1024*1024))
    if envelope.get('format')!='fire-ai-legal-signature-v1' or envelope.get('algorithm')!='Ed25519' or trust.get('format')!='fire-ai-legal-trust-v1':raise ValueError('unsupported signature/trust protocol')
    if not isinstance(envelope.get('key_id'),str) or not re.fullmatch('[0-9a-f]{64}',envelope['key_id']) or not isinstance(envelope.get('signature'),str) or not isinstance(trust.get('keys'),dict):raise ValueError('malformed signature envelope or trust keys')
    key=trust['keys'].get(envelope['key_id'])
    if not isinstance(key,dict) or key.get('revoked') is not False:raise ValueError('unknown or revoked collector key')
    digest=hashlib.sha256(raw).hexdigest()
    if envelope.get('manifest_sha256')!=digest:raise ValueError('manifest SHA mismatch')
    if not isinstance(key.get('public_key'),str):raise ValueError('malformed public trust key')
    try:
        public=base64.b64decode(key['public_key'],validate=True)
        if hashlib.sha256(public).hexdigest()!=envelope.get('key_id'):raise ValueError('trust key ID mismatch')
        Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(envelope['signature'],validate=True),DOMAIN+raw)
    except (KeyError,InvalidSignature,ValueError) as exc:raise ValueError('invalid legal update signature') from exc
    hosts=key.get('allowed_hosts')
    if not isinstance(hosts,list) or not hosts or any(not isinstance(host,str) or not host or '*' in host for host in hosts):raise ValueError('explicit collector source scopes required')
    return {'signature_status':'verified','signer_key_id':envelope['key_id'],'manifest_sha256':digest,'algorithm':'Ed25519'},hosts


def checked_url(url,hosts):
    if not isinstance(url,str):raise ValueError('source URL required')
    parsed=urlsplit(url)
    if not parsed.hostname or parsed.scheme!='https' or parsed.username or parsed.password or parsed.hostname not in hosts or parsed.port not in {None,443}:raise ValueError('source URL outside approved official origin')


def payloads(manifest,expected_adapter,hosts):
    if not isinstance(manifest.get('bundle_format'),str) or expected_adapter not in FORMATS.values() or FORMATS.get(manifest['bundle_format'])!=expected_adapter:raise ValueError('bundle adapter mismatch')
    if expected_adapter=='egov_v2':
        checked_url(manifest.get('source_url'),hosts)
        checked_url(manifest.get('effective_source_url',manifest.get('source_url')),hosts)
        if manifest.get('mode') not in ('all','delta'):raise ValueError('invalid collector mode')
        items=[(manifest.get('archive_file'),manifest.get('archive_sha256'))]
    else:
        checked_url(manifest.get('index_url'),hosts)
        if manifest.get('allowed_host') not in hosts:raise ValueError('collector host mismatch')
        documents=manifest.get('documents')
        if not isinstance(documents,list) or len(documents)>20000:raise ValueError('bounded documents required')
        items=[]
        for document in documents:
            if not isinstance(document,dict):raise ValueError('invalid document metadata')
            checked_url(document.get('url'),hosts);checked_url(document.get('effective_url',document.get('url')),hosts);items.append((document.get('file'),document.get('sha256')))
    seen={}
    unique=[]
    for name,digest in items:
        if not isinstance(name,str) or '\\' in name or not name or PurePosixPath(name).is_absolute() or any(part in {'.','..',''} for part in name.split('/')):raise ValueError('unsafe payload path')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('invalid payload hash')
        if name in seen:
            if seen[name]!=digest:raise ValueError('conflicting payload identity')
            continue
        seen[name]=digest;unique.append((name,digest))
    return unique


@contextmanager
def open_beneath(root,name):
    descriptors=[]
    try:
        descriptor=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(descriptor)
        parts=name.split('/')
        for part in parts[:-1]:
            descriptor=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor);descriptors.append(descriptor)
        file_descriptor=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=descriptor)
        with os.fdopen(file_descriptor,'rb') as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):raise ValueError('regular payload required')
            yield file
    except OSError as exc:raise ValueError('unsafe or missing bundle payload') from exc
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)


@dataclass(frozen=True)
class VerifiedBundle:
    root: Path
    manifest: dict
    manifest_path: Path
    provenance: dict


@contextmanager
def stage_verified_bundle(manifest_path,trusted_keys_file,*,expected_hosts,expected_adapter,allow_unsigned=False):
    manifest_path=Path(manifest_path).absolute()
    if any(path.is_symlink() for path in [manifest_path.parent,*manifest_path.parent.parents]):raise ValueError('bundle root symlink forbidden')
    raw=bounded_read(manifest_path,MAX_MANIFEST);manifest=parse_json(raw)
    provenance,key_hosts=trusted_signer(raw,manifest_path,trusted_keys_file,allow_unsigned)
    hosts=set(expected_hosts)
    if not hosts or (key_hosts is not None and not hosts.issubset(set(key_hosts))):raise ValueError('collector key outside approved source scope')
    items=payloads(manifest,expected_adapter,hosts)
    retrieved=parse_retrieved(manifest.get('retrieved_at'))
    if retrieved>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('future collector timestamp')
    provenance['source_retrieved_at']=retrieved.isoformat()
    with tempfile.TemporaryDirectory(prefix='fire-ai-verified-legal-') as temporary:
        root=Path(temporary);total=0
        for name,expected_hash in items:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            digest=hashlib.sha256();size=0
            with open_beneath(manifest_path.parent,name) as source,target.open('xb') as output:
                os.chmod(target,0o600)
                for chunk in iter(lambda:source.read(1024*1024),b''):
                    size+=len(chunk);total+=len(chunk)
                    if size>(MAX_PAYLOAD if expected_adapter=='egov_v2' else 32*1024*1024) or total>MAX_TOTAL:raise ValueError('bundle exceeds payload bound')
                    digest.update(chunk);output.write(chunk)
            if digest.hexdigest()!=expected_hash:raise ValueError('payload SHA mismatch')
        if expected_adapter=='egov_v2':
            try:
                with zipfile.ZipFile(root/manifest['archive_file']) as archive:
                    entries=archive.infolist();names=set();expanded=0
                    if len(entries)>20000:raise ValueError('too many archive entries')
                    for entry in entries:
                        name=entry.filename.rstrip('/')
                        if not name or '\\' in name or PurePosixPath(name).is_absolute() or any(part in {'.','..',''} for part in name.split('/')) or name in names:raise ValueError('unsafe archive member')
                        names.add(name);expanded+=entry.file_size
                        if entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr>>16) or entry.file_size>32*1024*1024 or expanded>MAX_PAYLOAD:raise ValueError('unsafe or oversized archive member')
                        if name.lower().endswith('.xml') and not entry.is_dir():
                            if len(PurePosixPath(name).stem)>160 or len(PurePosixPath(name).name)>255:raise ValueError('oversized law metadata name')
                            try:
                                law=ET.fromstring(archive.read(entry))
                            except ET.ParseError as exc:raise ValueError('malformed law XML') from exc
                            if law.tag.rsplit('}',1)[-1]!='Law' or not any(element.tag.rsplit('}',1)[-1]=='LawTitle' and ''.join(element.itertext()).strip() for element in law.iter()):raise ValueError('Law root and title required')
            except zipfile.BadZipFile as exc:raise ValueError('invalid legal archive') from exc
        staged_manifest=root/manifest_path.name;staged_manifest.write_bytes(raw);staged_manifest.chmod(0o600)
        if provenance['signature_status']=='verified':
            staged_signature=signature_path(staged_manifest)
            staged_signature.write_bytes(bounded_read(signature_path(manifest_path),65536));staged_signature.chmod(0o600)
        yield VerifiedBundle(root,manifest,staged_manifest,provenance)


@contextmanager
def verified_import_inputs(session_factory,source_id,manifest_path,config,*,archive_path=None):
    from uuid import UUID
    from .models import LegalSource
    source_id=str(UUID(source_id))
    with session_factory() as db:
        source=db.get(LegalSource,source_id)
        if not source or not source.enabled:raise ValueError('enabled legal source required')
        base=urlsplit(source.base_url)
        if not base.hostname or base.scheme!='https' or base.username or base.password or base.port not in {None,443}:raise ValueError('approved HTTPS legal source required')
        host=base.hostname;adapter=source.adapter_type
        scope={'source_id':source_id,'host':host,'adapter':adapter,'jurisdiction_id':source.jurisdiction_id,'legal_profile_id':source.legal_profile_id}
    with stage_verified_bundle(manifest_path,config.legal_update_trust_file,expected_hosts={host},expected_adapter=adapter,
                               allow_unsigned=not(config.production_mode or config.tenant_id)) as verified:
        if archive_path is not None:
            original=Path(manifest_path).parent/verified.manifest['archive_file']
            if Path(archive_path).resolve()!=original.resolve():raise ValueError('archive argument disagrees with signed manifest')
        verified.provenance['source_scope']=scope
        yield verified


def parse_retrieved(value):
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('collector timestamp needs timezone')
        return parsed.astimezone(timezone.utc)
    except (TypeError,AttributeError,ValueError) as exc:raise ValueError('valid collector timestamp required') from exc


def lock_and_validate_freshness(db,source_id,provenance):
    from sqlalchemy import select,text
    from .models import AuditLog
    if db.bind.dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),{'key':'fire-ai-legal-bundle:'+source_id})
        db.expire_all()
    previous=db.scalars(select(AuditLog).where(AuditLog.action=='legal.bundle.import',AuditLog.entity_id==source_id,AuditLog.success.is_(True)).order_by(AuditLog.audit_id.desc()).limit(1)).first()
    if previous and isinstance(previous.after_data,dict) and previous.after_data.get('source_retrieved_at'):
        incoming=parse_retrieved(provenance['source_retrieved_at']);accepted=parse_retrieved(previous.after_data['source_retrieved_at'])
        if incoming<accepted or (incoming==accepted and provenance['manifest_sha256']!=previous.after_data.get('manifest_sha256')):
            raise ValueError('older or conflicting legal bundle refused')


def validate_source_snapshot(source,provenance):
    scope=provenance.get('source_scope')
    current={'source_id':source.legal_source_id,'host':urlsplit(source.base_url).hostname,'adapter':source.adapter_type,
             'jurisdiction_id':source.jurisdiction_id,'legal_profile_id':source.legal_profile_id}
    if not source.enabled or scope!=current:raise ValueError('source configuration changed during verification')
