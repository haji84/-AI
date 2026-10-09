"""Observed statistics in the real shared shell and API, with synthetic data.

Chromium execution is restricted to the authorized CI job. Held requests are
continued in finally; no response is fabricated or obtained with route.fetch.
"""
import csv
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
    reason='actual Chromium observed-statistics journeys execute in authorized CI',
)
CASE_ID = '11111111-7777-4111-8111-111111111111'
PATIENT_ID = '22222222-7777-4222-8222-222222222222'
KEYS = ['emergency.cases', 'emergency.patient_records', 'operations.incidents',
        'operations.dispatches', 'operations.approved_dispatches', 'fleet.trips',
        'fleet.distance_km']
TITLE = '汎用統計出力（正式様式ではありません）'
SEED = r'''
from datetime import date
from sqlalchemy import select
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import EmergencyCase,EmergencyPatient,User,Role,Permission,RolePermission,UserRole
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 seed_rbac(db)
 admin=db.scalar(select(Role).where(Role.code=='system_admin'));assert admin
 aggregate=Role(code='synthetic_statistics_aggregate',name='Synthetic aggregate reader')
 readonly=Role(code='synthetic_statistics_readonly',name='Synthetic read-only statistics')
 db.add_all([aggregate,readonly]);db.flush()
 base=['statistics.read','emergency.report.read','incident.aggregate','fleet.aggregate','facility.read','inspection.read','submission.read','equipment.read','drawing.read']
 for role,codes in [(aggregate,base+['statistics.record','statistics.export','emergency.report.export','incident.export','fleet.export']),(readonly,base)]:
  for code in codes:
   permission=db.scalar(select(Permission).where(Permission.code==code));assert permission,code
   db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
 for name,role in [('statistics-writer',admin),('statistics-aggregate',aggregate),('statistics-reader',readonly)]:
  user=User(username=name,password_hash=hash_password('synthetic-statistics-password'));db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
 case=EmergencyCase(emergency_case_id='11111111-7777-4111-8111-111111111111',source_case_key='synthetic-statistics-case',call_date=date(2026,1,2),dispatch_number='SYNTHETIC-STATISTICS',incident_address='Synthetic authorized original record')
 db.add(case);db.flush()
 db.add_all([EmergencyPatient(emergency_patient_id='22222222-7777-4222-8222-222222222222',emergency_case_id=case.emergency_case_id,patient_number=1,diagnosis_text='SYNTHETIC_PRIVATE_MEDICAL'),EmergencyPatient(emergency_case_id=case.emergency_case_id,patient_number=2),EmergencyCase(source_case_key='synthetic-empty-patient-case',call_date=date(2026,1,3)),EmergencyCase(source_case_key='synthetic-undated-case',call_date=None)])
 db.commit()
'''


