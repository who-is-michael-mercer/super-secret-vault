import json
from pathlib import Path

import pytest

from v2_reference import config
from v2_reference.config import (
    AppConfig,
    ConfigError,
    RuntimeState,
    ensure_runtime_directories,
    is_initialized,
    load_config,
    load_runtime_state,
    resolve_paths,
    save_config_atomic,
    save_runtime_state_atomic,
    validate_config,
)
from v2_reference.main import main


def test_default_home_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv("VAULTGAME_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    paths = resolve_paths()

    assert paths.home == tmp_path / ".relayvault"
    assert paths.config_path == paths.home / "config.json"
    assert paths.state_path == paths.home / "state.json"
    assert paths.vault_dir == paths.home / "vault"
    assert paths.manifest_path == paths.vault_dir / "manifest.vlt"
    assert paths.objects_dir == paths.vault_dir / "objects"
    assert not paths.home.exists()


@pytest.mark.parametrize("kind", ["config", "state"])
@pytest.mark.parametrize("fail_replace", [False, True])
def test_atomic_replacement(tmp_path, monkeypatch, kind, fail_replace):
    paths = config.resolve_paths(tmp_path)
    destination = paths.config_path if kind == "config" else paths.state_path
    value = config.AppConfig() if kind == "config" else config.RuntimeState()
    save = config.save_config_atomic if kind == "config" else config.save_runtime_state_atomic
    original = b'{"schema_version": 1}\n'
    destination.write_bytes(original)
    replace = config.os.replace
    replacements = []

    def observe_replace(source, target):
        source, target = Path(source), Path(target)
        replacements.append(source)
        assert source.parent == destination.parent
        assert source != destination
        assert target == destination
        assert destination.read_bytes() == original
        assert json.loads(source.read_text())["schema_version"] == 1
        if fail_replace:
            raise OSError("replacement failed")
        replace(source, target)

    monkeypatch.setattr(config.os, "replace", observe_replace)
    if fail_replace:
        with pytest.raises(OSError, match="replacement failed"):
            save(paths, value)
        assert destination.read_bytes() == original
    else:
        save(paths, value)
        assert json.loads(destination.read_text())["schema_version"] == 1
    assert len(replacements) == 1
    assert not replacements[0].exists()
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("override", [None, "explicit", Path("explicit")])
def test_home_override(monkeypatch, tmp_path, override):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("VAULTGAME_HOME", "environment")

    expected = "environment" if override is None else "explicit"
    assert resolve_paths(override).home == tmp_path / expected
    assert not (tmp_path / expected).exists()


def test_environment_override_does_not_require_user_home(monkeypatch, tmp_path):
    def unavailable_home():
        raise RuntimeError("Home directory unavailable")

    monkeypatch.setattr(Path, "home", unavailable_home)
    monkeypatch.setenv("VAULTGAME_HOME", str(tmp_path / "application"))

    assert resolve_paths().home == tmp_path / "application"


def test_config_round_trip(tmp_path):
    paths = resolve_paths(tmp_path / "application")
    config = AppConfig(schema_version=1)

    save_config_atomic(paths, config)

    assert load_config(paths) == config
    assert json.loads(paths.config_path.read_text()) == {"schema_version": 1}


@pytest.mark.parametrize(
    "contents",
    ["{", "null", "[]", "{}", '{"schema_version": 2}',
     '{"schema_version": true}', '{"schema_version": 1.0}',
     '{"schema_version": "1"}', '{"schema_version": 1, "unexpected": 0}',
     b"\xff"],
)
def test_malformed_configuration_is_rejected(tmp_path, contents):
    paths = resolve_paths(tmp_path)
    paths.config_path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())

    with pytest.raises(ConfigError):
        load_config(paths)
    if isinstance(contents, str) and contents != "{":
        with pytest.raises(ConfigError):
            validate_config(json.loads(contents))


def test_invalid_config_save_preserves_existing_file(tmp_path):
    paths = resolve_paths(tmp_path)
    paths.config_path.write_text('{"schema_version": 1}\n')
    original = paths.config_path.read_bytes()

    with pytest.raises(ConfigError):
        save_config_atomic(paths, AppConfig(schema_version=True))

    assert paths.config_path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [paths.config_path]


