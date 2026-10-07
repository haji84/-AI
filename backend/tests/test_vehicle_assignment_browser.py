"""Real shared-shell Vehicle → Organization journey using synthetic API data.

Chromium is intentionally CI-only. Held requests use continue_(), never a second
API request via route.fetch(); every held route is released in finally.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
    reason='real Chromium vehicle assignment runs only in authorized CI',
)
ROOT = Path(__file__).resolve().parents[2]
SEED = r'''
import json
from sqlalchemy import select
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,Role,Permission,RolePermission,UserRole
from app.personnel import OrganizationUnit
from app.operations_models import Vehicle
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 seed_rbac(db)
 for name,rights in [('assignment-ui',['fleet.read','fleet.update','fleet.create']),('assignment-reader',['fleet.read']),('assignment-auditor',['audit.read'])]:
  role=Role(code=name,name='Synthetic '+name);db.add(role);db.flush()
  for code in rights:
   permission=db.scalar(select(Permission).where(Permission.code==code));assert permission is not None
   db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
  user=User(username=name,password_hash=hash_password('synthetic-assignment-password'));db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
 a=OrganizationUnit(code='STA-A',name='Synthetic Alpha Station');b=OrganizationUnit(code='STA-B',name='Synthetic Beta Station')
 vehicle=Vehicle(code='ASSIGN-PUMP',name='Synthetic pump vehicle');other=Vehicle(code='OTHER-PUMP',name='Synthetic other vehicle')
 db.add_all([a,b,vehicle,other]);db.commit()
 print(json.dumps({'a':a.organization_id,'b':b.organization_id,'vehicle':vehicle.vehicle_id,'other':other.vehicle_id}))
'''


@pytest.fixture
def assignment_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    env = {**os.environ, 'PYTHONPATH': str(ROOT/'backend'),
           'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),
           'FIRE_AI_STORAGE_ROOT': str(tmp_path/'storage'), 'FIRE_AI_PRODUCTION_MODE': 'false'}
    env.pop('FIRE_AI_TENANT_ID', None)

    def database(script):
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout

    ids = json.loads(database(SEED).strip().splitlines()[-1])
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0))
        port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path/'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                               '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env,
                              stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base+'/health', timeout=.2).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:
            raise AssertionError('Synthetic assignment server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: (errors.append(dialog.message), dialog.dismiss()))

            def login(username='assignment-ui'):
                page.goto(base+'/ui/')
                page.locator('#loginUser').fill(username)
                page.locator('#loginPass').fill('synthetic-assignment-password')
                page.get_by_role('button', name='ログイン', exact=True).click()
                expect(page.locator('#operationsBtn')).to_be_visible()

            def vehicle():
                page.locator('#operationsBtn').click()
                page.locator('#operationsVehicles').click()
                page.locator('[data-operations-open="'+ids['vehicle']+'"]').click()
                expect(page.locator('#operationsAssignmentPanel')).to_be_visible()

            def edit(target='a', reason='Synthetic assignment reason', source='Synthetic order ref A-7'):
                page.locator('#operationsAssignmentEdit').click()
                expect(page.locator('#operationsAssignmentOrganization')).to_be_enabled()
                if target:
                    page.locator('#operationsAssignmentOrganization').select_option(ids[target])
                    expect(page.locator('#operationsAssignmentAfter')).to_contain_text('Synthetic Alpha Station' if target=='a' else 'Synthetic Beta Station')
                else:
                    page.locator('#operationsAssignmentAction').select_option('unassign')
                    expect(page.locator('#operationsAssignmentAfter')).to_contain_text('未配属')
                page.locator('#operationsAssignmentReason').fill(reason)
                page.locator('#operationsAssignmentSource').fill(source)
                page.locator('#operationsAssignmentAcknowledged').check()

            def save(status=201):
                with page.expect_response(lambda r: r.url.endswith('/assignments') and r.request.method=='POST') as response:
                    page.locator('#operationsAssignmentSave').click()
                assert response.value.status == status, response.value.text()
                if status == 201:
                    expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
                else:
                    expect(page.locator('#operationsAssignmentSave')).to_be_enabled()
                return response.value.json()

            login()
            yield page, base, ids, database, login, vehicle, edit, save
            assert not errors, errors
            browser.close()
    except BaseException:
        logs.flush()
        print((tmp_path/'server.log').read_text())
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        logs.close()


def test_pending_navigation_locks_old_vehicle_rows_before_authority_returns(assignment_browser):
    from playwright.sync_api import expect
    page, _, ids, _, _, vehicle, _, _ = assignment_browser
    vehicle()
    page.locator('#operationsVehicles').click()
    row = page.locator('[data-operations-open="'+ids['vehicle']+'"]')
    expect(row).to_be_enabled()
    held = []

    def hold_first_context(route):
        if not held:
            held.append(route)
        else:
            route.continue_()

    page.route('**/auth/context', hold_first_context)
    try:
        with page.expect_request(lambda request: request.url.endswith('/auth/context')):
            page.locator('#operationsVehicles').click()
        expect(row).to_be_disabled()
        assert len(held) == 1
    finally:
        for route in held:
            route.continue_()
        page.unroute('**/auth/context', hold_first_context)
    expect(row).to_be_enabled()
    row.click()
    expect(page.locator('#operationsAssignmentPanel')).to_be_visible()


def test_assign_transfer_unassign_retained_history_and_frozen_org_names(assignment_browser, tmp_path):
    from playwright.sync_api import expect
    page, base, ids, database, _, vehicle, edit, save = assignment_browser
    vehicle()
    expect(page.locator('#operationsAssignmentCurrent')).to_have_text('未記録（現在の配属は不明）')
    edit('a')
    first = save()
    assert first['vehicle_version'] == 2
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('Synthetic Alpha Station')
    # Current organization availability changes without rewriting its history.
    database("""
