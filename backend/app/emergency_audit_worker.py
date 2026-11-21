"""Durable private jobs and a bounded, killable native-reader subprocess.

Only short BoundSession transactions claim/publish work. No user session is
kept alive by a background job: its account, employee, scope and permissions
are checked again when publishing. Source bytes never appear in argv/logs.
"""
from base64 import b64decode, b64encode
from datetime import timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
from threading import Event, Thread
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update

from . import emergency_vault as vault
from .audit import write_audit
from .authz import permission_codes
from .db import SessionLocal
from .emergency_audit_models import AuditConfiguration, AuditJob, AuditReport, AuditRevision, AuditWorkerHeartbeat
from .emergency_mapping import ProfileDefinition, _pages, map_fields
from .emergency_reader import ERROR_CODES as READER_CODES, MAX_RENDER_PIXELS, MAX_SOURCE_BYTES, ReaderError
from .models import User, now_utc
from .personnel import account_change_lock, employee_available
from .settings import settings


MODE_TIMEOUTS = {'inspect': 10, 'render': 20}
OUTPUT_LIMITS = {'inspect': 4096, 'render': 52 * 1024 * 1024, 'read': 8 * 1024 * 1024, 'ai': 1024 * 1024, 'vision': 1024 * 1024}
MAX_INPUT_BYTES = 36 * 1024 * 1024
REQUIRED_RIGHTS = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read', 'emergency.report.create'}
DEFAULT_WORKER_ID = str(uuid4())
HEARTBEAT_INTERVAL_SECONDS = 15
NATIVE_PLATFORM_SUPPORTED = os.name == 'posix' and sys.platform.startswith('linux')
WORKER_CODES = frozenset({
    'PROCESS_TIMEOUT', 'PROCESS_OUTPUT_LIMIT', 'PROCESS_RESPONSE_INVALID', 'PROCESS_FAILED',
    'PROCESS_INPUT_INVALID', 'PROCESS_RETRY_LIMIT', 'AUTHORITY_CHANGED', 'STALE_REVISION',
    'PROCESS_PLATFORM_UNSUPPORTED',
    'BASELINE_ASSISTANCE_BLOCKED',
    'SOURCE_CHANGED', 'CONFIGURATION_CHANGED', 'AUDIT_UNAVAILABLE', 'AI_READING_UNAVAILABLE',
    'PRIVATE_STORAGE_UNAVAILABLE', 'PRIVATE_CONTENT_INTEGRITY', 'PRIVATE_CONTENT_INVALID',
    'PRIVATE_CONTENT_TOO_LARGE', 'KEY_NOT_CONFIGURED', 'KEY_LOCATION_INVALID', 'KEY_INVALID',
    'KEY_PERMISSIONS_INVALID',
}) | READER_CODES
RETRYABLE = {'PROCESS_TIMEOUT', 'PROCESS_FAILED', 'OCR_TIMEOUT', 'OCR_FAILED'}


class WorkerError(RuntimeError):
    def __init__(self, code='PROCESS_FAILED'):
        self.code = code if code in WORKER_CODES else 'PROCESS_FAILED'
        super().__init__(self.code)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


def _invalid_number(_):
    raise ValueError()


def _decode(data):
    return json.loads(data, object_pairs_hook=_unique, parse_constant=_invalid_number)


def _child_command():
    return [sys.executable, '-B', '-m', 'app.emergency_reader_process']


def _terminate(process):
    try:
        if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
        else: process.kill()
    except (OSError, ProcessLookupError):
        pass


def _read_result(value):
    try:
        if not isinstance(value, dict) or set(value) != {'schema_version', 'page_count', 'complete', 'pages', 'issues'}:
            raise ValueError()
        pages = _pages(value)
        if sorted(pages) != list(range(1, len(pages)+1)) or type(value['complete']) is not bool:
            raise ValueError()
        chars = 0
        for page in pages.values():
            if set(page) != {'page', 'width', 'height', 'status', 'method', 'text', 'words', 'issues'}:
                raise ValueError()
            if not isinstance(page['text'], str) or len(page['text']) > 50_000:
                raise ValueError()
            chars += len(page['text'])
            if not set(page['issues']) <= READER_CODES:
                raise ValueError()
            if any(set(word) != {'text', 'bbox', 'confidence'} for word in page['words']):
                raise ValueError()
        if chars > 250_000 or value['issues'] != sorted({issue for page in pages.values() for issue in page['issues']}):
            raise ValueError()
        complete = all(page['status'] in {'TEXT_EXTRACTED', 'OCR_CANDIDATE'} and not page['issues'] for page in pages.values())
        if value['complete'] != complete:
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError):
        raise WorkerError('PROCESS_RESPONSE_INVALID') from None