@pytest.mark.parametrize("cooldown", [None, "2026-09-08T17:30:00Z", "2026-09-08T17:30:00+00:00"])
def test_runtime_state_round_trip(tmp_path, cooldown):
    paths = resolve_paths(tmp_path / "application")
    state = RuntimeState(cooldown_until=cooldown)

    save_runtime_state_atomic(paths, state)

    assert load_runtime_state(paths) == state
    assert json.loads(paths.state_path.read_text()) == {
        "schema_version": 1, "cooldown_until": cooldown,
    }


@pytest.mark.parametrize(
    "data",
    [None, [], {}, {"schema_version": True}, {"schema_version": 2},
     {"schema_version": 1, "progress": 2}]
    + [{"schema_version": 1, "cooldown_until": value} for value in
       [True, 42, [], "", "tomorrow", "2026-09-08", "2026-09-08T17:30:00",
        "2026-09-08T17:30:00+02:00"]],
)
def test_malformed_runtime_state_is_rejected(tmp_path, data):
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text(json.dumps(data))

    with pytest.raises(ConfigError):
        load_runtime_state(paths)


def test_invalid_runtime_state_save_preserves_existing_file(tmp_path):
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text('{"schema_version": 1}\n')
    original = paths.state_path.read_bytes()

    with pytest.raises(ConfigError):
        save_runtime_state_atomic(paths, RuntimeState(cooldown_until="tomorrow"))

    assert paths.state_path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [paths.state_path]


def test_missing_persistent_files(tmp_path):
    paths = resolve_paths(tmp_path / "missing")

    with pytest.raises(ConfigError):
        load_config(paths)
    assert load_runtime_state(paths) == RuntimeState()
    assert not paths.home.exists()


def test_state_without_cooldown_uses_default(tmp_path):
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text('{"schema_version": 1}')

    assert load_runtime_state(paths) == RuntimeState()


@pytest.mark.parametrize("kind", ["config", "state"])
def test_atomic_write_failure_cleans_temporary_file(tmp_path, monkeypatch, kind):
    paths = resolve_paths(tmp_path)
    destination = paths.config_path if kind == "config" else paths.state_path
    value = AppConfig() if kind == "config" else RuntimeState()
    save = save_config_atomic if kind == "config" else save_runtime_state_atomic
    original = b'{"schema_version": 1}\n'
    destination.write_bytes(original)

    def fail_write(data, stream, **kwargs):
        stream.write("{")
        raise OSError("write failed")

    monkeypatch.setattr(config.json, "dump", fail_write)

    with pytest.raises(OSError, match="write failed"):
        save(paths, value)

    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("kind", ["config", "state"])
def test_persistent_path_directory_is_rejected(tmp_path, kind):
    paths = resolve_paths(tmp_path)
    path = paths.config_path if kind == "config" else paths.state_path
    load = load_config if kind == "config" else load_runtime_state
    path.mkdir()

    with pytest.raises(ConfigError):
        load(paths)


def test_runtime_directories_can_be_created(tmp_path):
    paths = resolve_paths(tmp_path / "nested" / "application")
    ensure_runtime_directories(paths)
    ensure_runtime_directories(paths)

    assert paths.home.is_dir()
    assert paths.vault_dir.is_dir()
    assert paths.objects_dir.is_dir()
    assert not paths.config_path.exists()
    assert not paths.state_path.exists()
    assert not paths.manifest_path.exists()


@pytest.mark.parametrize("missing", [None, "config_path", "state_path", "manifest_path", "objects_dir"])
def test_initialization_detection(tmp_path, missing):
    paths = resolve_paths(tmp_path / "application")
    assert not is_initialized(paths)
    ensure_runtime_directories(paths)
    assert not is_initialized(paths)
    for path in (paths.config_path, paths.state_path, paths.manifest_path):
        path.touch()
    assert is_initialized(paths)

    if missing is not None:
        path = getattr(paths, missing)
        if path.is_dir():
            path.rmdir()
            path.touch()
        else:
            path.unlink()
            assert not is_initialized(paths)
            path.mkdir()
        assert not is_initialized(paths)


def test_entry_point_routes_without_initializing(tmp_path, monkeypatch, capsys):
    home = tmp_path / "application"
    monkeypatch.setenv("VAULTGAME_HOME", str(home))

    assert main([]) == 0
    output = capsys.readouterr()
    assert "relay init" in output.out
    assert not home.exists()


def test_optional_vault_id_round_trip(tmp_path):
    paths = resolve_paths(tmp_path)
    value = AppConfig(vault_id="test-vault-identity")
    save_config_atomic(paths, value)
    assert load_config(paths) == value
    assert json.loads(paths.config_path.read_text()) == {
        "schema_version": 1, "vault_id": "test-vault-identity",
    }


