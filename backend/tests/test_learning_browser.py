"""Real HTTP/Chromium Human learning workflow; synthetic records only."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='real browser CI explicitly required')


def test_human_learning_candidate_evaluation_promotion_and_rollback(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    subprocess.run([sys.executable,'-m','app.bootstrap','--username','learningui','--display-name','Synthetic learning operator','--password','synthetic-learning-ui-password'],cwd=root,env=env,check=True,capture_output=True)
    seed="""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Employee,User,Role,UserRole,Permission,RolePermission
from app.security import hash_password
with Session(engine) as db:
    staff=Employee(display_name='Synthetic intake-only reader');role=Role(code='synthetic_learning_intake',name='Synthetic narrow reader')
    db.add_all([staff,role]);db.flush()
    user=User(employee_id=staff.employee_id,username='intake-only',password_hash=hash_password('synthetic-second-account-password'));db.add(user);db.flush()
    db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
    for code in ['learning.read','learning.record','document.read','intake.read']:
        permission=db.scalar(select(Permission).where(Permission.code==code));db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
    db.commit()
"""
    subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True,capture_output=True)
    logs=(tmp_path/'server.log').open('w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','9091'],cwd=root,env=env,stdout=logs,stderr=logs)
    try:
        for _ in range(100):
            try:urllib.request.urlopen('http://127.0.0.1:9091/health',timeout=.2).close();break
            except OSError:
                if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:raise AssertionError('synthetic server not ready')
        with sync_playwright() as browser_api:
            browser=browser_api.chromium.launch();page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto('http://127.0.0.1:9091/ui/learning.html')
            page.locator('#loginForm input[name=username]').fill('learningui');page.locator('#loginForm input[name=password]').fill('synthetic-learning-ui-password');page.locator('#loginForm button').click()
            expect(page.locator('#workspace')).to_be_visible();page.locator('#task').select_option('ocr')
            expect(page.locator('#champion')).to_contain_text('Baseline')
            page.locator('#humanReason').fill('Synthetic Human verification')
            page.locator('#correctionForm input[name=synthetic]').check();page.locator('#correctionForm textarea[name=input_text]').fill('消火線');page.locator('#correctionForm textarea[name=output_text]').fill('消火栓');page.locator('#correctionForm button').click()
            expect(page.locator('#corrections')).to_contain_text('消火線')
            page.locator('#corrections button').filter(has_text='確認済みにする').click()
            expect(page.locator('#corrections')).to_contain_text('approved')
            page.locator('#corrections input[type=checkbox]').check();page.locator('#buildButton').click()
            expect(page.locator('#artifactSelect option')).to_have_count(1)
            page.locator('#caseForm textarea[name=input]').fill('屋内消火線');page.locator('#caseForm textarea[name=expected]').fill('屋内消火栓');page.locator('#caseForm button').click()
            page.locator('#setForm input[name=name]').fill('Synthetic fixed holdout');page.locator('#setForm input[name=synthetic]').check();page.locator('#setForm button').click()
            expect(page.locator('#evaluationSets')).to_contain_text('Synthetic fixed holdout')
            page.locator('#evaluationSets button').filter(has_text='入力・正解を見る').click();expect(page.locator('#setEvidence')).to_contain_text('屋内消火栓')
            page.locator('#evaluationSets button').filter(has_text='正解を確認済みにする').click();expect(page.locator('#setSelect option')).to_have_count(1)
            page.locator('#evaluateButton').click();expect(page.locator('#evaluations')).to_contain_text('100.0%')
            page.locator('#evaluations button').filter(has_text='Human承認して昇格').click();expect(page.locator('#champion')).to_contain_text('確認済み修正辞書')
            page.locator('#suggestForm textarea').fill('屋内消火線');page.locator('#suggestForm button').click();expect(page.locator('#suggestion')).to_contain_text('屋内消火栓')
            page.locator('#history button').filter(has_text='直前のChampionへ戻す').click();expect(page.locator('#champion')).to_contain_text('Baseline')
            expect(page.locator('#history')).to_contain_text('rollback')
            artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(artifact/'human-gated-learning.png'),full_page=True)
            # A second account lacks fire-investigation source access. It must never
            # inherit the first account's private evidence, form drafts or proposals.
            page.locator('#task').select_option('audio_correction')
            expect(page.locator('#champion')).to_contain_text('Baseline')
            private='PRIVATE synthetic fire-investigation evidence'
            fixed=page.request.post('http://127.0.0.1:9091/learning/evaluation-sets',data={'task':'audio_correction','name':private,'synthetic':True,'cases':[{'input':private,'expected':'Synthetic Human answer'}],'reason':'Synthetic restricted evidence'})
            assert fixed.status==201,fixed.text()
            page.locator('#refreshButton').click();expect(page.locator('#evaluationSets')).to_contain_text(private)
            page.locator('#evaluationSets button').filter(has_text='入力・正解を見る').click();expect(page.locator('#setEvidence')).to_contain_text(private)
            page.locator('#caseForm textarea[name=input]').fill(private);page.locator('#caseForm textarea[name=expected]').fill(private);page.locator('#caseForm button').click()
            page.locator('#suggestForm textarea').fill(private);page.locator('#suggestForm button').click();expect(page.locator('#suggestion')).to_contain_text(private)
            page.locator('#correctionForm textarea[name=input_text]').fill(private);page.locator('#humanReason').fill(private)
            page.locator('#logoutButton').click();expect(page.locator('#loginSection')).to_be_visible()
            page.locator('#loginForm input[name=username]').fill('intake-only');page.locator('#loginForm input[name=password]').fill('synthetic-second-account-password');page.locator('#loginForm button').click()
            expect(page.locator('#workspace')).to_be_visible()
            expect(page.locator('#task option[value=audio_correction]')).to_have_count(0)
            for selector in ['#setEvidence','#suggestion','#cases']:
                expect(page.locator(selector)).to_be_empty()
            for selector in ['#humanReason','#correctionForm textarea[name=input_text]','#caseForm textarea[name=input]','#suggestForm textarea']:
                expect(page.locator(selector)).to_have_value('')
            expect(page.locator('body')).not_to_contain_text(private)
            assert not errors,errors
            browser.close()
    finally:
        server.terminate();server.wait(timeout=15);logs.close()
