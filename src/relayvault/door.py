"""Opt-in Swayimg lifecycle and fixed-argv terminal handoff; no desktop observer."""

import fcntl
import hashlib
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile

from . import image_info, settings
from .input import VIEWER_KEYS, key_name

SEQUENCE = ['KEY_HOME','KEY_F7','KEY_END','KEY_PRINT','KEY_PGUP','KEY_CAPSLOCK','KEY_ESC','KEY_HOME']


def enroll(config, path, region=None, zoom=None, tolerance=None):
    info = image_info.inspect(path)
    if max(info.width, info.height) > 16384 or info.width * info.height > 64 * 1024 * 1024:
        raise ValueError('Image exceeds the visual-door decoded size limit.')
    region = region or [info.width*.45, info.height*.45, info.width*.1, info.height*.1]
    door = dict(carrier_path=info.path, viewer='swayimg', binding=info.binding,
        region=region, zoom=zoom or [.9,1.1], tolerance=tolerance or [.12,.12],
        sequence=list(SEQUENCE))
    candidate = settings.validate(config | {'image_door':door, 'target':info.path})
    x,y,w,h = region
    if x+w > info.width or y+h > info.height:
        raise ValueError('Target region falls outside the image.')
    return candidate


def checked(config, expected=None):
    policy = config['image_door']
    if policy is None:
        raise ValueError('Image door is disabled. Enroll a PNG first.')
    if expected is not None and not image_info.current(policy['carrier_path'], expected):
        raise ValueError('Displayed image is stale.')
    info = image_info.inspect(policy['carrier_path'])
    if info.binding != policy['binding'] or expected is not None and info.stamp != expected:
        raise ValueError('Image binding changed; reload or enroll the intended image.')
    return info


def lua_string(value):
    # Decimal byte escapes are valid Lua, including arbitrary filenames. No eval
    # of owner-supplied Lua, shell quoting, or interpolation of source syntax.
    return '"' + ''.join(f'\\{b:03d}' for b in value.encode()) + '"'


def lua_config(config):
    p = config['image_door']
    x,y,w,h = p['region']
    values = dict(image=p['carrier_path'], x=x,y=y,width=w,height=h,
        zoom_min=p['zoom'][0],zoom_max=p['zoom'][1],
        tolerance_x=p['tolerance'][0],tolerance_y=p['tolerance'][1],
        timeout=config['sequence_timeout_seconds'])
    fields = [f'{k}={lua_string(v) if isinstance(v,str) else repr(v)}' for k,v in values.items()]
    fields.append('sequence={' + ','.join(str(VIEWER_KEYS[key_name(k)]) for k in p['sequence']) + '}')
    return 'return {' + ','.join(fields) + '}\n'


def terminal_argv(info, foot):
    return [foot, '--title=Image inspection', '--app-id=image-inspection',
        sys.executable, '-m', 'relayvault', '_door-open', info.stamp]


def acquire_lock(path):
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or Path.home() / '.cache')
    if not runtime.is_absolute():
        raise ValueError('Runtime directory must be absolute.')
    directory = settings.private_directory(runtime / 'relay-image-door')
    name = hashlib.sha256(path.encode()).hexdigest() + '.lock'
    fd = os.open(directory / name, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        image_info.stamp(os.fstat(fd))
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def view(config, viewer):
    checked(config)
    if not os.environ.get('WAYLAND_DISPLAY'):
        raise ValueError('The image door requires native Wayland.')
    viewer = str(Path(viewer).expanduser().resolve(strict=True))
    foot = shutil.which('foot')
    if not foot:
        raise ValueError('Foot is required for the qualified terminal profile.')
    root = Path(__file__).parent / 'swayimg'
    directory = settings.private_directory(settings.home())
    child = terminal = None
    lock = None
    with tempfile.TemporaryDirectory(prefix='.viewer-', dir=directory) as temp:
        config_file = Path(temp) / 'config.lua'
        config_file.write_text(lua_config(config))
        config_file.chmod(0o600)
        parent, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            env = os.environ | {
                'RELAY_SWAYIMG_DOOR':'1', 'RELAY_SWAYIMG_REQUEST_FD':str(peer.fileno()),
                'RELAY_SWAYIMG_SCRIPTS':str(root), 'RELAY_SWAYIMG_CONFIG':str(config_file),
            }
            env.pop('RELAY_SWAYIMG_PROBE', None)
            env.pop('RELAY_SWAYIMG_TESTING', None)
            child = subprocess.Popen([viewer, '--config', str(root / 'door.lua'),
                '--size=1000,750', config['image_door']['carrier_path']],
                env=env, pass_fds=(peer.fileno(),), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            peer.close()
            while child.poll() is None:
                if terminal is not None and terminal.poll() is not None:
                    terminal = None
                    os.close(lock)
                    lock = None
                if not select.select([parent], [], [], .1)[0]:
                    continue
                data = parent.recv(256)
                if terminal is not None or not data or len(data) > 200:
                    continue
                try:
                    expected = data.decode('ascii')
                    # Reload local policy; disable takes effect without a service.
                    latest = settings.load()
                    if latest['image_door'] != config['image_door']:
                        continue
                    info = checked(latest, expected)
                    lock = acquire_lock(info.path)
                    if not image_info.current(info.path, info.stamp):
                        raise ValueError('Image changed before handoff.')
                    terminal = subprocess.Popen(terminal_argv(info, foot),
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                except (ValueError, OSError):
                    if lock is not None:
                        os.close(lock)
                        lock = None
            # The broker lives only as long as its viewer/terminal children.
            if terminal is not None:
                terminal.wait()
            return child.returncode
        finally:
            peer.close()
            parent.close()
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait()
            if terminal is not None and terminal.poll() is None:
                terminal.wait()
            if lock is not None:
                os.close(lock)
