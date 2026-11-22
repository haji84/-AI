"""Private original/derivative API, separate from every shared Document consumer."""
from datetime import timedelta
import json
import shutil
import subprocess
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import emergency_audit_service as svc
from .. import emergency_audit_workflow as workflow
from .. import emergency_vault as vault
from ..authz import current_user, permission_codes, require_mutation_permission, require_permission
from ..db import get_db
from ..department_maintenance import MaintenanceUnavailable
from ..emergency_audit_models import AuditConfiguration, AuditJob, AuditReport, AuditRevision, AuditRun, AuditSource, AuditWorkerHeartbeat
from ..emergency_audit_schemas import (AnnotatedPDF, ApproveConfiguration, AssignReviewer, CheckRevision, ConfirmFields,
    ImpactInput, MapRevision, MeasurementExport, PatternInput, SaveConfiguration, SaveDispositions, SaveEvent, VersionInput, VisionInput)
from ..models import Employee, User, now_utc
from ..personnel import employee_available
from ..settings import settings

MAX_UPLOAD = 25 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
PRIVATE_HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff',
                   'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; sandbox"}


class PrivateAuditRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def protected(request):
            try:
                if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                    origin = request.headers.get('origin')
                    if (origin and origin != str(request.base_url).rstrip('/')) or request.headers.get('sec-fetch-site') == 'cross-site':
                        raise HTTPException(403, '同じ画面から操作してください。')
                    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
                    if media not in {'application/json', 'multipart/form-data'}:
                        raise HTTPException(415, '所定の入力形式で送信してください。')
                    limit = MAX_UPLOAD + 65536 if media == 'multipart/form-data' else MAX_JSON
                    size = 0; chunks = []
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(413, 'ファイル・入力の容量が上限を超えています。')
                        chunks.append(chunk)
                    request._body = b''.join(chunks)
                result = await original(request)
            except (RequestValidationError, ValidationError, UnicodeError, RecursionError, ValueError, TypeError):
                result = JSONResponse(status_code=422, content={'detail': '入力の形式・値・様式を確認してください。'})
            except vault.VaultError:
                result = JSONResponse(status_code=503, content={'detail': '原本の保護・整合性を確認できません。管理担当者に連絡してください。'})
            except IntegrityError:
                result = JSONResponse(status_code=409, content={'detail': '別の操作と重なりました。再読込してください。'})
            except MaintenanceUnavailable:
                result = JSONResponse(status_code=503, content={'detail': '保守中です。後ほど再読込してください。'},
                                      headers={'Retry-After': '30'})
            except StarletteHTTPException as error:
                result = JSONResponse(status_code=error.status_code, content={'detail': error.detail if error.status_code != 400
                    else 'ファイル・入力の形式を確認してください。'}, headers=error.headers)
            result.headers.update(PRIVATE_HEADERS)
            return result
        return protected


router = APIRouter(prefix='/emergency/audit', tags=['emergency-audit'], route_class=PrivateAuditRoute)


def read_access(db: Session = Depends(get_db), user: User = Depends(require_permission('emergency.report.read'))):
    svc.require_details(db, user); return user


def write_access(db: Session = Depends(get_db), user: User = Depends(require_mutation_permission('emergency.report.create'))):
    svc.require_details(db, user); return user


def config_access(db: Session = Depends(get_db), user: User = Depends(require_mutation_permission('emergency.audit.configure'))):
    svc.require_details(db, user); return user


def approval_access(db: Session = Depends(get_db), user: User = Depends(require_mutation_permission('emergency.audit.approve'))):
    svc.require_details(db, user); return user


def event_access(payload: SaveEvent, db: Session = Depends(get_db), user: User = Depends(current_user)):
    code = 'emergency.report.review' if payload.kind == 'truth_review' else 'emergency.report.create'
    if payload.kind == 'work_interval' and 'emergency.report.create' not in permission_codes(db, user.user_id):
        code = 'emergency.report.review'
    # Invoke the same serializing mutation guard with explicit dependencies.
    result = require_mutation_permission(code)(user=user, db=db)
    svc.require_details(db, result); return result


def decision_access(db: Session = Depends(get_db), user: User = Depends(current_user)):
    code = 'emergency.report.create' if 'emergency.report.create' in permission_codes(db, user.user_id) else 'emergency.report.review'
    result = require_mutation_permission(code)(user=user, db=db)
    svc.require_details(db, result); return result


