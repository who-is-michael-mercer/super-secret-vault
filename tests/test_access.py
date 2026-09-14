import builtins
import os
from pathlib import Path
import subprocess
import pytest
from relayvault.access import AccessController
from relayvault.parser import parse_command, CommandParseError
from relayvault.topology import RESOURCES


def run(c, text): return c.handle(parse_command(text))


def test_fast_path_and_real_boundary():
    c=AccessController()
    assert c.prompt=='relay:/media> '
    assert run(c,'open').action==''
    assert 'layer 3' in run(c,'peel').message
    assert run(c,'follow 3').message.startswith('handoff: local')
    assert c.prompt=='relay:/13> '
    assert run(c,'knock').message=='no.'
    assert run(c,'knock --politely').action==''
    assert run(c,'open').action=='authenticate'
    assert not hasattr(c,'session')
    run(c,'back'); assert c.prompt=='relay:/media> '
    run(c,'follow 3'); assert run(c,'open').action=='authenticate'


def test_all_resources_explorable_and_never_resolve_paths():
    c=AccessController()
    for node in RESOURCES:
        run(c,'back')
        if node!='media': run(c,'follow '+('3' if node=='13' else node))
        assert set(run(c,'ls').message.split())==set(RESOURCES[node])
        for name,contents in RESOURCES[node].items():
            assert run(c,'cat '+name).message==contents
            assert run(c,'inspect '+name).message==contents
        for name in ('trace','probe','status'):
            assert run(c,name).message and not run(c,name).action
    assert run(c,'reset channel').action=='incident'
    assert c.node=='media'
    assert run(c,'sleep').action=='sleep'


@pytest.mark.parametrize('text',[
    'ls /','ls ..','cat /etc/passwd','cat ../layers','cat ~/secret','cd /',
    'env','printenv','python -c anything','sh','bash','$(touch /tmp/nope)',
    '`id`','cat layers; id','cat layers | sh','cat layers > /tmp/out',
    'follow 03','follow /3','open now','knock --force','peel now',
    'cat layers\nopen','follow service; open','cat "$HOME"'])
def test_route_has_no_host_capabilities(monkeypatch,text):
    def forbidden(*a,**k): pytest.fail('Fictional route accessed a host capability')
    for obj,name in ((builtins,'open'),(Path,'open'),(Path,'iterdir'),(Path,'stat'),
                     (os,'listdir'),(os,'system'),(subprocess,'Popen')):
        monkeypatch.setattr(obj,name,forbidden)
    c=AccessController()
    try:
        result=run(c,text)
    except CommandParseError:
        return
    assert result.action=='' and result.message=='command: unavailable'