@pytest.fixture
def statistics_browser(tmp_path, request):
    from playwright.sync_api import sync_playwright, expect

    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': str(root / 'backend'),
           'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
           'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'),
           'FIRE_AI_PRODUCTION_MODE': 'false',
           'FIRE_AI_STATISTICS_BUSINESS_TIMEZONE': 'Asia/Tokyo'}
    env.pop('FIRE_AI_TENANT_ID', None)

    def database(script):
        result = subprocess.run([sys.executable, '-c', script], cwd=root, env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    database(SEED)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0))
        port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                               '127.0.0.1', '--port', str(port)], cwd=root, env=env,
                              stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/health', timeout=.2).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError((tmp_path / 'server.log').read_text())
                # Server startup only. Browser interactions use explicit states.
                time.sleep(.1)
        else:
            raise AssertionError('Synthetic statistics server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # A foreign browser zone must not select the business reporting zone.
            context = browser.new_context(timezone_id='America/Los_Angeles', accept_downloads=True)
            page = context.new_page()
            errors = []
            request_events, measurements = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda event: request_events.append({
                'method': event.method, 'path': urlsplit(event.url).path}))
            artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
            artifacts.mkdir(parents=True, exist_ok=True)

            def login(username='statistics-writer'):
                page.goto(base + '/ui/')
                page.locator('#loginUser').fill(username)
                page.locator('#loginPass').fill('synthetic-statistics-password')
                page.get_by_role('button', name='ログイン', exact=True).click()
                expect(page.locator('#statisticsBtn')).to_be_visible()

            def open_statistics():
                with page.expect_response(lambda response: response.url == base + '/statistics/metrics') as response:
                    page.locator('#statisticsBtn').click()
                assert response.value.status == 200, response.value.text()
                expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')

            def select_metrics(keys=KEYS):
                page.locator('#statisticsStart').fill('2026-01-01')
                page.locator('#statisticsEnd').fill('2026-01-31')
                for box in page.locator('[data-statistics-metric]').all():
                    key = box.get_attribute('data-statistics-metric')
                    if box.is_enabled():
                        box.set_checked(key in keys)

            def action(button, path, status=200):
                started, request_start = time.perf_counter(), len(request_events)
                with page.expect_response(lambda response: response.url == base + path) as response:
                    page.locator('#' + button).click()
                assert response.value.status == status, response.value.text()
                expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
                measure(button, started, request_start, 'Expected real response and visible aria-busy=false')
                return response.value.json()

            def measure(name, started, request_start, completion):
                requests = request_events[request_start:]
                counts = {}
                for event in requests:
                    key = event['method'] + ' ' + event['path']
                    counts[key] = counts.get(key, 0) + 1
                measurements.append({'action': name, 'elapsed_seconds': round(time.perf_counter() - started, 4),
                                     'completion': completion, 'requests_started': len(requests),
                                     'request_counts_by_method_and_path': counts})

            try:
                yield {'page': page, 'context': context, 'base': base, 'database': database,
                       'login': login, 'open': open_statistics, 'select': select_metrics,
                       'action': action, 'artifacts': artifacts, 'tmp': tmp_path,
                       'measure': measure, 'request_events': request_events}
            finally:
                (artifacts / ('statistics-timing-' + request.node.name + '.json')).write_text(json.dumps({
                    'synthetic': True, 'browser_timezone': 'America/Los_Angeles',
                    'business_timezone': 'Asia/Tokyo',
                    'measurement_limits': 'Monotonic time begins before UI activation and ends at the stated completion. Counts include all page requests started in that window, including overlapping/background work. Requests begun before the window are excluded. These synthetic timings do not establish real deployment latency or a usability threshold.',
                    'measurements': measurements,
                }, ensure_ascii=False, indent=2) + '\n')
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        logs.close()


def seed_timestamp_sources(ui):
    """Use actual admission APIs so SQLite timestamps have known UTC lineage."""
    page, base = ui['page'], ui['base']

    def post(path, payload):
        response = page.request.post(base + path, data=payload)
        assert response.status == 201, response.text()
        return response.json()

    incident = post('/operations/incidents', {'kind': 'other', 'title': 'Synthetic statistics incident',
                    'occurred_at': '2026-01-01T00:00:00+09:00'})
    for unit in ['Synthetic unit one', 'Synthetic unit two']:
        current = page.request.get(base + '/operations/incidents/' + incident['incident_id']).json()
        post('/operations/incidents/' + incident['incident_id'] + '/dispatches',
             {'expected_version': current['version'], 'unit': unit})
    vehicle = post('/operations/vehicles', {'code': 'SYNTHETIC-STATISTICS-VEHICLE',
                   'name': 'Synthetic statistics vehicle', 'odometer': '0'})
    for day, start, end in [('01', '0', '0.1'), ('02', '0.1', '0.3')]:
        current = page.request.get(base + '/operations/vehicles/' + vehicle['vehicle_id']).json()
        post('/operations/vehicles/' + vehicle['vehicle_id'] + '/trips', {
            'expected_version': current['version'], 'started_at': f'2026-01-{day}T00:00:00+09:00',
            'ended_at': f'2026-01-{day}T01:00:00+09:00', 'start_odometer': start,
            'end_odometer': end, 'purpose': 'Synthetic observed statistics trip'})
    return incident, vehicle