@pytest.mark.parametrize("vault_id", [None, "", 1, True, [], "ambiguous:id", "\ud800"])
def test_malformed_vault_id_rejected(vault_id):
    with pytest.raises(ConfigError):
        validate_config({"schema_version": 1, "vault_id": vault_id})

import base64


def initialized_config_data():
    return dict(schema_version=1, vault_id='test-vault',
        kdf=dict(salt=base64.b64encode(bytes(16)).decode(), iterations=3,
                 memory_kib=65536, lanes=4, length=32),
        encryption=dict(algorithm='AES-256-GCM', format_version=1),
        key_check=dict(nonce=base64.b64encode(bytes(12)).decode(),
                       ciphertext=base64.b64encode(bytes(37)).decode()),
        auto_lock_seconds=300)


def test_initialized_config_round_trip(tmp_path):
    data = initialized_config_data()
    value = validate_config(data)
    paths = resolve_paths(tmp_path)
    save_config_atomic(paths, value)
    assert load_config(paths) == value
    assert json.loads(paths.config_path.read_text()) == data


@pytest.mark.parametrize('field', ['vault_id', 'kdf', 'encryption', 'key_check', 'auto_lock_seconds'])
def test_partial_initialized_config_rejected(field):
    data = initialized_config_data()
    del data[field]
    with pytest.raises(ConfigError):
        validate_config(data)


@pytest.mark.parametrize('field, value', [
    ('iterations', 2), ('iterations', True), ('iterations', 3.0),
    ('memory_kib', 65535), ('memory_kib', 10**100), ('lanes', 8),
    ('length', 16), ('salt', '%%%'), ('salt', None),
    ('salt', base64.b64encode(bytes(15)).decode()), ('algorithm', 'Argon2id')])
def test_invalid_kdf_rejected_before_library(field, value):
    data = initialized_config_data()
    data['kdf'][field] = value
    with pytest.raises(ConfigError):
        validate_config(data)


@pytest.mark.parametrize('encryption', [None, {}, [], {'algorithm': 'AES-128-GCM', 'format_version': 1},
    {'algorithm': 'AES-256-GCM', 'format_version': True},
    {'algorithm': 'AES-256-GCM', 'format_version': 1, 'nonce': ''}])
def test_invalid_encryption_metadata_rejected(encryption):
    data = initialized_config_data()
    data['encryption'] = encryption
    with pytest.raises(ConfigError):
        validate_config(data)


@pytest.mark.parametrize('field, value', [('nonce', '%%%'), ('nonce', None),
    ('nonce', base64.b64encode(bytes(11)).decode()), ('ciphertext', ''),
    ('ciphertext', base64.b64encode(bytes(15)).decode()), ('extra', '')])
def test_invalid_key_check_rejected(field, value):
    data = initialized_config_data()
    data['key_check'][field] = value
    with pytest.raises(ConfigError):
        validate_config(data)


@pytest.mark.parametrize('timeout', [None, 0, -1, True, '300', float('inf'), float('nan'), 10**1000])
def test_invalid_auto_lock_timeout_rejected(timeout):
    data = initialized_config_data()
    data['auto_lock_seconds'] = timeout
    with pytest.raises(ConfigError):
        validate_config(data)


@pytest.mark.parametrize('timeout', [300, 1, 0.01])
def test_positive_auto_lock_timeout_supported(timeout):
    data = initialized_config_data()
    data['auto_lock_seconds'] = timeout
    assert validate_config(data).auto_lock_seconds == timeout


@pytest.mark.parametrize('kind', ['config', 'state'])
@pytest.mark.parametrize('existing', [False, True])
def test_exclusive_json_publication(tmp_path, kind, existing):
    paths = resolve_paths(tmp_path)
    path = paths.config_path if kind == 'config' else paths.state_path
    save = save_config_atomic if kind == 'config' else save_runtime_state_atomic
    value = AppConfig() if kind == 'config' else RuntimeState()
    if existing:
        path.write_bytes(b'existing-private-data')
        with pytest.raises(FileExistsError):
            save(paths, value, exclusive=True)
        assert path.read_bytes() == b'existing-private-data'
    else:
        save(paths, value, exclusive=True)
        assert json.loads(path.read_text())['schema_version'] == 1
    assert list(tmp_path.iterdir()) == [path]