def _distinct_candidates(candidates):
    seen, result = set(), []
    for candidate in candidates:
        canonical = json.dumps(candidate, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        if canonical not in seen:
            seen.add(canonical); result.append(candidate)
    return result


def _ai_result(value, pages):
    try:
        from .emergency_local_ai import TextCandidate
        allowed = {'mode', 'status', 'candidates', 'reason_code', 'human_review_required', 'formal_decision', 'accuracy_measured', 'inspected_pages'}
        if (not isinstance(value, dict) or set(value)-allowed or value.get('status') not in {
                'NOT_CONFIGURED', 'UNAVAILABLE', 'REVIEW_REQUIRED', 'NO_CANDIDATE'}
                or not isinstance(value.get('candidates'), list) or len(value['candidates']) > 50):
            raise ValueError()
        if value.get('human_review_required', True) is not True or value.get('formal_decision', False) is not False or value.get('accuracy_measured', False) is not False:
            raise ValueError()
        if value.get('mode', 'text') != 'text': raise ValueError()
        if value['status'] != 'REVIEW_REQUIRED' and value['candidates']:
            raise ValueError()
        reason = value.get('reason_code')
        if reason is not None and (not isinstance(reason, str) or len(reason) > 80 or not all(c.isupper() or c == '_' for c in reason)):
            raise ValueError()
        texts = {page['page']: page['text'] for page in pages or []}
        candidates = []
        for item in value['candidates']:
            if not isinstance(item, dict) or item.get('state') != 'unconfirmed':
                raise ValueError()
            candidate = TextCandidate.model_validate({key: content for key, content in item.items() if key != 'state'})
            if candidate.page not in texts or candidate.quote not in texts[candidate.page]:
                raise ValueError()
            candidates.append({**candidate.model_dump(exclude_none=True), 'state': 'unconfirmed'})
        if 'inspected_pages' in value and (type(value['inspected_pages']) is not int or not 0 <= value['inspected_pages'] <= len(texts)):
            raise ValueError()
        return {**value, 'mode': 'text', 'candidates': _distinct_candidates(candidates), 'human_review_required': True, 'formal_decision': False, 'accuracy_measured': False}
    except (ValueError, TypeError, KeyError):
        raise WorkerError('PROCESS_RESPONSE_INVALID') from None


def _vision_result(value, page):
    try:
        from .emergency_local_ai import ImageCandidate
        allowed = {'mode', 'status', 'candidates', 'reason_code', 'human_review_required', 'formal_decision', 'accuracy_measured', 'width', 'height'}
        if (not isinstance(value, dict) or set(value)-allowed or value.get('status') not in {
                'NOT_CONFIGURED', 'UNAVAILABLE', 'REVIEW_REQUIRED', 'NO_CANDIDATE'}
                or not isinstance(value.get('candidates'), list) or len(value['candidates']) > 100):
            raise ValueError()
        if (value.get('mode', 'vision') != 'vision' or value.get('human_review_required', True) is not True
                or value.get('formal_decision', False) is not False or value.get('accuracy_measured', False) is not False):
            raise ValueError()
        if value['status'] != 'REVIEW_REQUIRED' and value['candidates']: raise ValueError()
        reason = value.get('reason_code')
        if reason is not None and (not isinstance(reason, str) or len(reason) > 80 or not all(c.isupper() or c == '_' for c in reason)):
            raise ValueError()
        if 'width' in value or 'height' in value:
            if (type(value.get('width')) is not int or type(value.get('height')) is not int
                    or value['width'] <= 0 or value['height'] <= 0 or value['width'] * value['height'] > MAX_RENDER_PIXELS):
                raise ValueError()
        candidates = []
        for item in value['candidates']:
            if not isinstance(item, dict) or item.get('state') != 'unconfirmed' or type(item.get('page')) is not int or item['page'] != page:
                raise ValueError()
            candidate = ImageCandidate.model_validate({key: content for key, content in item.items() if key not in {'state', 'page'}})
            candidates.append({**candidate.model_dump(mode='json'), 'page': page, 'state': 'unconfirmed'})
        return {**value, 'mode': 'vision', 'candidates': _distinct_candidates(candidates), 'human_review_required': True, 'formal_decision': False, 'accuracy_measured': False}
    except (ValueError, TypeError, KeyError):
        raise WorkerError('PROCESS_RESPONSE_INVALID') from None


def run_isolated(mode, data, *, page=None, pages=None):
    """Public safe-error boundary, supported on Linux servers in this release."""
    if not NATIVE_PLATFORM_SUPPORTED:
        raise WorkerError('PROCESS_PLATFORM_UNSUPPORTED')
    try:
        return _run_isolated(mode, data, page=page, pages=pages)
    except WorkerError:
        raise
    except Exception:
        raise WorkerError('PROCESS_FAILED') from None


def _run_isolated(mode, data, *, page=None, pages=None):
    """Fixed pipe protocol; bound stdout, kill descendants, discard native stderr.

    OCR's unavoidable temporary images/TSV are confined to a mode0700 folder,
    removed even after the child is killed. OS service hardening remains needed
    for native-library vulnerabilities and the separately managed local model.
    """
    if mode not in OUTPUT_LIMITS or type(data) is not bytes or len(data) > MAX_SOURCE_BYTES:
        raise WorkerError('PROCESS_INPUT_INVALID')
    if mode in {'render', 'vision'} and (type(page) is not int or not 1 <= page <= 50):
        raise WorkerError('PAGE_OUT_OF_RANGE')
    timeout = MODE_TIMEOUTS.get(mode, settings.emergency_audit_worker_timeout)
    payload = {'mode': mode, 'data': b64encode(data).decode('ascii'), 'page': page, 'pages': pages,
               'language': settings.emergency_audit_ocr_language, 'model': settings.emergency_audit_ai_model,
               'port': settings.emergency_audit_ai_port, 'timeout': max(1, math.ceil(timeout))}
    try:
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, RecursionError):
        raise WorkerError('PROCESS_INPUT_INVALID') from None
    if len(content) > MAX_INPUT_BYTES:
        raise WorkerError('PROCESS_INPUT_INVALID')
    collected = bytearray(); overflow = Event(); pipe_failed = Event()
    with tempfile.TemporaryDirectory(prefix='fire-ai-reader-') as private_temp:
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'LD_LIBRARY_PATH', 'LANG', 'LC_ALL', 'TZ', 'TESSDATA_PREFIX') if key in os.environ}
        env.update(TMPDIR=private_temp, TMP=private_temp, TEMP=private_temp,
                   PYTHONIOENCODING='utf-8', OMP_THREAD_LIMIT='2')
        try:
            process = subprocess.Popen(_child_command(), cwd=Path(__file__).resolve().parent.parent,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, start_new_session=os.name == 'posix')
        except (OSError, ValueError):
            raise WorkerError('PROCESS_FAILED') from None
        def send():
            try:
                process.stdin.write(content); process.stdin.close()
            except (OSError, ValueError):
                pipe_failed.set()
        def receive():
            try:
                while chunk := process.stdout.read(64 * 1024):
                    if len(collected) + len(chunk) > OUTPUT_LIMITS[mode]:
                        overflow.set(); _terminate(process); return
                    collected.extend(chunk)
            except (OSError, ValueError):
                pipe_failed.set()
        writer = Thread(target=send, daemon=True); receiver = Thread(target=receive, daemon=True)
        writer.start(); receiver.start()
        try:
            process.wait(timeout=timeout)
            writer.join(timeout=2); receiver.join(timeout=2)
            if overflow.is_set(): raise WorkerError('PROCESS_OUTPUT_LIMIT')
            if writer.is_alive() or receiver.is_alive() or pipe_failed.is_set() or process.returncode != 0:
                raise WorkerError('PROCESS_FAILED')
        except subprocess.TimeoutExpired:
            raise WorkerError('PROCESS_TIMEOUT') from None
        finally:
            _terminate(process)
            process.wait(timeout=5)
            writer.join(timeout=2); receiver.join(timeout=2)
            process.stdin.close(); process.stdout.close()
    try:
        envelope = _decode(bytes(collected))
        if not isinstance(envelope, dict) or type(envelope.get('ok')) is not bool:
            raise ValueError()
        if envelope['ok'] is False:
            if set(envelope) != {'ok', 'code'} or envelope['code'] not in WORKER_CODES:
                raise ValueError()
            raise WorkerError(envelope['code'])
        if set(envelope) != {'ok', 'result'}:
            raise ValueError()
        result = envelope['result']
        if mode == 'inspect':
            if (not isinstance(result, dict) or set(result) != {'media_type', 'page_count'}
                    or result['media_type'] not in {'application/pdf', 'image/png', 'image/jpeg'}
                    or type(result['page_count']) is not int or not 1 <= result['page_count'] <= 50):
                raise ValueError()
            return result
        if mode == 'render':
            if not isinstance(result, str): raise ValueError()
            png = b64decode(result, validate=True)
            if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
                raise ValueError()
            width, height = struct.unpack('>II', png[16:24])
            if not width or not height or width * height > MAX_RENDER_PIXELS:
                raise ValueError()
            return png
        if mode == 'read': return _read_result(result)
        return _ai_result(result, pages) if mode == 'ai' else _vision_result(result, page)
    except WorkerError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise WorkerError('PROCESS_RESPONSE_INVALID') from None


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _enabled(report):
    if not settings.emergency_audit_enabled or not vault.ready():
        return False
    if report.dataset_kind == 'synthetic':
        return True
    return bool(report.dataset_kind == 'internal_trial' and settings.emergency_audit_internal_enabled
                and settings.production_mode and settings.tenant_id and settings.cookie_secure
                and settings.database_url.startswith('postgresql'))


