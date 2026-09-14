import fcntl
import os
import signal
import struct
import termios
import time
import pytest
from relayvault import settings, vault_scene
from relayvault.input import TTYInput
from test_input import tty_pair, drain
from test_cli import Process


@pytest.mark.parametrize('width,height',[(1,1),(8,3),(30,10),(41,15),(79,23),(119,39),(239,79),(1000,1000)])
def test_canvas_bounds_and_progress(width,height):
    complete=vault_scene.frame(width,height)
    assert len(complete)==min(height,80)
    assert all(len(row)==min(width,240) for row in complete)
    previous=0
    for p in (0,.1,.3,.5,.7,.9,1):
        current=vault_scene.frame(width,height,p)
        count=sum(c!=' ' for row in current for c in row)
        assert count>=previous
        previous=count
        for y,row in enumerate(current):
            for x,c in enumerate(row):
                assert c==' ' or c==complete[y][x]
    assert vault_scene.frame(width,height)==complete


def test_effects_off_is_immediate_and_drains(tty_pair):
    master,slave,ins,outs,original=tty_pair
    with TTYInput(ins,outs) as keyboard:
        os.write(master,b'old input')
        start=time.monotonic()
        vault_scene.build(keyboard,settings.defaults() | {'effects':False})
        assert time.monotonic()-start < .3
        assert keyboard.poll(.01) is None
        output=drain(master)
        assert b'R / 13' in output and b'probably fine' not in output
    assert termios.tcgetattr(slave)==original


def test_build_timing_and_resize_uses_one_input_owner(monkeypatch):
    clock=[0.0]
    writes=[]
    sizes=[(79,23)]
    class Keyboard:
        def boundary(self): pass
        def _write(self,text): writes.append(text)
        def poll(self,timeout):
            clock[0]+=timeout
            if clock[0]>.3: sizes[0]=(59,19)
    monkeypatch.setattr(vault_scene.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(vault_scene,'dimensions',lambda _ : sizes[0])
    vault_scene.build(Keyboard(),settings.defaults() | {'animation_speed':'fast'})
    assert 1.4 <= clock[0] < 1.45
    assert sum('\x1b[2J' in s for s in writes)>=3
    assert 'R / 13' in ''.join(writes)


def test_interrupted_build_restores_terminal(tty_pair,monkeypatch):
    _,slave,ins,outs,original=tty_pair
    with pytest.raises(KeyboardInterrupt):
        with TTYInput(ins,outs) as keyboard:
            monkeypatch.setattr(keyboard,'poll',lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
            vault_scene.build(keyboard,settings.defaults())
    assert termios.tcgetattr(slave)==original


def test_no_input_crosses_build_or_hold_boundary(tmp_path,monkeypatch):
    home=tmp_path/'home'; monkeypatch.setenv('RELAY_HOME',str(home))
    settings.save(settings.defaults() | {'effects':False})
    path=tmp_path/'ordinary.txt'; path.write_text('ordinary')
    first=b'\x1b[H\x1b[19~\x1b[5~\x1b[F'
    final=b'\x1b[D\x1b[C\x1b[18~\x1b[H'
    with Process(['open',str(path)],home) as app:
        app.wait_for('inspection incomplete')
        app.send(b'\x1b[200~'+first+b'\x1b[201~')
        time.sleep(.1)
        app.send(first+final+b'follow 3\r')
        app.wait_for('R / 13')
        time.sleep(.1)
        app.send(final+b'follow 3\r')
        app.wait_for('relay:/media> ')
        app.send('status\r')
        output=app.wait_for('channel: unselected')
        assert b'channel: unselected' in output
        app.send('exit\r'); app.finish()


def test_fade_timing_resize_and_final_blank(monkeypatch):
    clock=[0.0]; writes=[]; boundaries=[]; size=[(79,23)]
    class Keyboard:
        def boundary(self): boundaries.append(clock[0])
        def _write(self,text): writes.append(text)
        def poll(self,timeout):
            clock[0]+=timeout
            if clock[0]>.3: size[0]=(99,31)
    monkeypatch.setattr(vault_scene.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(vault_scene,'dimensions',lambda _:size[0])
    vault_scene.dissolve(Keyboard(),settings.defaults())
    assert .95<=clock[0]<1
    assert len(boundaries)==2 and boundaries[-1]>=.95
    assert '\x1b[2m' in ''.join(writes)
    assert writes[-1]=='\x1b[0m'
    assert 'R / 13' in ''.join(writes)
    assert sum('\x1b[2J' in w for w in writes)>=3


def test_interrupted_fade_resets_style_and_tty(tty_pair,monkeypatch):
    master,slave,ins,outs,original=tty_pair
    with pytest.raises(EOFError):
        with TTYInput(ins,outs) as keyboard:
            monkeypatch.setattr(keyboard,'poll',lambda _: (_ for _ in ()).throw(EOFError()))
            vault_scene.dissolve(keyboard,settings.defaults())
    assert termios.tcgetattr(slave)==original
    out=drain(master)
    assert out.endswith(b'\x1b[0m\x1b[?25h\x1b[?2004l\x1b[?1049l')


def test_effects_off_fade_still_drains(tty_pair):
    master,_,ins,outs,_=tty_pair
    with TTYInput(ins,outs) as keyboard:
        os.write(master,b'open\r')
        start=time.monotonic()
        vault_scene.dissolve(keyboard,settings.defaults() | {'effects':False})
        assert time.monotonic()-start<.3 and keyboard.poll(.01) is None
