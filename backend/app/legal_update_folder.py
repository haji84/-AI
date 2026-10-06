"""Server-side approved-folder processing; only review candidates are imported."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID
from sqlalchemy import select
from .audit import write_audit
from .models import AuditLog,LegalSource
from .legal_update_bundle import verified_import_inputs

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
IMPORTERS={'egov_v2':'import_egov_xml_bundle.py','official_html_crawl':'import_official_regulation_snapshot.py'}


def run_import(command):
    completed=subprocess.run(command,cwd=SCRIPTS.parent,capture_output=True,text=True,timeout=1800)
    if completed.returncode:raise ValueError('verified importer failed; consult server logs')
    lines=[line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:raise ValueError('missing importer result')
    result=json.loads(lines[-1])
    if not isinstance(result,dict):raise ValueError('invalid importer result')
    return result


def process_update_folder(folder,source_id,session_factory,config,*,runner=None):
    source_id=str(UUID(source_id));root=Path(folder).absolute()
    if not root.is_dir() or any(path.is_symlink() for path in [root,*root.parents]):raise ValueError('approved nonsymlink update folder required')
    with session_factory() as db:
        source=db.get(LegalSource,source_id)
        if not source or not source.enabled or source.update_mode!='bundle' or source.adapter_type not in IMPORTERS:raise ValueError('enabled bundle-mode source required')
        adapter=source.adapter_type
    descriptor=os.open(root/'.fire-ai-update.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directories=[root]
        for path in root.iterdir():
            if path.is_symlink():raise ValueError('update folder symlink forbidden')
            if path.is_dir():directories.append(path)
        manifests=sorted({path for directory in directories for path in [*directory.glob('*.manifest.json'),*directory.glob('manifest.json')]})
        if len(manifests)>1000:raise ValueError('too many pending bundles')
        result={'imported':0,'already_processed':0,'rejected':0,'results':[]}
        for manifest in manifests:
            try:
                with verified_import_inputs(session_factory,source_id,manifest,config) as verified:
                    provenance=dict(verified.provenance)
                    with session_factory() as db:
                        receipts=db.scalars(select(AuditLog).where(AuditLog.action=='legal.bundle.folder.complete',AuditLog.entity_id==source_id,AuditLog.success.is_(True))).all()
                        known=any(isinstance(receipt.after_data,dict) and receipt.after_data.get('manifest_sha256')==provenance['manifest_sha256'] for receipt in receipts)
                    if known:
                        result['already_processed']+=1;continue
                    command=[sys.executable,str(SCRIPTS/IMPORTERS[adapter]),'--source-id',source_id,'--manifest',str(verified.manifest_path)]
                    if adapter=='egov_v2':command+=['--archive',str(verified.root/verified.manifest['archive_file'])]
                    imported=(runner or run_import)(command)
                    if imported.get('failure_count',0):raise ValueError('candidate import incomplete; safe retry required')
                    with session_factory() as db:
                        write_audit(db,user_id=None,action='legal.bundle.folder.complete',entity_type='legal_source',entity_id=source_id,
                                    after={**provenance,'result':imported,'human_review_required':True})
                        db.commit()
                    result['imported']+=1;result['results'].append({'manifest':manifest.name,'status':'candidates_created'})
            except (ValueError,OSError,subprocess.SubprocessError) as exc:
                result['rejected']+=1;result['results'].append({'manifest':manifest.name,'status':'rejected','reason':str(exc)})
        return result
    except BlockingIOError as exc:raise ValueError('another folder processor is active') from exc
    finally:
        os.close(descriptor)