def test_workforce_catalog_actual_query_confirmation_and_frozen_exports(statistics_browser):
    from playwright.sync_api import expect
    ui = statistics_browser
    page = ui['page']
    ui['login']()
    ui['database']("import sys; sys.path.insert(0,'backend/tests')\nfrom test_statistics_workforce import seed_workforce\nfrom app.db import SessionLocal\nfrom app.models import User\nfrom sqlalchemy import select\nwith SessionLocal() as db:\n seed_workforce(db,db.scalar(select(User).where(User.username=='statistics-writer')).user_id)")
    ui['open']()
    keys = ['workforce.approved_rosters','workforce.approved_worked_minutes','workforce.approved_overtime_minutes']
    ui['select'](keys)
    snapshot = ui['action']('statisticsQuery', '/statistics/query')
    assert [m['value'] for m in snapshot['metrics']] == ['3','990','100']
    assert 'PRIVATE' not in json.dumps(snapshot)
    expect(page.locator('#statisticsSnapshot')).to_contain_text('承認済実勤務時間')
    expect(page.locator('#statisticsSnapshot')).to_contain_text('網羅性: unknown')
    saved = ui['action']('statisticsSave', '/statistics/reports', 201)
    key = saved['report_id']
    page.locator('#statisticsReviewNote').fill('Synthetic stored work observations reviewed independently')
    page.locator('#statisticsAcknowledge').check()
    confirmed = ui['action']('statisticsConfirm', '/statistics/reports/'+key+'/confirm')
    assert confirmed['state'] == 'confirmed' and confirmed['snapshot'] == saved['snapshot']
    with page.expect_download() as download:
        page.locator('#statisticsCSV').click()
    path = ui['tmp'] / 'workforce-observed.csv'
    download.value.save_as(path)
    content = path.read_text(encoding='utf-8-sig')
    assert '990' in content and 'approved_overtime_minutes' in content and 'PRIVATE' not in content
    page.screenshot(path=str(ui['artifacts'] / 'statistics-workforce-observed.png'), full_page=True)


def test_real_query_recapture_confirmation_history_and_safe_frozen_downloads(statistics_browser):
    from openpyxl import load_workbook
    from playwright.sync_api import expect

    ui = statistics_browser
    page = ui['page']
    ui['login']()
    seed_timestamp_sources(ui)
    ui['open']()
    expect(page.locator('#statisticsStart')).to_have_value('')
    expect(page.locator('#statisticsContent')).to_contain_text('Asia/Tokyo')
    ui['select']()
    snapshot = ui['action']('statisticsQuery', '/statistics/query')
    values = {metric['key']: metric['value'] for metric in snapshot['metrics']}
    assert values == dict(zip(KEYS, ['2', '2', '1', '2', '0', '2', '0.3']))
    assert snapshot['period']['start_at_utc'].startswith('2025-12-31T15:00:00')
    assert snapshot['coverage_status'] == 'unknown'
    public = json.dumps(snapshot)
    assert CASE_ID not in public and PATIENT_ID not in public and 'PRIVATE_MEDICAL' not in public
    expect(page.locator('#statisticsSnapshot')).to_contain_text('観測値: 0')
    expect(page.locator('#statisticsSnapshot')).to_contain_text('department_all_dates')

    # Saving recaptures current sources, rather than trusting preview values.
    ui['database']("from datetime import date; from app.db import SessionLocal; from app.models import EmergencyCase\nwith SessionLocal() as db:\n db.add(EmergencyCase(source_case_key='synthetic-before-save',call_date=date(2026,1,4)));db.commit()")
    saved = ui['action']('statisticsSave', '/statistics/reports', 201)
    assert saved['snapshot']['metrics'][0]['value'] == '3'
    key = saved['report_id']
    page.locator('#statisticsReviewNote').fill('=SYNTHETIC_PRIVATE_REVIEW()')
    page.locator('#statisticsAcknowledge').check()
    confirmed = ui['action']('statisticsConfirm', f'/statistics/reports/{key}/confirm')
    assert confirmed['state'] == 'confirmed' and confirmed['snapshot'] == saved['snapshot']
    expect(page.locator('#statisticsContent')).to_contain_text('Human確認済み')
    expect(page.locator('#statisticsContent')).to_contain_text('網羅性: unknown')
    expect(page.locator('#statisticsContent')).to_contain_text('歴史的な網羅性や正式承認を意味しません')
    history = ui['action']('statisticsHistory', f'/statistics/reports/{key}/history?limit=20&offset=0')
    assert [item['action'] for item in history['items']] == ['saved', 'confirmed']
    page.screenshot(path=str(ui['artifacts'] / 'statistics-confirmed-unknown.png'), full_page=True)

    ui['database']("from datetime import date; from app.db import SessionLocal; from app.models import EmergencyCase\nwith SessionLocal() as db:\n db.add(EmergencyCase(source_case_key='synthetic-after-confirm',call_date=date(2026,1,5)));db.commit()")
    for format, button in [('csv', 'statisticsCSV'), ('xlsx', 'statisticsXLSX')]:
        started, request_start = time.perf_counter(), len(ui['request_events'])
        with page.expect_download() as download:
            page.locator('#' + button).click()
        file = download.value
        assert file.suggested_filename == f'statistics-{key}.{format}'
        destination = ui['tmp'] / file.suggested_filename
        file.save_as(destination)
        expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
        ui['measure'](button, started, request_start, 'Downloaded file saved and visible aria-busy=false')
        if format == 'csv':
            rows = list(csv.reader(StringIO(destination.read_text(encoding='utf-8-sig'))))
            flat = [cell for row in rows for cell in row]
            assert not any(cell.startswith(('=', '+', '-', '@')) for cell in flat)
        else:
            workbook = load_workbook(BytesIO(destination.read_bytes()), data_only=False)
            cells = [cell for sheet in workbook for row in sheet for cell in row]
            assert not any(cell.data_type == 'f' for cell in cells)
            flat = [str(cell.value) for cell in cells]
        exported = '\n'.join(flat)
        assert TITLE in exported and '3' in flat and '0.3' in flat
        assert CASE_ID not in exported and PATIENT_ID not in exported
        assert 'SYNTHETIC_PRIVATE_REVIEW' not in exported and 'SYNTHETIC_PRIVATE_MEDICAL' not in exported

    page.locator('#statisticsReplacementReason').fill('Sources changed after confirmation')
    replacement = ui['action']('statisticsReplace', f'/statistics/reports/{key}/replacements', 201)
    assert replacement['predecessor_id'] == key and replacement['state'] == 'saved'
    assert replacement['snapshot']['metrics'][0]['value'] == '4'
    old = page.request.get(ui['base'] + f'/statistics/reports/{key}').json()
    assert old['state'] == 'confirmed' and old['snapshot'] == saved['snapshot']


