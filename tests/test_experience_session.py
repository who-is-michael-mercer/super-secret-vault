"""Cross-state qualification using disposable PTYs, never OS-action executors."""
import fcntl
import os
import select
import signal
import struct
import termios
import time
import pytest
from relayvault import settings
from test_cli import Process, vault

FIRST=b'\x1b[H\x1b[19~\x1b[5~\x1b[F'
FINAL=b'\x1b[D\x1b[C\x1b[18~\x1b[H'


def advance(app,state):
    app.wait_for('inspection incomplete')
    if state=='cover': return
    app.send(FIRST)
    if state=='build':
        app.wait_for('probably fine'); return
    app.wait_for('R / 13'); time.sleep(.12)
    if state=='hold': return
    app.send(FINAL)
    if state=='fade':
        app.wait_for(b'\x1b[2m'); return
    app.wait_for('relay:/media> ')
    if state=='route': return
    app.send('follow 3\r'); app.wait_for('relay:/13> ')
    app.send('open\r'); app.wait_for('password: ')
    if state=='password': return
    app.send('CLI-password\r'); app.wait_for('session: active')


@pytest.mark.parametrize('state',['cover','build','hold','fade','route','password','unlocked'])
@pytest.mark.parametrize('interruption',['eof','term','int','hup'])
def test_restoration_from_every_state(vault,state,interruption):
    path,home=vault
    settings.save(settings.defaults() | {'animation_speed':'fast'})
    with Process(['open',str(path)],home) as app:
        advance(app,state)
        if interruption=='eof': app.send(b'\x04')
        else: app.process.send_signal({'term':signal.SIGTERM,'int':signal.SIGINT,'hup':signal.SIGHUP}[interruption])
        app.wait_for(b'\x1b[?1049l')
        app.finish(130)  # Also compares complete termios with the original PTY.
        assert b'\x1b[?25h\x1b[?2004l' in app.data
        assert b'Traceback' not in app.data


def test_hold_resize_resets_partial_and_recovers(vault):
    path,home=vault
    settings.save(settings.defaults() | {'effects':False})
    with Process(['open',str(path)],home) as app:
        advance(app,'hold')
        app.send(b'\x1b[D\x1b[C')
        time.sleep(.04)
        fcntl.ioctl(app.master,termios.TIOCSWINSZ,struct.pack('HHHH',35,110,0,0))
        app.process.send_signal(signal.SIGWINCH)
        app.wait_for('R / 13')
        app.send(b'\x1b[18~\x1b[H')
        time.sleep(.12)
        if select.select([app.master],[],[],0)[0]:
            assert b'relay:/media>' not in os.read(app.master,65536)
        app.send(FINAL); app.wait_for('relay:/media> ')
        app.send('exit\r'); app.finish()


def test_explicit_legacy_wake_preserved(vault):
    path,home=vault
    settings.save(settings.defaults() | {'effects':False,'wake':['q','HOME']})
    with Process(['open',str(path),'--legacy-wake'],home) as app:
        app.wait_for('inspection incomplete')
        app.send(b'q\x1b[H'); app.wait_for('R / 13')
        time.sleep(.1)
        app.send(FINAL); app.wait_for('relay:/media> ')
        app.send('exit\r'); app.finish()


@pytest.mark.parametrize('state',['cover','password','unlocked'])
def test_terminal_loss_closes_without_traceback(vault,state):
    path,home=vault
    settings.save(settings.defaults() | {'effects':False})
    with Process(['open',str(path)],home) as app:
        advance(app,state)
        os.close(app.master); app.master=None
        assert app.process.wait(timeout=8)==130