def _config_service():
    from .. import emergency_audit_config_service
    return emergency_audit_config_service


def config_response(db, row, user):
    result = _config_service().config_output(db, row)
    impact = result.get('impact')
    rights = permission_codes(db, user.user_id)
    if impact:
        identities = {item['report_id'] for item in impact.get('reports', [])}
        can_manage = bool({'emergency.audit.configure', 'emergency.audit.approve'} & rights)
        visible = set(db.scalars(svc.reports_query(db, user).with_only_columns(AuditReport.report_id)
                                .where(AuditReport.report_id.in_(identities)))) if can_manage else set()
        if not can_manage or visible != identities:
            # A shared rule definition is not a grant to private source reports,
            # their hashes, existence, counts or inspection outcomes.
            result['impact'] = None
    return result


def _isolated(mode, data, **kwargs):
    from ..emergency_audit_worker import WorkerError, run_isolated
    try:
        return run_isolated(mode, data, **kwargs)
    except WorkerError as error:
        if mode == 'review_pdf':
            if error.code in {'PDF_OUTPUT_LIMIT', 'PDF_APPENDIX_LIMIT', 'PROCESS_OUTPUT_LIMIT'}:
                raise HTTPException(413, '訂正確認用PDFの出力上限を超えました。途中を省略したPDFは返していません。') from None
            if error.code in {'PROCESS_TIMEOUT', 'TOTAL_TIMEOUT', 'PDF_FONT_UNAVAILABLE', 'PROCESS_PLATFORM_UNSUPPORTED'}:
                raise HTTPException(503, '訂正確認用PDFの生成期限または実行環境を確認できません。PDFは返していません。') from None
            raise HTTPException(422, '訂正確認用PDFを全件出力できません。原本の形式・ページ数・検査結果を確認してください。') from None
        raise HTTPException(422, 'この原本を安全に処理できません。形式・ページ数・保護設定を確認してください。') from None


async def _upload(file):
    try:
        value = await file.read(MAX_UPLOAD + 1)
    finally:
        await file.close()
    if not value or len(value) > MAX_UPLOAD:
        raise HTTPException(413, '空のファイル、または容量上限を超えたファイルです。')
    return value


@router.get('/capabilities')
def capabilities(db: Session = Depends(get_db), user: User = Depends(read_access)):
    languages = []
    binary = shutil.which('tesseract')
    if binary:
        try:
            check = subprocess.run([binary, '--list-langs'], capture_output=True, timeout=3, check=False)
            languages = [line.strip() for line in check.stdout.decode('utf-8', 'replace').splitlines()[1:]
                         if line.strip() in {'jpn', 'jpn_vert', 'eng', 'osd'}]
        except (OSError, subprocess.TimeoutExpired):
            pass
    seen = db.scalar(select(func.max(AuditWorkerHeartbeat.seen_at)))
    running = seen is not None and workflow.aware(seen) >= now_utc() - timedelta(seconds=60)
    # Queue counts are scoped to visible reports, not other employees' records.
    visible = svc.reports_query(db, user).with_only_columns(AuditReport.report_id)
    count = db.scalar(select(func.count()).select_from(AuditJob).join(AuditRevision,
        AuditRevision.revision_id == AuditJob.revision_id).where(AuditRevision.report_id.in_(visible),
        AuditJob.status.in_(['queued', 'processing'])))
    return {'enabled': settings.emergency_audit_enabled, 'storage_ready': vault.ready(),
        'internal_enabled': bool(settings.emergency_audit_internal_enabled and settings.production_mode and settings.tenant_id),
        'ocr': {'available': bool(binary), 'languages': languages, 'japanese': 'jpn' in languages},
        'ai': {'configured': bool(settings.emergency_audit_ai_model)},
        'worker': {'status': 'running' if running else 'unavailable', 'pending': count},
        'limits': {'max_file_bytes': MAX_UPLOAD, 'max_pages': 50},
        'permissions': sorted(permission_codes(db, user.user_id))}


