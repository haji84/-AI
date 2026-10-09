"""Real shared-shell work-queue journey. Synthetic data; Chromium runs in CI."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
    reason='actual Chromium work queue executes in the authorized CI job',
)

ASSET_ID = '11111111-1111-4111-8111-111111111111'
INQUIRY_ID = '22222222-2222-4222-8222-222222222222'
FACILITY_ID = '33333333-3333-4333-8333-333333333333'
VEHICLE_ID = '44444444-4444-4444-8444-444444444444'
RESTRICTED_ID = '55555555-5555-4555-8555-555555555555'

SEED = r'''
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Facility,User,Role,Permission,RolePermission,UserRole
from app.assets_models import OperationalAsset
from app.operations_models import Vehicle
from app.inquiries_models import Inquiry
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
today=datetime.now(ZoneInfo('Asia/Tokyo')).date()
with SessionLocal() as db:
 seed_rbac(db)
 role=Role(code='synthetic_queue_reader',name='Synthetic limited queue reader');db.add(role);db.flush()
 rights=['facility.read','inspection.read','submission.read','equipment.read','drawing.read','asset.read','inquiry.read']
 for code in rights:
  permission=db.scalar(select(Permission).where(Permission.code==code));assert permission is not None
  db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
 user=User(username='queue-ui',password_hash=hash_password('synthetic-queue-password'));other=User(username='queue-other',password_hash=hash_password('synthetic-other-password'))
 db.add_all([user,other]);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
 db.add(Facility(building_id='33333333-3333-4333-8333-333333333333',name='Synthetic queue facility',status='active'))
 db.add(OperationalAsset(asset_id='11111111-1111-4111-8111-111111111111',code='QUEUE-READ',name='Synthetic queue pressure equipment',category='durable',unit='piece',next_pressure_test_on=today))
 db.add(Vehicle(vehicle_id='44444444-4444-4444-8444-444444444444',code='FORBIDDEN-VEHICLE',name='Synthetic forbidden vehicle',next_inspection_on=today))
 db.add(Inquiry(inquiry_id='22222222-2222-4222-8222-222222222222',year=today.year,question='Synthetic own queue question',created_by=user.user_id))
 db.add(Inquiry(year=today.year,question='Synthetic other creator question',created_by=other.user_id))
 db.add(Inquiry(inquiry_id='55555555-5555-4555-8555-555555555555',year=today.year,question='Synthetic restricted fleet question',created_by=user.user_id,provenance={'security_sources':[{'source_type':'vehicle','source_id':'44444444-4444-4444-8444-444444444444','required_permissions':['fleet.read'],'documents':[]}]}))
 db.commit()
'''


def test_limited_user_source_navigation_refresh_and_authority_changes(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ, 'PYTHONPATH': str(root / 'backend'),
        'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
        'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'),
        'FIRE_AI_PRODUCTION_MODE': 'false',
    }
    env.pop('FIRE_AI_TENANT_ID', None)

    def database(script):
        subprocess.run([sys.executable, '-c', script], cwd=root, env=env, check=True, capture_output=True)

    database(SEED)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0))
        port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path / 'server.log').open('w')
    server = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=root, env=env, stdout=logs, stderr=logs,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/health', timeout=.2).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError((tmp_path / 'server.log').read_text())
                time.sleep(.1)
        else:
            raise AssertionError('Synthetic work-queue server did not start')

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: (errors.append(dialog.message), dialog.dismiss()))
            panel = page.locator('#workQueuePanel')
            artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
            artifacts.mkdir(parents=True, exist_ok=True)
            timings = {}

            def loaded(action):
                with page.expect_response(lambda r: r.url.startswith(base + '/work-queue?')) as result:
                    action()
                assert result.value.status == 200, result.value.text()
                expect(panel).to_have_attribute('aria-busy', 'false')
                return result.value.json()

            def login(record_timing=False):
                page.goto(base + '/ui/')
                page.locator('#loginUser').fill('queue-ui')
                page.locator('#loginPass').fill('synthetic-queue-password')
                started = time.perf_counter()
                result = loaded(lambda: page.get_by_role('button', name='ログイン', exact=True).click())
                if record_timing:
                    timings['login_to_home_ready_seconds'] = round(time.perf_counter() - started, 3)
                return result

            first = login(record_timing=True)
            assert first['total'] == 2
            assert first['counts'] == {'operational_assets': 1, 'inquiries': 1}
            assert {item['navigation']['id'] for item in first['items']} == {ASSET_ID, INQUIRY_ID}
            expect(panel).to_contain_text('Synthetic queue pressure equipment')
            expect(panel).to_contain_text('Synthetic own queue question')
            expect(page.locator('#noSelection')).to_be_hidden()
            expect(panel).not_to_contain_text('Synthetic forbidden vehicle')
            expect(panel).not_to_contain_text('Synthetic restricted fleet question')
            expect(panel).not_to_contain_text('Synthetic other creator question')
            assert VEHICLE_ID not in json.dumps(first) and RESTRICTED_ID not in json.dumps(first)
            expect(page.locator('#operationsBtn')).to_be_hidden()
            expect(page.locator('#assetsBtn')).to_be_visible()
            page.screenshot(path=str(artifacts / 'work-queue-authorized-sources.png'), full_page=True)

            related = loaded(lambda: page.locator('#workQueueScope').select_option('related'))
            assert related['total'] == 1 and related['items'][0]['source_id'] == INQUIRY_ID
            expect(panel).to_contain_text('自分が作成')
            loaded(lambda: page.locator('#workQueueScope').select_option('all'))

            # Queue source pointers enter the real existing module, not a copied detail.
            asset_card = panel.locator('article').filter(has_text='Synthetic queue pressure equipment')
            source_started = time.perf_counter()
            with page.expect_response(lambda r: r.url == base + '/assets/registry/' + ASSET_ID) as detail:
                asset_card.get_by_role('button', name='元記録を開く').click()
            assert detail.value.status == 200
            expect(page.locator('#assetsContent h2')).to_contain_text('QUEUE-READ')
            expect(page.locator('#assetsEdit')).to_have_count(0)
            expect(panel).to_have_attribute('aria-busy', 'false')
            timings['first_source_open_to_detail_ready_seconds'] = round(time.perf_counter() - source_started, 3)
            (artifacts / 'work-queue-timings.json').write_text(json.dumps({'synthetic': True, **timings}, indent=2) + '\n')
            page.locator('#assetsClose').click()
            expect(page.locator('#assetsModal')).to_be_hidden()
            expect(panel).to_be_visible()

            # Pause the real trailing authority request after the asset list has
            # opened. Close/reopen must own the view when that request completes.
            pending_source = []
            stale_detail_requests = []

            def observe_detail(request):
                if request.url == base + '/assets/registry/' + ASSET_ID:
                    stale_detail_requests.append(request.url)

            def hold_source_authority(route):
                if pending_source or not page.evaluate("workQueueState.opening && !!document.querySelector('#assetsSearch')"):
                    route.fallback()
                else:
                    pending_source.append((route, route.fetch()))

            page.evaluate('''() => {
              window.originalQueueSource=openWorkQueueSource;
              window.openWorkQueueSource=(...args)=>{window.queueSourceFinished=false;return originalQueueSource(...args).finally(()=>window.queueSourceFinished=true)};
              window.originalAssetsOpen=openAssets;
              window.openAssets=(...args)=>{window.assetsOpenFinished=false;return originalAssetsOpen(...args).finally(()=>window.assetsOpenFinished=true)};
            }''')
            page.on('request', observe_detail)
            page.route('**/auth/context', hold_source_authority)
            asset_card.get_by_role('button', name='元記録を開く').click()
            for _ in range(100):
                if pending_source:
                    break
                page.wait_for_timeout(10)
            assert pending_source, 'Source navigation did not reach the trailing authority check'
            assert page.evaluate('window.assetsOpenFinished') is True
            page.locator('#assetsClose').click()
            expect(page.locator('#assetsModal')).to_be_hidden()
            page.evaluate('window.assetsOpenFinished=false')
            page.locator('#assetsBtn').click()
            page.wait_for_function('window.assetsOpenFinished===true')
            expect(page.locator('#assetsSearch')).to_be_visible()
            pending_source[0][0].fulfill(response=pending_source[0][1])
            page.wait_for_function('window.queueSourceFinished===true')
            assert not stale_detail_requests, 'Old queue selection fetched detail after Close/reopen'
            expect(page.locator('#assetsSearch')).to_be_visible()
            page.unroute('**/auth/context', hold_source_authority)
            page.remove_listener('request', observe_detail)
            page.evaluate('openWorkQueueSource=originalQueueSource;openAssets=originalAssetsOpen;delete window.originalQueueSource;delete window.originalAssetsOpen')
            page.locator('#assetsClose').click()
            expect(page.locator('#assetsModal')).to_be_hidden()

            # A detail already dispatched must also yield to a newer real list.
            delayed_detail = []

            def hold_detail(route):
                if delayed_detail:
                    route.fallback()
                else:
                    delayed_detail.append((route, route.fetch()))

            page.evaluate('''() => {
              window.originalQueueSource=openWorkQueueSource;
              window.openWorkQueueSource=(...args)=>{window.queueSourceFinished=false;return originalQueueSource(...args).finally(()=>window.queueSourceFinished=true)};
              window.originalAssetsList=assetsList;
              window.assetsList=(...args)=>{window.assetsListFinished=false;return originalAssetsList(...args).finally(()=>window.assetsListFinished=true)};
            }''')
            detail_path = '**/assets/registry/' + ASSET_ID
            page.route(detail_path, hold_detail)
            asset_card.get_by_role('button', name='元記録を開く').click()
            for _ in range(100):
                if delayed_detail:
                    break
                page.wait_for_timeout(10)
            assert delayed_detail, 'Actual queue source detail request did not start'
            page.evaluate('window.assetsListFinished=false')
            page.locator('#assetsRegistry').click()
            page.wait_for_function('window.assetsListFinished===true')
            expect(page.locator('#assetsSearch')).to_be_visible()
            current_list = page.locator('#assetsContent').inner_html()
            delayed_detail[0][0].fulfill(response=delayed_detail[0][1])
            page.wait_for_function('window.queueSourceFinished===true')
            expect(page.locator('#assetsSearch')).to_be_visible()
            assert page.locator('#assetsContent').inner_html() == current_list
            page.unroute(detail_path, hold_detail)
            page.evaluate('openWorkQueueSource=originalQueueSource;assetsList=originalAssetsList;delete window.originalQueueSource;delete window.originalAssetsList')
            page.locator('#assetsClose').click()
            expect(page.locator('#assetsModal')).to_be_hidden()

            own_card = panel.locator('article').filter(has_text='Synthetic own queue question')
            own_card.get_by_role('button', name='元記録を開く').click()
            expect(page.locator('#inquiryContent h2')).to_contain_text('Synthetic own queue question')
            expect(panel).to_have_attribute('aria-busy', 'false')
            page.locator('#inquiryClose').click()
            expect(page.locator('#inquiryModal')).to_be_hidden()

            # A source closure disappears and a newer original version/title is shown.
            database('''
from app.db import SessionLocal
from app.assets_models import OperationalAsset
from app.inquiries_models import Inquiry
with SessionLocal() as db:
 asset=db.get(OperationalAsset,'11111111-1111-4111-8111-111111111111');asset.next_pressure_test_on=None;asset.version+=1
 inquiry=db.get(Inquiry,'22222222-2222-4222-8222-222222222222');inquiry.question='Synthetic updated queue question';inquiry.version+=1
 db.commit()
''')
            refreshed = loaded(lambda: page.locator('#workQueueRefresh').click())
            assert refreshed['total'] == 1 and refreshed['items'][0]['source_version'] == 2
            expect(panel).to_contain_text('Synthetic updated queue question')
            expect(panel).not_to_contain_text('Synthetic queue pressure equipment')

            # Keep one persistent route and explicitly fall back after its first use.
            # Chromium 153 can drop a pending response when times=1 expires.
            failure_sent = False

            def fail_once(route):
                nonlocal failure_sent
                if failure_sent:
                    route.fallback()
                else:
                    failure_sent = True
                    route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic queue unavailable"}')

            page.route('**/work-queue?*', fail_once)
            with page.expect_response(lambda r: r.url.startswith(base + '/work-queue?')) as failed:
                page.locator('#workQueueRefresh').click()
            assert failed.value.status == 503
            expect(panel.get_by_role('alert')).to_contain_text('取得できません')
            expect(panel).not_to_contain_text('対象の業務はありません')
            assert loaded(lambda: page.locator('#workQueueRefresh').click())['total'] == 1
            page.unroute('**/work-queue?*', fail_once)

            # A late facility response must not replace a newer Home navigation.
            pending_facility = []

            def hold_facility(route):
                if pending_facility:
                    route.fallback()
                else:
                    pending_facility.append((route, route.fetch()))

            facility_path = '**/facilities/' + FACILITY_ID + '/detail'
            page.route(facility_path, hold_facility)
            page.evaluate('''() => {
              const original=selectFacility;
              window.selectFacility=(...args)=>{window.facilityFinished=false;return original(...args).finally(()=>window.facilityFinished=true)};
            }''')
            page.locator('.facilityItem').filter(has_text='Synthetic queue facility').click()
            for _ in range(100):
                if pending_facility:
                    break
                page.wait_for_timeout(10)
            assert pending_facility, 'Facility navigation did not reach the real detail request'
            expect(panel).to_be_hidden()
            loaded(lambda: page.locator('#workQueueBtn').click())
            pending_facility[0][0].fulfill(response=pending_facility[0][1])
            page.wait_for_function('window.facilityFinished===true')
            expect(panel).to_be_visible()
            expect(page.locator('#detailView')).to_be_hidden()
            page.unroute(facility_path, hold_facility)

            def delayed_queue():
                pending = []

                def hold(route):
                    if pending:
                        route.fallback()
                    else:
                        pending.append((route, route.fetch()))

                page.route('**/work-queue?*', hold)
                page.evaluate('window.delayedQueueFinished=false;void loadWorkQueue().finally(()=>window.delayedQueueFinished=true)')
                for _ in range(100):
                    if pending:
                        break
                    page.wait_for_timeout(10)
                assert pending, 'Queue refresh did not reach the real HTTP request'
                return pending[0], hold

            # A same-user new session must discard the old session's successful data.
            (route, response), hold = delayed_queue()
            before = page.request.get(base + '/auth/context').json()
            replacement = page.request.post(base + '/auth/login', data={'username': 'queue-ui', 'password': 'synthetic-queue-password'})
            assert replacement.status == 200
            after = page.request.get(base + '/auth/context').json()
            assert before['user_id'] == after['user_id'] and before['session_id'] != after['session_id']
            route.fulfill(response=response)
            page.wait_for_function('window.delayedQueueFinished===true')
            expect(page.locator('#loginView')).to_be_visible()
            expect(panel).to_be_empty()
            expect(panel).to_be_hidden()
            assert page.evaluate('workQueueState.data') is None
            page.unroute('**/work-queue?*', hold)

            login()
            (route, response), hold = delayed_queue()
            database('''
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Permission,Role,RolePermission
with SessionLocal() as db:
 role=db.scalar(select(Role).where(Role.code=='synthetic_queue_reader'))
 permission=db.scalar(select(Permission).where(Permission.code=='asset.read'))
 grant=db.get(RolePermission,(role.role_id,permission.permission_id));db.delete(grant);db.commit()
''')
            route.fulfill(response=response)
            page.wait_for_function('window.delayedQueueFinished===true')
            expect(page.locator('#loginView')).to_be_visible()
            expect(panel).to_be_empty()
            expect(page.locator('#workQueueBtn')).to_be_hidden()
            assert page.evaluate('workQueueState.data') is None
            page.unroute('**/work-queue?*', hold)
            assert not errors, errors

            page.screenshot(path=str(artifacts / 'work-queue-authority-cleared.png'), full_page=True)

            # A finance card is a pointer to the existing Human-gated screen,
            # never a copied amount/reason or an approval in the Home panel.
            database('''
from decimal import Decimal
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User,Role,Permission,RolePermission,Document
from app.finance_models import FinanceYear,BudgetAccount,FinanceProposal
with SessionLocal() as db:
 role=db.scalar(select(Role).where(Role.code=='synthetic_queue_reader'))
 user=db.scalar(select(User).where(User.username=='queue-ui'))
 for code in ('finance.read','finance.review','document.read'):
  permission=db.scalar(select(Permission).where(Permission.code==code))
  db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
 year=FinanceYear(fiscal_year=2026,currency='JPY',decimal_places=0,reason='Synthetic fiscal policy');db.add(year);db.flush()
 account=BudgetAccount(year_id=year.year_id,code='QUEUE',name='Synthetic private account',level=1);db.add(account)
 original=Document(original_filename='Synthetic private finance evidence.txt',storage_path='unused-synthetic',sha256='a'*64,mime_type='text/plain',size_bytes=1,created_by=user.user_id);db.add(original);db.flush()
 db.add(FinanceProposal(proposal_id='66666666-6666-4666-8666-666666666666',kind='initial',account_id=account.account_id,document_id=original.document_id,amount=Decimal('12000.00'),currency='JPY',reason='Synthetic private finance reason',created_by=user.user_id,idempotency_key='synthetic-queue-finance'))
 db.commit()
''')
            finance_id = '66666666-6666-4666-8666-666666666666'
            financial = login()
            assert financial['counts']['budget'] == 1
            expect(panel).not_to_contain_text('12000')
            expect(panel).not_to_contain_text('Synthetic private finance reason')
            finance_card = panel.locator('article').filter(has_text='財務根拠確認')
            with page.expect_response(lambda r: r.url == base + '/finance/proposals/' + finance_id) as detail:
                finance_card.get_by_role('button', name='元記録を開く').click()
            assert detail.value.status == 200
            expect(page.locator('#financeContent')).to_contain_text('Synthetic private finance reason')
            expect(page.locator('#financeReview')).to_be_visible()
            expect(page.locator('#financeApprove')).to_have_count(0)
            expect(page.locator('#financeProposalEdit')).to_have_count(0)
            expect(panel).to_have_attribute('aria-busy', 'false')
            page.locator('#financeClose').click()
            database('''
from app.db import SessionLocal
from app.finance_models import FinanceProposal
with SessionLocal() as db:
 row=db.get(FinanceProposal,'66666666-6666-4666-8666-666666666666');row.status='cancelled';row.version+=1;db.commit()
''')
            refreshed = loaded(lambda: page.locator('#workQueueRefresh').click())
            assert 'budget' not in refreshed['counts']
            assert finance_id not in json.dumps(refreshed)
            expect(panel.locator('article').filter(has_text='財務根拠確認')).to_have_count(0)
            assert errors == []
            page.screenshot(path=str(artifacts / 'work-queue-finance-pointer.png'), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        logs.close()