def _authority(db, job, report):
    actor = db.get(User, job.requested_by, populate_existing=True)
    if not actor or not actor.active or actor.employee_id != job.requested_employee_id or not employee_available(db, actor):
        return False
    rights = permission_codes(db, actor.user_id)
    if not REQUIRED_RIGHTS <= rights:
        return False
    return ('emergency.audit.read_all' in rights or bool(actor.employee_id and (
        (report.owner_id == actor.user_id and report.owner_employee_id == actor.employee_id)
        or (report.reviewer_id == actor.user_id and report.reviewer_employee_id == actor.employee_id))))


def _context(db, job):
    revision = db.get(AuditRevision, job.revision_id, populate_existing=True)
    report = db.get(AuditReport, revision.report_id, populate_existing=True) if revision else None
    if revision is None or report is None or report.current_revision_id != job.revision_id or revision.version != job.revision_version:
        return report, revision, 'STALE_REVISION'
    if revision.source_sha256 != job.source_sha256:
        return report, revision, 'SOURCE_CHANGED'
    if not _enabled(report):
        return report, revision, 'AUDIT_UNAVAILABLE'
    if not _authority(db, job, report):
        return report, revision, 'AUTHORITY_CHANGED'
    if job.kind in {'ai', 'vision'}:
        from .emergency_audit_workflow import state
        if state(db, report)['study']['cohort'] == 'baseline':
            return report, revision, 'BASELINE_ASSISTANCE_BLOCKED'
    return report, revision, None


