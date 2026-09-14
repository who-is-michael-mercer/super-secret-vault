"""Install a wheel outside the checkout; exercise real CLI, PTY and storage paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tests'))
from test_cli import Process
from test_carrier import image_bytes
import conftest  # Real machine actions are forbidden throughout this process.


def ritual(app):
    app.wait_for('inspection complete')
    app.send(b'\x1b[H\x1b[19~\x1b[5~\x1b[F')
    app.wait_for('R / 13'); time.sleep(.15)
    app.send(b'\x1b[D\x1b[C\x1b[18~\x1b[H')
    app.wait_for('route table retained')
    app.send('peel\r'); app.wait_for('layer 3')
    app.send('follow 3\r'); app.wait_for('roundtrip: below useful precision')
    app.send('open\r')
    output=app.wait_for('password: ')
    assert b'Password authentication required.' in output
    app.send('installed-password\r'); app.wait_for('session: active')


def main():
    started=time.monotonic(); passed=[]
    wheel=max((REPO/'dist').glob('super_secret_vault-*.whl'),key=lambda p:p.stat().st_mtime_ns)
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist()
        assert not any('v2_reference' in n or n.startswith('tests/') for n in names)
        assert sorted(n for n in names if n.startswith('vaultgame/'))==['vaultgame/__init__.py','vaultgame/__main__.py']
        assert all('relayvault/swayimg/'+n in names for n in ('door.lua','matcher.lua'))
    passed.append('wheel contains production Lua and legacy entry shim, no test fixtures')
    with tempfile.TemporaryDirectory(prefix='relay-installed-') as directory:
        root=Path(directory)
        subprocess.run([sys.executable,'-m','venv',str(root/'env')],check=True)
        python=str(root/'env/bin/python')
        subprocess.run([python,'-m','pip','install',str(wheel)],check=True,capture_output=True)
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','VAULTGAME_HOME','RELAY_HOME'}}
        env.update(RELAY_HOME=str(root/'state'),PYTHONSAFEPATH='1')
        def command(*args):
            return subprocess.run([python,'-m','relayvault',*args],env=env,cwd=root,
                check=True,capture_output=True,text=True).stdout
        def app(args, module='relayvault'):
            return Process(args,root/'state',python=python,env=env,module=module)
        previous=Path.cwd(); os.chdir(root)
        try:
            imported=subprocess.check_output([python,'-c','import relayvault; print(relayvault.__file__)'],env=env,text=True).strip()
            assert imported.startswith(str(root/'env'))
            passed.append('fresh venv imports installed package outside checkout')
            image=root/'source.png'; image.write_bytes(image_bytes())
            target=root/'carrier.png'
            with app(['init',str(target),'--image',str(image)]) as process:
                process.wait_for('password: '); process.send('installed-password\r')
                process.wait_for('confirm password: '); process.send('installed-password\r')
                process.wait_for('created:'); process.finish()
            passed.append('real PNG initialization and password confirmation')
            command('configure','--animation-speed','fast')
            assert 'enrolled' in command('door','enroll',str(target))
            policy=json.loads((root/'state/preferences.json').read_text())
            assert policy['version']==2 and not policy['real_os_actions']['enabled']
            assert (root/'state/preferences.json').stat().st_mode & 0o777 == 0o600
            passed.append('installed image enrollment and private v2 settings')
            source=root/'message.txt'; source.write_text('Installed experience round trip.\n')
            destination=root/'retrieved.txt'
            with app(['open',str(target)]) as process:
                ritual(process)
                passed.append('inspector, both hidden inputs, animated build/fade, route, real auth')
                process.send(f'store "{source}" note\r'); process.wait_for('store: verified and committed')
                process.send(f'retrieve note "{destination}"\r'); process.wait_for('retrieve: authenticated and written')
                assert destination.read_bytes()==source.read_bytes()
                passed.append('authenticated store/retrieve content round trip')
                process.send('lock\r'); ritual(process)
                process.send('list\r'); process.wait_for('note —')
                process.send('exit\r'); process.finish()
                assert b'installed-password' not in process.data
            passed.append('lock, full ritual reopen, password secrecy and termios restoration')
            with app(['maintenance',str(target)]) as process:
                process.wait_for('password: '); process.send('installed-password\r')
                process.wait_for('session: active'); process.send('list\r')
                process.wait_for('note —'); process.send('exit\r'); process.finish()
            passed.append('maintenance bypasses concealment and retains real authentication')
            backup=root/'backup.relayvault'; recovered=root/'recovered.relayvault'
            for args in (['backup',str(target),str(backup)],['recover',str(backup),str(recovered)],['verify',str(recovered)]):
                with app(args,module='vaultgame' if args[0]=='verify' else 'relayvault') as process:
                    process.wait_for('password: '); process.send('installed-password\r')
                    if args[0]=='recover':
                        process.wait_for('[y/N] '); process.send('yes\r')
                    process.finish()
                passed.append('installed '+args[0]+' with real password and verified encrypted material')
            assert 'disabled' in command('door','disable')
            passed.append('door disable is local and explicit')
            result=subprocess.run([str(root/'env/bin/relay'),'--help'],env=env,capture_output=True,text=True,check=True)
            assert 'maintenance' in result.stdout and 'view' in result.stdout
            passed.append('installed relay executable')
        finally:
            os.chdir(previous)
    report={'checks':passed,'count':len(passed),'seconds':round(time.monotonic()-started,2)}
    (REPO/'.local').mkdir(exist_ok=True)
    (REPO/'.local/installed-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    for check in passed: print('PASS',check)
    print(f"{len(passed)} installed checks passed in {report['seconds']}s")


if __name__=='__main__': main()
