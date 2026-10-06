"""Real Chromium renewal of expired synthetic credentials through the LAN UI."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='real browser CI explicitly required')


def test_expired_browser_redirects_renews_and_relogs_without_client_install(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic-expiry.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    subprocess.run([sys.executable,'-m','app.bootstrap','--username','expiryui','--display-name','Synthetic expiry operator','--password','synthetic-expired-ui-password'],cwd=root,env=env,check=True,capture_output=True)
    seed="""
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine
from app.models import User
with Session(engine) as db:
    db.scalar(select(User).where(User.username=='expiryui')).password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    db.commit()
"""
    subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True,capture_output=True)
    logs=(tmp_path/'server.log').open('w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','9092'],cwd=root,env=env,stdout=logs,stderr=logs)
    try:
        for _ in range(100):
            try:urllib.request.urlopen('http://127.0.0.1:9092/health',timeout=.2).close();break
            except OSError:
                if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:raise AssertionError('synthetic expiry server not ready')
        with sync_playwright() as browser_api:
            browser=browser_api.chromium.launch();page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:9092/ui/admin.html')
            page.locator('#loginForm input[name=username]').fill('expiryui');page.locator('#loginForm input[name=password]').fill('synthetic-expired-ui-password');page.locator('#loginForm button').click()
            expect(page).to_have_url('http://127.0.0.1:9092/ui/password.html')
            expect(page.locator('#renewSection')).to_be_visible();expect(page.locator('#message')).to_contain_text('期限切れ')
            assert page.request.get('http://127.0.0.1:9092/administration/accounts').status==403
            page.locator('#renewForm input[name=current_password]').fill('synthetic-expired-ui-password');page.locator('#renewForm input[name=new_password]').fill('synthetic-renewed-ui-password');page.locator('#renewForm input[name=confirmation]').fill('synthetic-renewed-ui-password');page.locator('#renewForm button').click()
            expect(page.locator('#loginSection')).to_be_visible();expect(page.locator('#message')).to_contain_text('更新しました')
            expect(page.locator('#renewForm input[name=new_password]')).to_have_value('')
            assert page.request.get('http://127.0.0.1:9092/auth/me').status==401
            page.locator('#loginForm input[name=username]').fill('expiryui');page.locator('#loginForm input[name=password]').fill('synthetic-renewed-ui-password');page.locator('#loginForm button').click()
            expect(page.locator('#businessLink')).to_be_visible();page.locator('#businessLink').click()
            response=page.request.get('http://127.0.0.1:9092/administration/accounts');assert response.status==200,response.text()
            artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(artifact/'password-renewal.png'),full_page=True)
            assert not errors,errors
            browser.close()
    finally:server.terminate();server.wait(timeout=15);logs.close()