def _audit(db, job):
    write_audit(db, user_id=job.requested_by, action='emergency.audit.worker',
                entity_type='emergency_audit_jobs', entity_id=job.job_id,
                after={'kind': job.kind, 'status': job.status, 'attempts': job.attempts, 'error_code': job.error_code})


def _stop(db, job, code, *, cancelled=False, revision=None):
    job.status = 'cancelled' if cancelled else 'failed'
    job.error_code = code; job.finished_at = now_utc(); job.lease_token = None; job.lease_until = None
    if revision is not None and job.kind == 'read' and revision.version == job.revision_version:
        revision.processing_status = 'failed'; revision.error_code = code
    _audit(db, job)


def _heartbeat(db, identity):
    row = db.get(AuditWorkerHeartbeat, identity)
    if row is None: db.add(AuditWorkerHeartbeat(worker_id=identity, seen_at=now_utc()))
    else: row.seen_at = now_utc()


def _claim(factory, identity):
    with factory() as db:
        account_change_lock(db)
        _heartbeat(db, identity)
        now = now_utc()
        eligible = or_(AuditJob.status == 'queued', (AuditJob.status == 'processing') &
                       or_(AuditJob.lease_until.is_(None), AuditJob.lease_until <= now))
        job = db.scalar(select(AuditJob).where(eligible).order_by(AuditJob.created_at, AuditJob.job_id)
                        .with_for_update(skip_locked=True).limit(1))
        if job is None:
            db.commit(); return None
        report, revision, issue = _context(db, job)
        if issue or job.attempts >= 3:
            _stop(db, job, issue or 'PROCESS_RETRY_LIMIT', cancelled=issue is not None,
                  revision=revision if report and report.current_revision_id == job.revision_id else None)
            db.commit(); return {'skipped': True}
        old_status, old_attempts, old_lease = job.status, job.attempts, job.lease_token
        token = str(uuid4())
        taken = db.execute(update(AuditJob).where(AuditJob.job_id == job.job_id, eligible,
            AuditJob.status == old_status, AuditJob.attempts == old_attempts, AuditJob.lease_token == old_lease)
            .values(status='processing', attempts=old_attempts+1, lease_token=token,
                    lease_until=now+timedelta(seconds=settings.emergency_audit_worker_timeout+90),
                    started_at=now, finished_at=None, error_code=None).execution_options(synchronize_session=False)).rowcount
        if taken != 1:
            db.rollback(); return None
        db.refresh(job)
        if job.kind == 'read': revision.processing_status = 'processing'; revision.error_code = None
        config = db.get(AuditConfiguration, revision.profile_id) if revision.profile_id else None
        claim = {'job_id': job.job_id, 'token': token, 'kind': job.kind, 'revision_id': revision.revision_id,
                 'page_number': job.page_number,
                 'source_sha256': job.source_sha256, 'size_bytes': revision.size_bytes, 'page_count': revision.page_count,
                 'profile_id': revision.profile_id, 'profile_version': config.version if config else None,
                 'profile_cipher': config.definition_cipher if config else None,
                 'reading_cipher': revision.reading_cipher}
        _audit(db, job); db.commit(); return claim


