"""All server-rendered entry points share the fixed renewal redirect."""
from pathlib import Path
import subprocess


def test_all_browser_entry_points_install_password_guard_and_renewal_form():
    root=Path(__file__).resolve().parents[2]
    for path in (root/'frontend').glob('*.html'):
        assert '<script src="/ui/auth-session.js"></script>' in path.read_text(),path
    html=(root/'frontend/password.html').read_text()
    assert 'autocomplete="current-password"' in html
    assert 'autocomplete="new-password"' in html
    assert 'maxlength="128"' in html


def test_guard_redirects_only_to_fixed_renewal_page_and_preserves_response(tmp_path):
    root=Path(__file__).resolve().parents[2]
    script=tmp_path/'guard.js'
    script.write_text(r'''
const vm=require('vm'),fs=require('fs');let destination=null;
const response={headers:{get:name=>name==='X-FireAI-Password-Renewal'?'required':null}};
const context={window:{location:{pathname:'/ui/learning.html',replace:value=>{destination=value;}},fetch:async()=>response}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
(async()=>{
 if(await context.window.fetch('/learning/context')!==response)throw Error('response replaced');
 if(destination!=='/ui/password.html')throw Error('expiry not redirected safely');
 destination=null;context.window.location.pathname='/ui/password.html';await context.window.fetch('/auth/login');
 if(destination!==null)throw Error('renewal loop');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
''')
    result=subprocess.run(['node',str(script),str(root/'frontend/auth-session.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
