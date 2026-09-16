import os
import subprocess
from pathlib import Path
import pytest
from relayvault import door, image_info, settings
from test_carrier import carrier, image_bytes
from relayvault.vault.session import VaultSession


def test_binding_survives_real_atomic_vault_commit(carrier, tmp_path):
    path, original = carrier
    config = door.enroll(settings.defaults(), path)
    before = door.checked(config)
    assert before.binding == image_info.inspect(original).binding
    source = tmp_path/'source'; source.write_bytes(b'new secret')
    with VaultSession.authenticate('password', path) as session:
        session.store(source)
    with pytest.raises(ValueError, match='stale'):
        door.checked(config, before.stamp)
    after = door.checked(config)
    assert after.stamp != before.stamp and after.binding == before.binding


def test_replacement_rename_and_aliases(tmp_path):
    path=tmp_path/'a.png'; path.write_bytes(image_bytes())
    config=door.enroll(settings.defaults(),path)
    before=door.checked(config)
    elsewhere=tmp_path/'sub'; elsewhere.mkdir()
    other=elsewhere/path.name; other.write_bytes(path.read_bytes())
    assert image_info.inspect(other).stamp != before.stamp
    path.rename(tmp_path/'renamed.png')
    assert not image_info.current(path,before.stamp)
    path.symlink_to(other)
    with pytest.raises((ValueError,OSError)):
        door.checked(config)
    path.unlink(); path.write_bytes(other.read_bytes())
    assert not image_info.current(path,before.stamp)
    os.link(path,tmp_path/'hard.png')
    with pytest.raises(ValueError):
        door.checked(config)


def test_request_and_lua_are_fixed_data(tmp_path):
    path=tmp_path/'a"; $(echo nope).png'; path.write_bytes(image_bytes())
    config=door.enroll(settings.defaults(),path)
    lua=door.lua_config(config)
    assert '$(echo nope)' not in lua and 'os.execute' not in lua
    info=door.checked(config)
    argv=door.terminal_argv(info,'/usr/bin/foot')
    assert argv[-3:] == ['relayvault','_door-open',info.stamp]
    assert str(path) not in argv and '-c' not in argv
    if Path('/usr/bin/lua').exists():
        result=subprocess.run(['lua','-e',lua.replace('return {','local c={')+'; print(c.image)'],text=True,capture_output=True,check=True)
        assert result.stdout.rstrip('\n') == str(path)


def test_duplicate_lock_and_release(tmp_path,monkeypatch):
    monkeypatch.setenv('RELAY_HOME',str(tmp_path/'home'))
    monkeypatch.setenv('XDG_RUNTIME_DIR',str(tmp_path/'runtime'))
    fd=door.acquire_lock('/some/image.png')
    try:
        monkeypatch.setenv('RELAY_HOME',str(tmp_path/'different-profile'))
        with pytest.raises(BlockingIOError):
            door.acquire_lock('/some/image.png')
        other=door.acquire_lock('/other.png'); os.close(other)
    finally:
        os.close(fd)
    os.close(door.acquire_lock('/some/image.png'))


def test_disabled_and_wrong_binding(tmp_path):
    with pytest.raises(ValueError,match='disabled'):
        door.checked(settings.defaults())
    path=tmp_path/'a.png'; path.write_bytes(image_bytes())
    config=door.enroll(settings.defaults(),path)
    config['image_door']['binding']='0'*64
    with pytest.raises(ValueError,match='binding'):
        door.checked(config)


def test_invalid_regions_and_sequences(tmp_path):
    path=tmp_path/'a.png'; path.write_bytes(image_bytes())
    with pytest.raises(ValueError):
        door.enroll(settings.defaults(),path,[0,0,100,100])
    config=door.enroll(settings.defaults(),path)
    config['image_door']['sequence']=['KEY_FN']
    with pytest.raises(ValueError):
        settings.validate(config)


def test_decoded_image_budget_is_an_enrollment_limit(tmp_path):
    import struct
    from test_image_info import chunk
    raw=image_bytes()
    for width,height in ((16385,1),(8193,8192)):
        path=tmp_path/'large.png'
        path.write_bytes(raw[:8]+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+raw[33:])
        with pytest.raises(ValueError,match='decoded size limit'):
            door.enroll(settings.defaults(),path)