def _original(claim):
    data = vault.read_original('revision', claim['revision_id'])
    if len(data) != claim['size_bytes'] or sha256(data).hexdigest() != claim['source_sha256']:
        raise vault.VaultError('PRIVATE_CONTENT_INTEGRITY')
    return data


def _execute(claim, executor):
    data = _original(claim)
    if claim['kind'] == 'read':
        reading = _read_result(executor('read', data))
        if reading['page_count'] != claim['page_count']:
            raise WorkerError('PROCESS_RESPONSE_INVALID')
        fields = {}
        if claim['profile_id']:
            definition = ProfileDefinition.model_validate(vault.open_json('config', claim['profile_id'], claim['profile_cipher']))
            fields = map_fields(reading, definition)
            for item in definition.fields:
                fields[item.field_id].update(label=item.label, value_type=item.value_type, unit=item.unit, phase=item.phase)
        result = {'reading_cipher': vault.seal_json('reading', claim['revision_id'], reading),
                  'fields_cipher': vault.seal_json('fields', claim['revision_id'], fields),
                  'processing_status': 'ready' if reading['complete'] else 'partial', 'error_code': None}
    elif claim['kind'] == 'ai':
        reading = vault.open_json('reading', claim['revision_id'], claim['reading_cipher'])
        if reading is None: raise WorkerError('AI_READING_UNAVAILABLE')
        pages = _read_result(reading)['pages']
        ai = _ai_result(executor('ai', b'', pages=pages), pages)
        result = {'ai_cipher': vault.seal_json('ai', claim['revision_id'], ai)}
    else:
        page = claim['page_number']
        if type(page) is not int or not 1 <= page <= claim['page_count']:
            raise WorkerError('PAGE_OUT_OF_RANGE')
        vision = _vision_result(executor('vision', data, page=page), page)
        result = {'ai_cipher': vault.seal_json('ai', claim['revision_id'], vision)}
    _original(claim)  # Detect replacement/tampering while native/model work ran.
    return result


