"""Public pre-auth status never reads encrypted metadata or reveals names."""

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2_reference.config import AppConfig, RuntimeState, resolve_paths, save_runtime_state_atomic
from v2_reference.dashboard import SCHEMATIC, opaque_object_count, render_dashboard
from v2_reference.terminal import Terminal
from v2_reference.vault import crypto, storage


class TTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def public_layout(tmp_path):
    paths = resolve_paths(tmp_path / 'runtime')
    paths.objects_dir.mkdir(parents=True)
    paths.manifest_path.write_bytes(b'ENCRYPTED-MANIFEST-NOT-FOR-DASHBOARD')
    paths.config_path.write_text('{}')
    save_runtime_state_atomic(paths, RuntimeState())
    (paths.objects_dir / ('a' * 32 + '.vlt')).write_bytes(b'SECRET-CONTENT')
    (paths.objects_dir / ('b' * 32 + '.vlt')).write_bytes(b'SECRET-CONTENT')
    (paths.objects_dir / 'private-filename.txt').write_text('PRIVATE-PLAINTEXT')
    return paths


def render(paths, width=100, effects=False, stream_type=io.StringIO, **kwargs):
    output = stream_type()
    terminal = Terminal(output, effects=effects, width=width,
                        sleep=lambda _: pytest.fail('dashboard delayed'))
    render_dashboard(terminal, paths, **kwargs)
    return output.getvalue()


def test_wide_two_column_layout(public_layout):
    output = render(public_layout)
    lines = output.splitlines()
    assert lines[0].endswith('    relay')
    assert '.----------------------.' in lines[0]
    assert 'interlock' in next(line for line in lines if 'vault      :: initialized' in line)
    assert 'objects    :: 02' in output
    assert output.count('::') == 11
    assert max(map(len, lines)) <= 100


def test_narrow_stacks_art_above_status(public_layout):
    output = render(public_layout, width=45)
    assert output.startswith(SCHEMATIC + '\n\nrelay\n')
    assert max(map(len, output.splitlines())) <= 45
    assert output.index('interlock') < output.index('runtime')


def test_uninitialized_layout_does_not_create_files(tmp_path):
    paths = resolve_paths(tmp_path / 'absent')
    output = render(paths)
    assert 'vault      :: uninitialized' in output
    assert 'archive    :: offline' in output
    assert 'objects    :: 00' in output
    assert 'session    :: locked' in output
    assert not paths.home.exists()


@pytest.mark.parametrize('seconds,expected', [(30, '30s'), (-1, 'clear'), (0, 'clear')])
def test_cooldown_uses_public_state_and_injected_time(public_layout, seconds, expected):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    save_runtime_state_atomic(public_layout, RuntimeState(cooldown_until=(now + timedelta(seconds=seconds)).isoformat()))
    assert 'cooldown   :: ' + expected in render(public_layout, now=now)


def test_manifest_objects_and_secret_config_are_never_read_or_displayed(public_layout, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Pre-auth dashboard attempted decryption')
    monkeypatch.setattr(storage, 'load_manifest', forbidden)
    monkeypatch.setattr(crypto, 'decrypt_bytes', forbidden)
    original_open = Path.open
    def guarded_open(path, *args, **kwargs):
        assert path != public_layout.manifest_path
        assert public_layout.objects_dir not in path.parents
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    config = AppConfig(vault_id='PRIVATE-VAULT-ID', key_check={'nonce': 'PRIVATE-NONCE'},
                       kdf={'salt': 'PRIVATE-SALT'},
                       encryption={'algorithm': 'AES-256-GCM', 'format_version': 1})
    output = render(public_layout, config=config)
    for secret in ('PRIVATE', 'SECRET', 'private-filename.txt', 'a' * 32, 'b' * 32, 'ENCRYPTED-MANIFEST'):
        assert secret not in output
    assert 'aes-256-gcm' in output and 'argon2id' in output


def test_object_count_ignores_links_directories_and_staging(public_layout, tmp_path):
    obj = public_layout.objects_dir
    (obj / ('c' * 32 + '.vlt')).symlink_to(obj / ('a' * 32 + '.vlt'))
    (obj / ('d' * 32 + '.vlt')).mkdir()
    (obj / 'pending.partial').write_bytes(b'staging')
    assert opaque_object_count(public_layout) == '02'
    other = resolve_paths(tmp_path / 'linked')
    other.home.symlink_to(public_layout.home, target_is_directory=True)
    assert opaque_object_count(other) == 'unavailable'


@pytest.mark.parametrize('stream_type,effects', [(TTY, False), (io.StringIO, True), (io.StringIO, False)])
def test_static_dashboard_has_no_ansi(public_layout, stream_type, effects):
    output = render(public_layout, stream_type=stream_type, effects=effects)
    assert '\x1b' not in output and '\r' not in output
    assert 'vault      :: initialized' in output


def test_tty_dashboard_uses_cyan_accent(public_layout):
    assert '\x1b[36m' in render(public_layout, stream_type=TTY, effects=True)


def test_denied_count_reports_no_private_details(public_layout, monkeypatch):
    from v2_reference import dashboard
    def denied(*args):
        raise PermissionError('PRIVATE-PATH')
    monkeypatch.setattr(dashboard.os, 'scandir', denied)
    output = render(public_layout)
    assert 'objects    :: unavailable' in output
    assert 'PRIVATE' not in output


def test_very_narrow_uses_compact_schematic(public_layout):
    output = render(public_layout, width=32)
    assert '[ seal ]' in output
    assert 'interlock' not in output
    assert output.index('[ seal ]') < output.index('runtime')
    assert max(map(len, output.splitlines())) <= 32
