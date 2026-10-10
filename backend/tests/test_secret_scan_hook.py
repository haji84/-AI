"""Execute the actual pre-push entry point in generated disposable repositories."""
import os
from pathlib import Path
import secrets
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('case',['clean','dirty-secret','missing-scanner'])
def test_pre_push_gate_uses_actual_pinned_scanner(tmp_path,case):
    root=Path(__file__).resolve().parents[2]
    assert (root/'.githooks/pre-push').is_file(),'pre-push gate is missing'
    binary=os.environ.get('FIRE_AI_GITLEAKS_BIN')
    assert binary,'FIRE_AI_GITLEAKS_BIN must identify the pinned official binary'
    repo=tmp_path/'synthetic';repo.mkdir()
    def git(*args):
        subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
    git('init','-q');git('config','user.name','Synthetic');git('config','user.email','synthetic@example.invalid')
    (repo/'scripts').mkdir();shutil.copyfile(root/'scripts/security_scan.py',repo/'scripts/security_scan.py')
    (repo/'.githooks').mkdir();hook=repo/'.githooks/pre-push';shutil.copyfile(root/'.githooks/pre-push',hook);hook.chmod(0o700)
    git('add','-A');git('commit','-qm','synthetic clean fixture')
    token=None
    if case=='dirty-secret':
        token='gh'+'p_'+''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(36))
        (repo/'private-fixture.txt').write_text('credential = '+token+'\n')
    env={**os.environ,'FIRE_AI_GITLEAKS_BIN':binary}
    if case=='missing-scanner':env.pop('FIRE_AI_GITLEAKS_BIN')
    result=subprocess.run([str(hook)],cwd=repo,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode=={'clean':0,'dirty-secret':1,'missing-scanner':2}[case]
    output=result.stdout+result.stderr
    assert str(repo) not in output
    if token:assert token not in output