def _while_running(factory, identity, claim, stop):
    """Publish liveness separately; this never extends a processing lease."""
    while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        try:
            with factory() as db:
                job = db.get(AuditJob, claim['job_id'])
                if (job is None or job.status != 'processing' or job.lease_token != claim['token']
                        or job.lease_until is None or _utc(job.lease_until) <= now_utc()):
                    return
                _heartbeat(db, identity)
                db.commit()
        except Exception:
            # Maintenance / unavailable DB cannot be bypassed by a background
            # heartbeat. Publication still needs its own fresh BoundSession.
            return


def _publish(factory, identity, claim, result, error):
    with factory() as db:
        account_change_lock(db)
        _heartbeat(db, identity)
        job = db.scalar(select(AuditJob).where(AuditJob.job_id == claim['job_id']).with_for_update())
        if (job is None or job.status != 'processing' or job.lease_token != claim['token']
                or job.lease_until is None or _utc(job.lease_until) <= now_utc()):
            db.commit(); return
        report, revision, issue = _context(db, job)
        config = db.get(AuditConfiguration, revision.profile_id) if revision and revision.profile_id else None
        if not issue and (revision.profile_id != claim['profile_id']
                or (config and (config.version != claim['profile_version'] or config.definition_cipher != claim['profile_cipher']))
                or (claim['profile_id'] and config is None)):
            issue = 'CONFIGURATION_CHANGED'
        if issue:
            _stop(db, job, issue, cancelled=True,
                  revision=revision if report and report.current_revision_id == job.revision_id else None)
        elif error:
            if error in RETRYABLE and job.attempts < 3:
                job.status = 'queued'; job.error_code = error; job.lease_token = None; job.lease_until = None
                if job.kind == 'read': revision.processing_status = 'queued'; revision.error_code = error
                _audit(db, job)
            else:
                _stop(db, job, error, revision=revision)
        else:
            changed = db.execute(update(AuditRevision).where(AuditRevision.revision_id == revision.revision_id,
                AuditRevision.version == job.revision_version).values(**result,
                    **({'version': job.revision_version+1, 'ai_cipher': None} if job.kind == 'read' else {}))
                .execution_options(synchronize_session=False)).rowcount
            if changed != 1:
                db.rollback(); return
            # The report may have gained independent measurement/history events
            # during work. Preserve them and increment its CURRENT version.
            published = db.execute(update(AuditReport).where(AuditReport.report_id == report.report_id,
                AuditReport.current_revision_id == job.revision_id).values(version=AuditReport.version+1)).rowcount
            if published != 1:
                db.rollback(); return
            if job.kind in {'ai', 'vision'}:
                ai_result = vault.open_json('ai', revision.revision_id, result['ai_cipher'])
                if ai_result['status'] in {'REVIEW_REQUIRED', 'NO_CANDIDATE'}:
                    from .emergency_audit_workflow import record_ai_run
                    db.refresh(report); db.refresh(revision)
                    record_ai_run(db, report, revision, job, ai_result)
            job.status = 'done'; job.error_code = None; job.finished_at = now_utc(); job.lease_token = None; job.lease_until = None
            _audit(db, job)
        db.commit()


def process_one(*, session_factory=SessionLocal, worker_id: str | None = None, executor=None) -> bool:
    """Process at most one persisted job. False means no claimable work."""
    if not settings.emergency_audit_enabled:
        return False
    try:
        identity = str(UUID(worker_id or DEFAULT_WORKER_ID))
    except (ValueError, TypeError, AttributeError):
        raise WorkerError('PROCESS_INPUT_INVALID') from None
    claim = _claim(session_factory, identity)
    if claim is None: return False
    if claim.get('skipped'): return True
    result, error = None, None
    stopped = Event()
    heartbeat = Thread(target=_while_running, args=(session_factory, identity, claim, stopped), daemon=True)
    heartbeat.start()
    try:
        result = _execute(claim, executor or run_isolated)
    except (WorkerError, ReaderError, vault.VaultError) as failure:
        error = failure.code if failure.code in WORKER_CODES else 'PROCESS_FAILED'
    except (ValueError, TypeError, KeyError):
        error = 'PROCESS_RESPONSE_INVALID'
    except Exception:
        error = 'PROCESS_FAILED'
    finally:
        stopped.set()
        heartbeat.join(timeout=5)
    _publish(session_factory, identity, claim, result, error)
    return True