@router.get('/reviewers')
def reviewers(db: Session = Depends(get_db), user: User = Depends(read_access)):
    values = []
    for person in db.scalars(select(User).where(User.active.is_(True), User.employee_id.is_not(None))):
        if (person.user_id != user.user_id and employee_available(db, person) and
            svc.DETAIL_RIGHTS | {'emergency.report.review'} <= permission_codes(db, person.user_id)):
            employee = db.get(Employee, person.employee_id)
            values.append({'user_id': person.user_id, 'display_name': employee.display_name})
    return values


@router.get('/reports')
def listing(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: User = Depends(read_access)):
    rows = db.scalars(svc.reports_query(db, user).order_by(AuditReport.created_at.desc(), AuditReport.report_id)
                      .offset(offset).limit(limit))
    return [svc.summary(db, row, user) for row in rows]


@router.post('/reports', status_code=201)
async def upload_report(response: Response, request_id: UUID = Form(...), dataset_kind: str = Form(...),
    profile_id: UUID | None = Form(None), file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(write_access)):
    svc.allow_dataset(dataset_kind)
    identity = user.user_id
    # Release account/session/maintenance transaction before parsing a file.
    db.rollback()
    value = await _upload(file)
    metadata = await run_in_threadpool(_isolated, 'inspect', value)
    user = require_mutation_permission('emergency.report.create')(user=db.get(User, identity), db=db)
    svc.require_details(db, user)
    row, created = svc.create_report(db, user, value, metadata, request_id, dataset_kind, profile_id)
    if not created: response.status_code = 200
    return svc.output(db, row, user)


