"""Stop this department's registered writers and restore previous service activity."""
import fcntl
import os
import re
from uuid import UUID


def run_scheduled_backup(*,slug,tenant_id,lock_path,writer_units,control,backup):
    UUID(tenant_id)
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,15}',slug):raise ValueError('invalid department slug')
    app='fire-ai-'+slug+'.service';prefix='fire-ai-'+slug+'-'
    if any(not unit.startswith(prefix) or not re.fullmatch(r'[a-z0-9_-]+\.(service|timer)',unit)
           or unit in {'fire-ai-'+slug+'-backup.service','fire-ai-'+slug+'-backup.timer'} for unit in writer_units):
        raise ValueError('writers must be explicit units of this department, excluding backup units')
    writers=list(dict.fromkeys(writer_units));units=[app,*writers]
    fd=os.open(lock_path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('department backup already running') from None
        active=[unit for unit in units if control('is-active',unit)]
        try:
            # Stop timers before their writer services to prevent rescheduling.
            for unit in sorted(writers,key=lambda name:not name.endswith('.timer')):control('stop',unit)
            control('stop',app)
            return backup()
        finally:
            failures=[]
            for unit in active:
                try:control('start',unit)
                except Exception as exc:failures.append((unit,type(exc).__name__))
            if failures:raise RuntimeError('service restart failed: '+repr(failures))
    finally:
        os.close(fd)


def systemd_control(action,unit,*,runner=None):
    import subprocess
    runner=runner or subprocess.run
    if action=='is-active':
        result=runner(['systemctl','show','--property=LoadState','--property=ActiveState',unit],capture_output=True,text=True)
        values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode or values.get('LoadState')!='loaded':raise RuntimeError('registered service unavailable: '+unit)
        state=values.get('ActiveState')
        if state in {'active','activating','reloading'}:return True
        if state in {'inactive','failed'}:return False
        raise RuntimeError('transitional service state requires operator retry: '+unit)
    result=runner(['systemctl',action,unit],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('systemctl '+action+' failed for '+unit)
    return True


from contextlib import contextmanager
import signal


@contextmanager
def controlled_termination():
    previous=signal.getsignal(signal.SIGTERM)
    def terminate(signum,frame):
        # Allow finally to finish even when another stop request arrives.
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    try:yield
    finally:signal.signal(signal.SIGTERM,previous)


def run_backup_child(command):
    """Cancellation waits for the entire dump subprocess group before restart."""
    import subprocess
    process=subprocess.Popen(command,start_new_session=True)
    try:
        code=process.wait()
        if code:raise subprocess.CalledProcessError(code,command)
    except BaseException:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait()
        raise