def test_aggregate_only_drilldown_denial_and_read_only_saved_access(statistics_browser):
    from playwright.sync_api import expect

    ui = statistics_browser
    page = ui['page']
    ui['login']('statistics-aggregate')
    ui['open']()
    ui['select'](['emergency.cases', 'emergency.patient_records'])
    saved = ui['action']('statisticsSave', '/statistics/reports', 201)
    key = saved['report_id']
    with page.expect_response(lambda response: '/drilldown?' in response.url) as response:
        page.locator('[data-statistics-drill="1"]').click()
    assert response.value.status == 403
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#statisticsDrilldown')).to_contain_text('別の権限')
    expect(page.locator('#statisticsSnapshot')).to_contain_text('観測値: 2')
    assert CASE_ID not in page.locator('#statisticsContent').inner_html()
    page.locator('#statisticsClose').click()
    # SharedSession shows login before logout's awaited HTTP call and reload.
    # Wait for that real reload before the next account's login navigates again.
    with page.expect_navigation(wait_until='load'):
        page.locator('#logoutBtn').click()
    expect(page.locator('#loginView')).to_be_visible()
    ui['login']('statistics-reader')
    ui['open']()
    ui['select'](['emergency.cases'])
    ui['action']('statisticsQuery', '/statistics/query')
    expect(page.locator('#statisticsSave')).to_have_count(0)
    ui['action']('statisticsSaved', '/statistics/reports?limit=20&offset=0')
    with page.expect_response(lambda response: response.url == ui['base'] + f'/statistics/reports/{key}'):
        page.locator(f'[data-statistics-report="{key}"]').click()
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#statisticsSnapshot')).to_contain_text('観測値: 2')
    for control in ['statisticsConfirm', 'statisticsReplace', 'statisticsCSV', 'statisticsXLSX']:
        expect(page.locator('#' + control)).to_have_count(0)


def test_authorized_drilldown_opens_real_source_and_close_owns_delayed_detail(statistics_browser):
    from playwright.sync_api import expect

    ui = statistics_browser
    page = ui['page']
    ui['login']()
    ui['open']()
    ui['select'](['emergency.cases'])
    ui['action']('statisticsSave', '/statistics/reports', 201)
    with page.expect_response(lambda response: '/drilldown?' in response.url) as response:
        page.locator('[data-statistics-drill="0"]').click()
    assert response.value.status == 200
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    pointers = response.value.json()['items']
    index = next(i for i, item in enumerate(pointers) if item['record_id'] == CASE_ID)
    with page.expect_response(lambda response: response.url == ui['base'] + '/emergency/cases/' + CASE_ID):
        page.locator(f'[data-statistics-source="{index}"]').click()
    expect(page.locator('#emergencyContent')).to_contain_text('SYNTHETIC-STATISTICS')
    expect(page.locator('#emergencyContent')).to_contain_text('SYNTHETIC_PRIVATE_MEDICAL')
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    page.locator('#emergencyClose').click()
    expect(page.locator('#emergencyModal')).to_be_hidden()
    held = []

    def hold(route):
        held.append(route)
        page.evaluate('window.statisticsDetailHeld = true')

    pattern = '**/emergency/cases/' + CASE_ID
    page.route(pattern, hold)
    try:
        page.locator(f'[data-statistics-source="{index}"]').click()
        page.wait_for_function('window.statisticsDetailHeld === true')
        page.locator('#emergencyClose').click()
        expect(page.locator('#emergencyModal')).to_be_hidden()
    finally:
        for route in held:
            route.continue_()
        page.unroute(pattern, hold)
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#emergencyModal')).to_be_hidden()
    expect(page.locator('#emergencyContent')).not_to_contain_text('SYNTHETIC_PRIVATE_MEDICAL')