from app.db import SessionLocal
from app.personnel import OrganizationUnit
with SessionLocal() as db:
 row=db.get(OrganizationUnit,%r);row.name='Synthetic Renamed Alpha';row.active=False;row.version+=1;db.commit()
""" % ids['a'])
    page.locator('#operationsReload').click()
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('Synthetic Renamed Alpha')
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('無効')
    expect(page.locator('#operationsAssignmentPanel tbody')).to_contain_text('Synthetic Alpha Station')
    edit('b', 'Synthetic transfer reason', 'Synthetic transfer notice B-8')
    second = save()
    assert second['vehicle_version'] == 3
    assert second['change']['before_organization']['name'] == 'Synthetic Alpha Station'
    # A suspended vehicle retains its assignment and still supports explicit unassign.
    paused = page.request.patch(base+'/operations/vehicles/'+ids['vehicle'], data={'expected_version':3,'active':False})
    assert paused.status == 200, paused.text()
    page.locator('#operationsReload').click()
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('Synthetic Beta Station')
    edit(None, 'Synthetic release reason', 'Synthetic release order C-9')
    third = save()
    assert third['vehicle_version'] == 5
    expect(page.locator('#operationsAssignmentCurrent')).to_have_text('未配属（Human確認済み）')
    history = page.request.get(base+'/operations/vehicles/'+ids['vehicle']+'/assignments').json()
    assert history['total'] == 3
    assert [row['action'] for row in history['items']] == ['unassign','assign','assign']
    assert all(row['human_confirmation']['acknowledged'] for row in history['items'])
    assert all(row['changed_at'] and row['changed_by'] for row in history['items'])
    expect(page.locator('#operationsAssignmentPanel')).to_contain_text('Human記録の参照情報')
    artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path/'artifacts')))
    artifacts.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifacts/'vehicle-assignment-retained-history.png'), full_page=True)


def test_real_noop_conflict_required_fields_and_draft_reload(assignment_browser):
    from playwright.sync_api import expect
    page, base, ids, _, _, vehicle, edit, save = assignment_browser
    vehicle()
    edit('a')
    # HTML validation rejects missing Human reference before a request is sent.
    mutations = []
    page.on('request', lambda r: mutations.append(r) if r.method=='POST' and r.url.endswith('/assignments') else None)
    page.locator('#operationsAssignmentSource').fill('')
    page.locator('#operationsAssignmentSave').click()
    assert not mutations
    page.locator('#operationsAssignmentSource').fill('Synthetic order ref A-7')
    page.locator('#operationsAssignmentAcknowledged').check()
    patched = page.request.patch(base+'/operations/vehicles/'+ids['vehicle'], data={'expected_version':1,'name':'Synthetic current pump'})
    assert patched.status == 200
    save(409)
    expect(page.locator('#operationsAssignmentReason')).to_have_value('Synthetic assignment reason')
    expect(page.locator('#operationsAssignmentSource')).to_have_value('Synthetic order ref A-7')
    page.locator('#operationsAssignmentReload').click()
    expect(page.locator('#operationsContent h2')).to_contain_text('Synthetic current pump')
    expect(page.locator('#operationsAssignmentOrganization')).to_be_enabled()
    expect(page.locator('#operationsAssignmentAcknowledged')).not_to_be_checked()
    page.locator('#operationsAssignmentAcknowledged').check()
    saved = save()
    assert saved['vehicle_version'] == 3
    edit('a')
    save(409)
    expect(page.locator('#operationsAssignmentMessage')).to_contain_text('同一')
    assert page.request.get(base+'/operations/vehicles/'+ids['vehicle']+'/assignments').json()['total'] == 1


def test_real_repeated_submit_and_accepted_post_failed_refresh_retry(assignment_browser):
    from playwright.sync_api import expect
    page, base, ids, _, _, vehicle, edit, _ = assignment_browser
    vehicle()
    edit('a')
    held = []
    mutations = []
    refresh_failed = []

    def hold_post(route):
        if route.request.method=='POST' and not held:
            held.append(route)
            page.evaluate('window.assignmentRouteHeld=true')
        else:
            route.continue_()

    def fail_refresh(route):
        if not refresh_failed:
            refresh_failed.append(True)
            route.abort('failed')
        else:
            route.continue_()

    path = '**/operations/vehicles/'+ids['vehicle']+'/assignments'
    page.evaluate('window.assignmentRouteHeld=false')
    page.route(path, hold_post)
    page.on('request', lambda r: mutations.append(r) if r.method=='POST' and r.url.endswith('/assignments') else None)
    try:
        page.evaluate("""() => {
          window.oldAssignmentForm=document.querySelector('#operationsAssignmentForm');
          oldAssignmentForm.requestSubmit();oldAssignmentForm.requestSubmit();
        }""")
        page.wait_for_function('window.assignmentRouteHeld === true')
        assert held, 'Real assignment POST was not dispatched'
        expect(page.locator('#operationsAssignmentSave')).to_be_disabled()
        assert len(mutations) == 1
        page.route(path+'?*', fail_refresh)
        held.pop().continue_()
        expect(page.locator('#operationsContent')).to_contain_text('保存済み')
        expect(page.locator('#operationsAssignmentRetry')).to_be_visible()
        expect(page.locator('#operationsAssignmentForm')).to_have_count(0)
        # Even a cached detached submit handler cannot issue another POST.
        page.evaluate('oldAssignmentForm.onsubmit({preventDefault(){}})')
        page.locator('#operationsAssignmentRetry').click()
        expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
        assert len(mutations) == 1
        assert page.request.get(base+'/operations/vehicles/'+ids['vehicle']+'/assignments').json()['total'] == 1
    finally:
        for route in held:
            route.continue_()
        page.unroute(path, hold_post)
        page.unroute(path+'?*', fail_refresh)


@pytest.mark.parametrize('pending_kind,dismiss', [('lookup','back'),('lookup','close'),('detail','vehicles')])
def test_delayed_real_lookup_or_detail_yields_to_newer_navigation(assignment_browser, pending_kind, dismiss):
    from playwright.sync_api import expect
    page, _, ids, _, _, vehicle, _, _ = assignment_browser
    vehicle()
    held = []
    path = '**/operations/fleet-organizations?*' if pending_kind=='lookup' else '**/operations/vehicles/'+ids['vehicle']+'/assignments?*'

    def hold(route):
        if not held:
            held.append(route)
            page.evaluate('window.assignmentRouteHeld=true')
        else:
            route.continue_()

    function = 'operationsAssignmentEditor' if pending_kind=='lookup' else 'operationsVehicleDetail'
    page.evaluate('''name => {
      window.originalAssignmentPending=window[name];window.assignmentPendingFinished=false;window.assignmentRouteHeld=false;
      window[name]=function(...args){
        const result=originalAssignmentPending.apply(this,args);
        result.then(()=>window.assignmentPendingFinished=true,()=>window.assignmentPendingFinished=true);
        return result;
      };
    }''', function)
    page.route(path, hold)
    try:
        page.locator('#operationsAssignmentEdit' if pending_kind=='lookup' else '#operationsReload').click()
        page.wait_for_function('window.assignmentRouteHeld === true')
        assert held, 'The real lookup/detail request was not dispatched'
        control = {'back':'operationsAssignmentBack','close':'operationsClose','vehicles':'operationsVehicles'}[dismiss]
        page.locator('#'+control).click()
        if dismiss=='back':
            expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
        elif dismiss=='close':
            expect(page.locator('#operationsModal')).to_be_hidden()
        else:
            expect(page.locator('#operationsSearch')).to_be_visible()
        before = page.locator('#operationsContent').inner_html()
        with page.expect_response(lambda r: ('/fleet-organizations?' if pending_kind=='lookup' else '/assignments?') in r.url):
            held.pop().continue_()
        # Wait for the trailing SharedSession observation and body read.
        page.wait_for_function('window.assignmentPendingFinished === true')
        expect(page.locator('#operationsAssignmentForm')).to_have_count(0)
        assert page.locator('#operationsContent').inner_html() == before
    finally:
        for route in held:
            route.continue_()
        page.unroute(path, hold)
        page.evaluate('name => {window[name]=originalAssignmentPending;delete window.originalAssignmentPending}', function)


@pytest.mark.parametrize('authority_change', ['logout','revoke_update'])
def test_reader_sees_history_and_revoked_session_erases_draft(assignment_browser, authority_change):
    from playwright.sync_api import expect
    page, base, ids, database, login, vehicle, edit, save = assignment_browser
    vehicle()
    edit('a')
    save()
    edit('b', 'Synthetic protected transfer draft', 'Synthetic protected reference')
    if authority_change == 'logout':
        assert page.request.post(base+'/auth/logout').status == 200
    else:
        database('''
from sqlalchemy import select,delete
from app.db import SessionLocal
from app.models import Role,Permission,RolePermission
with SessionLocal() as db:
 role=db.scalar(select(Role).where(Role.code=='assignment-ui'))
 permission=db.scalar(select(Permission).where(Permission.code=='fleet.update'))
 db.execute(delete(RolePermission).where(RolePermission.role_id==role.role_id,RolePermission.permission_id==permission.permission_id));db.commit()
''')
    # Directly invoke the cached action because session clearing may already have
    # correctly removed its control. SharedSession remains the real API wrapper.
    page.evaluate("operationsState.assignment && operationsAssignmentLookup(operationsState.assignment,0,'')")
    expect(page.locator('#operationsModal')).to_have_count(0)
    assert page.evaluate('operationsState.assignment === null && operationsState.vehicle === null')
    login('assignment-reader')
    vehicle()
    expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
    expect(page.locator('#operationsAssignmentEdit')).to_have_count(0)
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('Synthetic Alpha Station')
    expect(page.locator('#operationsAssignmentPanel tbody')).to_contain_text('Synthetic order ref A-7')
    denied = page.request.post(base+'/operations/vehicles/'+ids['vehicle']+'/assignments', data={
        'expected_version':2,'action':'unassign','reason':'Synthetic reason',
        'source_evidence':'Synthetic ref','human_acknowledged':True})
    assert denied.status == 403
    assert page.request.get(base+'/operations/vehicles/'+ids['vehicle']+'/assignments').json()['total'] == 1


@pytest.mark.parametrize('pending_kind', ['detail','list'])
def test_close_intent_during_real_authority_preflight_blocks_late_detail(assignment_browser, pending_kind):
    from playwright.sync_api import expect
    page, _, ids, _, _, vehicle, _, _ = assignment_browser
    vehicle()
    held_detail, held_authority = [], []
    detail_path = '**/operations/vehicles/'+ids['vehicle']+'/assignments?*' if pending_kind=='detail' else '**/operations/vehicles?*'
    function = 'operationsVehicleDetail' if pending_kind=='detail' else 'operationsList'
    authority_path = '**/auth/context'
    should_hold = {'authority':False}

    def hold_detail(route):
        held_detail.append(route)
        page.evaluate('window.assignmentDetailRouteHeld=true')

    def hold_authority(route):
        if should_hold['authority'] and not held_authority:
            should_hold['authority'] = False
            held_authority.append(route)
            page.evaluate('window.assignmentAuthorityRouteHeld=true')
        else:
            route.continue_()

    page.evaluate('''name => {
      window.originalAssignmentDetail=window[name];window.assignmentDetailFinished=false;
      window.assignmentDetailRouteHeld=false;window.assignmentAuthorityRouteHeld=false;
      window[name]=function(...args){
        const result=originalAssignmentDetail.apply(this,args);
        result.then(()=>window.assignmentDetailFinished=true,()=>window.assignmentDetailFinished=true);
        return result;
      };
    }''', function)
    page.route(detail_path, hold_detail)
    page.route(authority_path, hold_authority)
    try:
        page.locator('#operationsReload' if pending_kind=='detail' else '#operationsVehicles').click()
        page.wait_for_function('window.assignmentDetailRouteHeld === true')
        assert held_detail
        should_hold['authority'] = True
        page.locator('#operationsClose').click()
        page.wait_for_function('window.assignmentAuthorityRouteHeld === true')
        assert held_authority
        held_detail.pop().continue_()
        page.wait_for_function('window.assignmentDetailFinished === true')
        expect(page.locator('#operationsAssignmentEdit')).to_have_count(0)
        expect(page.locator('#operationsSearch')).to_have_count(0)
        held_authority.pop().continue_()
        expect(page.locator('#operationsModal')).to_be_hidden()
    finally:
        for route in held_detail + held_authority:
            route.continue_()
        page.unroute(detail_path, hold_detail)
        page.unroute(authority_path, hold_authority)
        page.evaluate('name => {window[name]=originalAssignmentDetail;delete window.originalAssignmentDetail}', function)


def test_older_real_alerts_cannot_replace_new_assignment_draft(assignment_browser):
    from playwright.sync_api import expect
    page, _, ids, _, _, vehicle, edit, _ = assignment_browser
    held = []

    def hold(route):
        held.append(route)
        page.evaluate('window.assignmentOldAlertHeld=true')

    page.evaluate('''() => {
      window.originalAssignmentAlerts=operationsAlerts;
      window.assignmentOldAlertHeld=false;window.assignmentOldAlertFinished=false;
      window.operationsAlerts=function(...args){
        const result=originalAssignmentAlerts.apply(this,args);
        result.then(()=>window.assignmentOldAlertFinished=true,()=>window.assignmentOldAlertFinished=true);
        return result;
      };
    }''')
    # openOperations binds this function by reference when vehicle() opens it.
    # Install the observer first so the real Alerts button invokes that observer.
    vehicle()
    path = '**/operations/alerts'
    page.route(path, hold)
    try:
        page.locator('#operationsAlerts').click()
        page.wait_for_function('window.assignmentOldAlertHeld === true')
        page.locator('#operationsVehicles').click()
        page.locator('[data-operations-open="'+ids['vehicle']+'"]').click()
        expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
        edit('a', 'Synthetic retained draft reason', 'Synthetic retained draft reference')
        held.pop().continue_()
        page.wait_for_function('window.assignmentOldAlertFinished === true')
        expect(page.locator('#operationsAssignmentForm')).to_be_visible()
        expect(page.locator('#operationsAssignmentReason')).to_have_value('Synthetic retained draft reason')
        expect(page.locator('#operationsAssignmentSource')).to_have_value('Synthetic retained draft reference')
    finally:
        for route in held:
            route.continue_()
        page.unroute(path, hold)
        page.evaluate('operationsAlerts=originalAssignmentAlerts;delete window.originalAssignmentAlerts')


def test_human_can_register_an_additional_vehicle_then_assign_it(assignment_browser, tmp_path):
    from playwright.sync_api import expect
    page, base, ids, _, login, _, edit, save = assignment_browser
    code = 'SYN-ADDED-'+uuid4().hex[:12]
    name = 'Synthetic additional rescue van'
    reason = 'Synthetic first placement of an additional vehicle'
    reference = 'Synthetic additional vehicle placement notice'

    def search_added_vehicle():
        page.locator('#operationsQ').fill(code)
        with page.expect_response(lambda response: response.request.method=='GET'
                and urlsplit(response.url).path=='/operations/vehicles'
                and parse_qs(urlsplit(response.url).query).get('q')==[code]) as filtered:
            page.locator('#operationsSearch').click()
        assert filtered.value.status == 200, filtered.value.text()
        target = page.locator('[data-operations-open="'+vehicle_id+'"]')
        expect(target).to_be_visible()
        return target

    permissions = page.request.get(base+'/auth/permissions')
    assert permissions.status == 200
    assert {'fleet.read','fleet.create','fleet.update'} <= set(permissions.json()['permissions'])
    assert 'audit.read' not in permissions.json()['permissions']
    actor = page.request.get(base+'/auth/me').json()['user_id']
    before = page.request.get(base+'/operations/vehicles', params={'q':code})
    assert before.status == 200 and before.json() == []

    # The new vehicle must come from the real Human form, never a seed or direct
    # POST. Its server-returned identity drives every later lookup and placement.
    page.locator('#operationsBtn').click()
    # This fleet-only operator opens directly into the initial vehicle list.
    expect(page.locator('#operationsNew')).to_be_visible()
    page.locator('#operationsNew').click()
    expect(page.locator('#operationsContent h2')).to_have_text('車両登録')
    page.locator('#operationsField_code').fill(code)
    page.locator('#operationsField_name').fill(name)
    page.locator('#operationsField_registration').fill('SYN-ADDED-REG')
    page.locator('#operationsField_odometer').fill('12.5')
    page.locator('#operationsField_notes').fill('Synthetic Human vehicle registration')
    with page.expect_response(lambda response: response.url==base+'/operations/vehicles' and response.request.method=='POST') as created_response:
        page.locator('#operationsForm button[type="submit"]').click()
    assert created_response.value.status == 201, created_response.value.text()
    created = created_response.value.json()
    vehicle_id = created['vehicle_id']
    assert created['code'] == code and created['name'] == name
    assert created['registration'] == 'SYN-ADDED-REG' and float(created['odometer']) == 12.5
    assert created['version'] == 1
    expect(page.locator('#operationsAssignmentPanel')).to_be_visible()
    expect(page.locator('#operationsContent h2')).to_have_text(code+' / '+name)
    expect(page.locator('#operationsAssignmentCurrent')).to_have_text('未記録（現在の配属は不明）')

    edit('a', reason, reference)
    changed = save()
    assert changed['vehicle_version'] == 2
    assert changed['current']['organization']['organization_id'] == ids['a']
    assert changed['change']['changed_by'] == actor
    history_response = page.request.get(base+'/operations/vehicles/'+vehicle_id+'/assignments')
    assert history_response.status == 200
    history = history_response.json()
    assert history['vehicle_id'] == vehicle_id and history['total'] == 1
    assert history['items'][0]['reason'] == reason and history['items'][0]['source_evidence'] == reference

    # Search and reopen the newly registered record within the existing modal.
    page.locator('#operationsVehicles').click()
    search_added_vehicle().click()
    expect(page.locator('#operationsContent h2')).to_have_text(code+' / '+name)
    expect(page.locator('#operationsAssignmentCurrent')).to_contain_text('Synthetic Alpha Station')
    expect(page.locator('#operationsAssignmentPanel tbody')).to_contain_text(reason)
    expect(page.locator('#operationsAssignmentPanel tbody')).to_contain_text(reference)
    artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path/'artifacts')))
    artifacts.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifacts/'vehicle-created-and-assigned-through-ui.png'), full_page=True)

    # Audit access is independent of the fleet operator's session and rights.
    audit_context = page.context.browser.new_context()
    try:
        logged_in = audit_context.request.post(base+'/auth/login', data={
            'username':'assignment-auditor','password':'synthetic-assignment-password'})
        assert logged_in.status == 200, logged_in.text()
        audited = audit_context.request.get(base+'/administration/audit', params={
            'action':'fleet.vehicle.create','entity_type':'operation_vehicles'})
        assert audited.status == 200, audited.text()
        creation = [row for row in audited.json() if row['entity_id']==vehicle_id]
        assert len(creation) == 1
        assert creation[0]['user_id'] == actor and creation[0]['success'] is True
        assert creation[0]['after_data']['version'] == 1 and creation[0]['occurred_at']
    finally:
        audit_context.close()

    # Existing fleet.read access includes the added record, but does not grant
    # the New control or the underlying create endpoint.
    assert page.request.post(base+'/auth/logout').status == 200
    login('assignment-reader')
    page.locator('#operationsBtn').click()
    expect(page.locator('#operationsSearch')).to_be_visible()
    expect(page.locator('#operationsNew')).to_have_count(0)
    search_added_vehicle().click()
    expect(page.locator('#operationsAssignmentPanel tbody')).to_contain_text(reference)
    expect(page.locator('#operationsAssignmentEdit')).to_have_count(0)
    denied_code = 'DENIED-'+uuid4().hex[:12]
    denied = page.request.post(base+'/operations/vehicles', data={'code':denied_code,'name':'Synthetic denied addition'})
    assert denied.status == 403
    denied_lookup = page.request.get(base+'/operations/vehicles', params={'q':denied_code})
    assert denied_lookup.status == 200 and denied_lookup.json() == []
