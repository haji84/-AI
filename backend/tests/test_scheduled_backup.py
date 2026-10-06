from uuid import uuid4
import pytest


def test_backup_stops_only_own_active_units_and_restores_on_failure(tmp_path):
    from app.scheduled_backup import run_scheduled_backup
    operations=[]
    active={'fire-ai-alpha.service','fire-ai-alpha-legal-sync.timer'}
    def control(action,unit):
        operations.append((action,unit))
        if action=='is-active':return unit in active
        return True
    def backup():
        operations.append(('backup',None))
        raise RuntimeError('synthetic failed dump')
    with pytest.raises(RuntimeError,match='failed dump'):
        run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=tmp_path/'lock',
            writer_units=['fire-ai-alpha-legal-sync.timer','fire-ai-alpha-legal-sync.service'],control=control,backup=backup)
    assert operations==[('is-active','fire-ai-alpha.service'),('is-active','fire-ai-alpha-legal-sync.timer'),
        ('is-active','fire-ai-alpha-legal-sync.service'),('stop','fire-ai-alpha-legal-sync.timer'),
        ('stop','fire-ai-alpha-legal-sync.service'),('stop','fire-ai-alpha.service'),('backup',None),
        ('start','fire-ai-alpha.service'),('start','fire-ai-alpha-legal-sync.timer')]


def test_backup_refuses_foreign_units_before_any_service_command(tmp_path):
    from app.scheduled_backup import run_scheduled_backup
    operations=[]
    with pytest.raises(ValueError):
        run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=tmp_path/'lock',
            writer_units=['fire-ai-beta.service'],control=lambda *x:operations.append(x),backup=lambda:None)
    assert not operations


def test_backup_never_runs_after_stop_failure_and_still_recovers_active_units(tmp_path):
    from app.scheduled_backup import run_scheduled_backup
    operations=[]
    def control(action,unit):
        operations.append((action,unit))
        if action=='stop':raise RuntimeError('stop failed')
        return True
    with pytest.raises(RuntimeError,match='stop failed'):
        run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=tmp_path/'lock',
            writer_units=[],control=control,backup=lambda:operations.append(('backup',None)))
    assert operations==[('is-active','fire-ai-alpha.service'),('stop','fire-ai-alpha.service'),('start','fire-ai-alpha.service')]


def test_backup_overlap_never_issues_service_commands(tmp_path):
    import fcntl
    from app.scheduled_backup import run_scheduled_backup
    path=tmp_path/'lock';operations=[]
    with path.open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='already running'):
            run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=path,writer_units=[],
                control=lambda *x:operations.append(x),backup=lambda:operations.append('backup'))
    assert operations==[]


def test_sigterm_restores_active_services(tmp_path):
    import os,subprocess,sys
    log=tmp_path/'events'
    code='''
import os,signal
from pathlib import Path
from app.scheduled_backup import run_scheduled_backup, controlled_termination
from uuid import uuid4
log=Path(os.environ['TEST_EVENT_LOG'])
def control(action,unit):
 with log.open('a') as out:out.write(action+' '+unit+'\\n')
 return True
def backup():os.kill(os.getpid(),signal.SIGTERM)
with controlled_termination():
 run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=log.parent/'lock',writer_units=[],control=control,backup=backup)
'''
    result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'TEST_EVENT_LOG':str(log)},capture_output=True,text=True)
    assert result.returncode!=0
    assert log.exists() and 'start fire-ai-alpha.service' in log.read_text(),result.stderr


def test_systemd_activating_writer_is_preserved_and_deactivating_refuses():
    from types import SimpleNamespace
    from app.scheduled_backup import systemd_control
    def response(state):return lambda *a,**k:SimpleNamespace(returncode=0,stdout='LoadState=loaded\nActiveState='+state+'\n')
    assert systemd_control('is-active','fire-ai-alpha-sync.service',runner=response('activating')) is True
    assert systemd_control('is-active','fire-ai-alpha-sync.service',runner=response('inactive')) is False
    with pytest.raises(RuntimeError,match='transitional'):
        systemd_control('is-active','fire-ai-alpha-sync.service',runner=response('deactivating'))


def test_cancel_waits_for_dump_child_before_service_restart(tmp_path):
    import os,subprocess,sys
    log=tmp_path/'events'
    child="""
import os,signal,time
from pathlib import Path
log=Path(os.environ['TEST_EVENT_LOG'])
def stop(signum,frame):
 with log.open('a') as out:out.write('child stopped\\n')
 raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
os.kill(os.getppid(),signal.SIGTERM)
time.sleep(60)
"""
    parent="""
import os,sys
from pathlib import Path
from uuid import uuid4
from app.scheduled_backup import run_scheduled_backup,run_backup_child,controlled_termination
log=Path(os.environ['TEST_EVENT_LOG'])
def control(action,unit):
 with log.open('a') as out:out.write(action+' '+unit+'\\n')
 return True
with controlled_termination():
 run_scheduled_backup(slug='alpha',tenant_id=str(uuid4()),lock_path=log.parent/'lock',writer_units=[],control=control,
  backup=lambda:run_backup_child([sys.executable,'-c',os.environ['TEST_CHILD_CODE']]))
"""
    result=subprocess.run([sys.executable,'-c',parent],env={**os.environ,'TEST_EVENT_LOG':str(log),'TEST_CHILD_CODE':child},capture_output=True,text=True,timeout=20)
    assert result.returncode!=0
    events=log.read_text()
    assert events.index('child stopped')<events.index('start fire-ai-alpha.service'),events