@pytest.mark.parametrize('navigation', ['back', 'close', 'account_change'])
def test_held_real_query_cannot_repaint_after_navigation_or_account_change(statistics_browser, navigation):
    from playwright.sync_api import expect

    ui = statistics_browser
    page = ui['page']
    ui['login']()
    ui['open']()
    ui['select'](['emergency.cases'])
    page.evaluate('''() => {
      window.originalObservedQuery = statisticsQuery;
      window.statisticsQuerySettled = false;
      statisticsQuery = function(...args) {
        const result = Reflect.apply(window.originalObservedQuery, this, args);
        result.then(() => { window.statisticsQuerySettled = true; },
                    () => { window.statisticsQuerySettled = true; });
        return result;
      };
    }''')
    held = []

    def hold(route):
        held.append(route)
        page.evaluate('window.statisticsQueryHeld = true')

    page.route('**/statistics/query', hold)
    try:
        page.locator('#statisticsQuery').click()
        page.wait_for_function('window.statisticsQueryHeld === true')
        expect(page.locator('#statisticsQuery')).to_be_disabled()
        if navigation == 'back':
            page.locator('#statisticsBack').click()
            expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
        elif navigation == 'close':
            page.locator('#statisticsClose').click()
            expect(page.locator('#statisticsModal')).to_have_count(0)
        else:
            # A different user replaces the cookie while the first tab waits.
            response = ui['context'].request.post(ui['base'] + '/auth/login', data={
                'username': 'statistics-reader', 'password': 'synthetic-statistics-password'})
            assert response.status == 200
    finally:
        for route in held:
            route.continue_()
        page.unroute('**/statistics/query', hold)
    page.wait_for_function('window.statisticsQuerySettled === true')
    page.evaluate('statisticsQuery = window.originalObservedQuery; delete window.originalObservedQuery')
    if navigation == 'account_change':
        expect(page.locator('#loginView')).to_be_visible()
        expect(page.locator('#statisticsModal')).to_have_count(0)
    elif navigation == 'back':
        expect(page.locator('#statisticsSnapshot')).to_have_count(0)
        expect(page.locator('#statisticsStart')).to_have_value('2026-01-01')
    else:
        expect(page.locator('#statisticsModal')).to_have_count(0)


def test_actual_save_click_is_busy_during_authority_preflight(statistics_browser):
    from playwright.sync_api import expect

    ui = statistics_browser
    page = ui['page']
    ui['login']()
    ui['open']()
    ui['select'](['emergency.cases'])
    held, writes = [], []

    def observe_request(request):
        if request.url == ui['base'] + '/statistics/reports' and request.method == 'POST':
            writes.append(request)

    def hold(route):
        if held:
            route.fallback()
            return
        held.append(route)
        page.evaluate('window.statisticsPreflightHeld = true')

    page.on('request', observe_request)
    page.route('**/auth/context', hold)
    try:
        page.locator('#statisticsSave').click()
        page.wait_for_function('window.statisticsPreflightHeld === true')
        expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'true')
        expect(page.locator('#statisticsSave')).to_be_disabled()
        expect(page.locator('#statisticsStart')).to_be_disabled()
        expect(page.locator('#statisticsStatus')).to_contain_text('権限を確認中')
        expect(page.locator('#statisticsModal .modalHead #statisticsStatus')).to_be_in_viewport(ratio=1)
        page.screenshot(path=str(ui['artifacts'] / 'statistics-authority-preflight-busy.png'), full_page=True)
        page.locator('#statisticsSave').dispatch_event('click')
        assert not writes
    finally:
        for route in held:
            route.continue_()
        page.unroute('**/auth/context', hold)
    expect(page.locator('#statisticsContent')).to_contain_text('保存済み')
    expect(page.locator('#statisticsModal')).to_have_attribute('aria-busy', 'false')
    assert len(writes) == 1
    page.remove_listener('request', observe_request)