@router.get('/reports/{identity}')
def report_detail(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    row = svc.report(db, user, identity)
    svc.audit(db, user, 'read', row.report_id); db.commit()
    return svc.output(db, row, user)


@router.post('/reports/{identity}/annotated-pdf')
async def annotated_pdf(identity: UUID, payload: AnnotatedPDF,
    db: Session = Depends(get_db), user: User = Depends(read_access)):
    from ..emergency_audit_export import capture_export
    before, _, revision, _ = capture_export(db, user.user_id, identity, payload)
    value = svc.verified_original(revision)
    # Native work holds no database transaction, account lock or private file.
    db.rollback()
    rendered = await run_in_threadpool(_isolated, 'review_pdf', value, export_plan=before.plan)
    after, parent, _, actor = capture_export(db, before.user_id, identity, payload,
                                           expected_employee_id=before.employee_id)
    if before.guard != after.guard:
        svc.failure(409, '生成中に検査・確認結果・設定が変わりました。再読込してください。')
    svc.audit(db, actor, 'pdf_export', parent.report_id, version=parent.version,
              count=len(before.plan['findings']), kind=before.plan['mode'])
    db.commit()
    return Response(rendered, media_type='application/pdf',
                    headers={'Content-Disposition': 'attachment; filename="emergency-review.pdf"'})


@router.post('/reports/{identity}/revisions', status_code=201)
async def replace_report(identity: UUID, response: Response, request_id: UUID = Form(...), expected_version: int = Form(...),
    profile_id: UUID | None = Form(None), file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(write_access)):
    parent = svc.report(db, user, identity); dataset_kind = parent.dataset_kind; user_id = user.user_id
    db.rollback(); value = await _upload(file)
    metadata = await run_in_threadpool(_isolated, 'inspect', value)
    user = require_mutation_permission('emergency.report.create')(user=db.get(User, user_id), db=db)
    row, created = svc.create_report(db, user, value, metadata, request_id, dataset_kind, profile_id,
                                    report_id=identity, expected_version=expected_version)
    if not created: response.status_code = 200
    return svc.output(db, row, user)


@router.get('/revisions/{identity}')
def revision_detail(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    parent, row = svc.revision(db, user, identity)
    return svc.output(db, parent, user, selected_revision=row.revision_id)


@router.get('/revisions/{identity}/original')
def original(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    parent, row = svc.revision(db, user, identity)
    value = svc.verified_original(row)
    svc.audit(db, user, 'original_read', parent.report_id, number=row.number); db.commit()
    extension = {'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg'}[row.media_type]
    return Response(value, media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="report-{row.number}.{extension}"'})


@router.get('/revisions/{identity}/pages/{page}.png')
async def page_preview(identity: UUID, page: int, db: Session = Depends(get_db), user: User = Depends(read_access)):
    parent, row = svc.revision(db, user, identity)
    if page < 1 or page > row.page_count: raise HTTPException(404, 'ページを確認してください。')
    value = svc.verified_original(row); user_id = user.user_id
    db.rollback(); rendered = await run_in_threadpool(_isolated, 'render', value, page=page)
    # Revalidate the originating session after slow private rendering.
    from ..authz import revalidate_session
    revalidate_session(db, user_id)
    user = db.get(User, user_id, populate_existing=True)
    if not user or not user.active or not employee_available(db, user): svc.failure(403)
    parent, row = svc.revision(db, user, identity)
    svc.audit(db, user, 'page_read', parent.report_id, number=page); db.commit()
    return Response(rendered, media_type='image/png')


@router.post('/revisions/{identity}/mapping')
def mapping(identity: UUID, payload: MapRevision, db: Session = Depends(get_db), user: User = Depends(write_access)):
    return svc.output(db, svc.remap(db, user, identity, payload), user)


@router.post('/revisions/{identity}/fields')
def fields(identity: UUID, payload: ConfirmFields, db: Session = Depends(get_db), user: User = Depends(write_access)):
    return svc.output(db, svc.confirm_fields(db, user, identity, payload), user)


@router.post('/revisions/{identity}/retry')
def retry(identity: UUID, payload: VersionInput, db: Session = Depends(get_db), user: User = Depends(write_access)):
    return svc.output(db, svc.retry(db, user, identity, payload), user)


@router.post('/revisions/{identity}/ai')
def ai(identity: UUID, payload: VersionInput, db: Session = Depends(get_db), user: User = Depends(write_access)):
    parent, _ = svc.revision(db, user, identity, current=True); workflow.permit_assistance(db, parent)
    return svc.output(db, svc.retry(db, user, identity, payload, 'ai'), user)


@router.post('/revisions/{identity}/checks')
def checks(identity: UUID, payload: CheckRevision, db: Session = Depends(get_db), user: User = Depends(write_access)):
    return svc.output(db, workflow.check(db, user, identity, payload), user)


@router.post('/revisions/{identity}/vision')
def vision(identity: UUID, payload: VisionInput, db: Session = Depends(get_db), user: User = Depends(write_access)):
    parent, _ = svc.revision(db, user, identity, current=True); workflow.permit_assistance(db, parent)
    return svc.output(db, svc.retry(db, user, identity, payload, 'vision'), user)


@router.post('/runs/{identity}/decisions')
def decisions(identity: UUID, payload: SaveDispositions, db: Session = Depends(get_db), user: User = Depends(decision_access)):
    return svc.output(db, workflow.save_dispositions(db, user, identity, payload), user)


@router.get('/runs/{identity}')
def run_detail(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    row = db.get(AuditRun, str(identity))
    if not row: svc.failure(404)
    parent, revision = svc.revision(db, user, row.revision_id)
    return svc.run_output(db, row, parent, revision)


@router.post('/reports/{identity}/reviewer')
def assign(identity: UUID, payload: AssignReviewer, db: Session = Depends(get_db), user: User = Depends(write_access)):
    return svc.output(db, svc.assign_reviewer(db, user, identity, payload), user)


@router.post('/reports/{identity}/events')
def add_event(identity: UUID, payload: SaveEvent, db: Session = Depends(get_db), user: User = Depends(event_access)):
    return svc.output(db, workflow.save_event(db, user, identity, payload), user)


@router.get('/reports/{identity}/measurement')
def report_measurement(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return workflow.measurement(db, svc.report(db, user, identity))


@router.post('/measurement-export')
def measurement_export(payload: MeasurementExport, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return workflow.export_measurement(db, user, payload)


@router.post('/correction-patterns')
def correction_patterns(payload: PatternInput, db: Session = Depends(get_db), user: User = Depends(read_access)):
    from ..emergency_audit_learning import summarize_patterns
    return summarize_patterns(db, user, payload.report_ids)


@router.get('/profiles')
def profiles(db: Session = Depends(get_db), user: User = Depends(read_access)):
    return [config_response(db, row, user) for row in db.scalars(select(AuditConfiguration)
        .where(AuditConfiguration.kind == 'profile').order_by(AuditConfiguration.created_at.desc()))]


@router.get('/rule-sets')
def rule_sets(db: Session = Depends(get_db), user: User = Depends(read_access)):
    return [config_response(db, row, user) for row in db.scalars(select(AuditConfiguration)
        .where(AuditConfiguration.kind == 'rules').order_by(AuditConfiguration.created_at.desc()))]


def save_config(db, user, kind, payload, response):
    row, created = _config_service().create_config(db, user, kind, payload)
    if not created: response.status_code = 200
    return config_response(db, row, user)


@router.post('/profiles', status_code=201)
def new_profile(payload: SaveConfiguration, response: Response, db: Session = Depends(get_db), user: User = Depends(config_access)):
    return save_config(db, user, 'profile', payload, response)


@router.post('/rule-sets', status_code=201)
def new_rules(payload: SaveConfiguration, response: Response, db: Session = Depends(get_db), user: User = Depends(config_access)):
    return save_config(db, user, 'rules', payload, response)


@router.get('/configurations/{identity}')
def configuration(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return config_response(db, svc.configuration(db, identity), user)


@router.post('/configurations/{identity}/impact')
def impact(identity: UUID, payload: ImpactInput, db: Session = Depends(get_db), user: User = Depends(config_access)):
    return config_response(db, _config_service().impact_config(db, user, identity, payload), user)


@router.post('/configurations/{identity}/approve')
def approve(identity: UUID, payload: ApproveConfiguration, db: Session = Depends(get_db), user: User = Depends(approval_access)):
    return config_response(db, _config_service().approve_config(db, user, identity, payload), user)


@router.post('/configurations/{identity}/retire')
def retire(identity: UUID, payload: VersionInput, db: Session = Depends(get_db), user: User = Depends(approval_access)):
    return config_response(db, _config_service().retire_config(db, user, identity, payload), user)


@router.post('/sources', status_code=201)
async def upload_source(response: Response, request_id: UUID = Form(...), file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(config_access)):
    identity = user.user_id; db.rollback(); value = await _upload(file)
    metadata = await run_in_threadpool(_isolated, 'inspect', value)
    user = require_mutation_permission('emergency.audit.configure')(user=db.get(User, identity), db=db)
    row, created = _config_service().create_source(db, user, value, metadata, request_id)
    if not created: response.status_code = 200
    return {'source_id': row.source_id, 'media_type': row.media_type, 'page_count': row.page_count, 'sha256': row.source_sha256}


@router.get('/sources')
def source_listing(db: Session = Depends(get_db), user: User = Depends(read_access)):
    if not {'emergency.audit.configure', 'emergency.audit.approve'} & permission_codes(db, user.user_id): svc.failure(403)
    return [{'source_id': row.source_id, 'media_type': row.media_type, 'page_count': row.page_count,
             'sha256': row.source_sha256, 'created_at': row.created_at}
            for row in db.scalars(select(AuditSource).order_by(AuditSource.created_at.desc(), AuditSource.source_id))]


@router.get('/sources/{identity}/pages/{page}.png')
async def source_page(identity: UUID, page: int, db: Session = Depends(get_db), user: User = Depends(read_access)):
    if not {'emergency.audit.configure', 'emergency.audit.approve'} & permission_codes(db, user.user_id): svc.failure(403)
    row = db.get(AuditSource, str(identity))
    if not row or not 1 <= page <= row.page_count: svc.failure(404)
    value = svc.verified_original(row, 'source'); identity_user = user.user_id; db.rollback()
    rendered = await run_in_threadpool(_isolated, 'render', value, page=page)
    from ..authz import revalidate_session
    revalidate_session(db, identity_user)
    user = db.get(User, identity_user, populate_existing=True)
    if not user or not user.active or not employee_available(db, user): svc.failure(403)
    svc.require_details(db, user)
    if not {'emergency.audit.configure', 'emergency.audit.approve'} & permission_codes(db, user.user_id): svc.failure(403)
    svc.audit(db, user, 'source_read', row.source_id, number=page); db.commit()
    return Response(rendered, media_type='image/png')


@router.get('/rule-candidates')
def candidates(group: str = '', query: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0), user: User = Depends(read_access)):
    from ..emergency_rule_catalog import load_candidate_catalog
    catalog = load_candidate_catalog()
    items = catalog['candidates'] if isinstance(catalog, dict) else catalog
    if group: items = [item for item in items if item['candidate_id'].split('-')[0] == group]
    if query: items = [item for item in items if query.casefold() in json.dumps(item, ensure_ascii=False).casefold()]
    return {'total': len(items), 'items': items[offset:offset + limit]}
