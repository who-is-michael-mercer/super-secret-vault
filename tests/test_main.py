import importlib
import json

from vaultgame.config import is_initialized, load_config, resolve_paths

main_module = importlib.import_module('vaultgame.main')


def test_init_prompts_and_publishes_complete_configuration(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path / 'home'))
    prompts = []
    def password(prompt):
        prompts.append(prompt)
        return 'disposable-init-password'
    monkeypatch.setattr('getpass.getpass', password)
    assert main_module.main(['init']) == 0
    paths = resolve_paths()
    assert is_initialized(paths)
    assert len(prompts) == 2
    config = load_config(paths)
    assert config.auto_lock_seconds == 300
    assert config.real_os_actions == dict(enabled=False, allowed_actions=[], bindings={})
    assert 'disposable-init-password' not in paths.config_path.read_text()
    assert json.loads(paths.state_path.read_text())['cooldown_until'] is None
    assert 'initialized' in capsys.readouterr().out.lower()

import base64
import runpy
import sys
import uuid
from pathlib import Path

import pytest

from vaultgame import config as config_module
from vaultgame.vault import crypto, storage
from vaultgame.vault.session import AuthenticationError, VaultSession


@pytest.fixture
def init_home(tmp_path, monkeypatch):
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr('getpass.getpass', lambda _: 'INIT-UNIQUE-秘密-7F291')
    return resolve_paths()


def test_init_authentication_fixed_metadata_and_no_secrets(init_home):
    assert main_module.main(['init']) == 0
    config = load_config(init_home)
    assert uuid.UUID(hex=config.vault_id).version == 4
    assert len(base64.b64decode(config.kdf['salt'])) == 16
    assert {k: v for k, v in config.kdf.items() if k != 'salt'} == {
        'iterations': 3, 'memory_kib': 65536, 'lanes': 4, 'length': 32}
    assert config.encryption == {'algorithm': 'AES-256-GCM', 'format_version': 1}
    assert config.traps == dict(enabled=True, disabled_traps=[])
    session = VaultSession.authenticate('INIT-UNIQUE-秘密-7F291', config, init_home)
    try:
        key = bytes(session._key)
        assert session.list_files() == []
        for path in init_home.home.rglob('*'):
            assert 'INIT-UNIQUE' not in path.name
            if path.is_file():
                blob = path.read_bytes()
                assert 'INIT-UNIQUE-秘密-7F291'.encode() not in blob
                assert key not in blob
                assert key.hex().encode() not in blob
                assert base64.b64encode(key) not in blob
        assert not list(init_home.vault_dir.glob('*.json'))
    finally:
        session.lock()
    with pytest.raises(AuthenticationError):
        VaultSession.authenticate('wrong-password', config, init_home)


@pytest.mark.parametrize('answers', [('', ''), ('one', 'two')])
def test_password_rejected_without_runtime_files(init_home, monkeypatch, answers):
    values = iter(answers)
    monkeypatch.setattr('getpass.getpass', lambda _: next(values))
    assert main_module.main(['init']) == 1
    assert not is_initialized(init_home)
    assert not any(path.is_file() for path in init_home.home.rglob('*'))


@pytest.mark.parametrize('exception', [EOFError, KeyboardInterrupt])
def test_interrupted_prompt_is_controlled(init_home, monkeypatch, exception):
    def fail(_):
        raise exception()
    monkeypatch.setattr('getpass.getpass', fail)
    assert main_module.main(['init']) != 0
    assert not is_initialized(init_home)
    assert not any(path.is_file() for path in init_home.home.rglob('*'))


def test_initialized_vault_refuses_reinitialization_before_prompt(init_home, monkeypatch):
    assert main_module.main(['init']) == 0
    original = {p: p.read_bytes() for p in init_home.home.rglob('*') if p.is_file()}
    def forbidden(_):
        pytest.fail('Prompt should not run for initialized vault')
    monkeypatch.setattr('getpass.getpass', forbidden)
    assert main_module.main(['init']) == 1
    assert original == {p: p.read_bytes() for p in init_home.home.rglob('*') if p.is_file()}


@pytest.mark.parametrize('existing', ['config_path', 'state_path', 'manifest_path', 'object'])
def test_partial_prior_files_never_overwritten(init_home, existing):
    path = init_home.objects_dir / 'prior.vlt' if existing == 'object' else getattr(init_home, existing)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'prior-synthetic-data')
    assert main_module.main(['init']) == 1
    assert path.read_bytes() == b'prior-synthetic-data'
    assert not is_initialized(init_home)


@pytest.mark.parametrize('directory', ['vault_dir', 'objects_dir'])
def test_init_rejects_symlink_directory(init_home, tmp_path, directory):
    target = tmp_path / 'elsewhere'
    target.mkdir()
    path = getattr(init_home, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target, target_is_directory=True)
    assert main_module.main(['init']) == 1
    assert list(target.iterdir()) == []


@pytest.mark.parametrize('stage', ['manifest', 'config', 'state'])
def test_partial_initialization_never_claims_completion(init_home, monkeypatch, stage):
    calls = []
    initialize = storage.initialize_empty_vault
    save_config = main_module.save_config_atomic
    def manifest(*args):
        calls.append('manifest')
        assert not is_initialized(init_home)
        if stage == 'manifest':
            raise storage.StorageError('simulated manifest failure')
        return initialize(*args)
    def config(*args, **kwargs):
        calls.append('config')
        assert init_home.manifest_path.is_file()
        assert not is_initialized(init_home)
        if stage == 'config':
            raise OSError('simulated config failure')
        return save_config(*args, **kwargs)
    def state(*args, **kwargs):
        calls.append('state')
        assert init_home.config_path.is_file()
        assert not is_initialized(init_home)
        raise OSError('simulated state failure')
    monkeypatch.setattr(storage, 'initialize_empty_vault', manifest)
    monkeypatch.setattr(main_module, 'save_config_atomic', config)
    monkeypatch.setattr(main_module, 'save_runtime_state_atomic', state)
    assert main_module.main(['init']) == 1
    assert not is_initialized(init_home)
    assert calls == ['manifest', 'config', 'state'][:['manifest', 'config', 'state'].index(stage) + 1]
    assert not list(init_home.home.rglob('*.tmp'))
    assert not list(init_home.home.rglob('*.partial'))


@pytest.mark.parametrize('field', ['config_path', 'state_path'])
def test_concurrent_existing_json_is_not_overwritten(init_home, monkeypatch, field):
    original_link = config_module.os.link
    target = getattr(init_home, field)
    def race(source, destination, **kwargs):
        if Path(destination) == target:
            target.write_bytes(b'concurrent-original')
        return original_link(source, destination, **kwargs)
    monkeypatch.setattr(config_module.os, 'link', race)
    assert main_module.main(['init']) == 1
    assert target.read_bytes() == b'concurrent-original'
    assert not is_initialized(init_home)
    assert not init_home.manifest_path.exists()
    assert not list(init_home.home.rglob('*.tmp'))


def test_module_uses_shared_init_entry_point(init_home, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['vaultgame', 'init'])
    with pytest.raises(SystemExit) as error:
        runpy.run_module('vaultgame', run_name='__main__')
    assert error.value.code == 0
    assert is_initialized(init_home)


def test_init_fresh_vault_ids_and_salts(init_home, monkeypatch, tmp_path):
    assert main_module.main(['init']) == 0
    first = load_config(init_home)
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path / 'second'))
    assert main_module.main(['init']) == 0
    second = load_config(resolve_paths())
    assert first.vault_id != second.vault_id
    assert first.kdf['salt'] != second.kdf['salt']
    assert first.key_check['nonce'] != second.key_check['nonce']


def test_init_write_failure_removes_json_staging(init_home, monkeypatch):
    def fail(data, stream, **kwargs):
        stream.write('{')
        raise OSError('write failed')
    monkeypatch.setattr(config_module.json, 'dump', fail)
    assert main_module.main(['init']) == 1
    assert not is_initialized(init_home)
    assert not list(init_home.home.rglob('*.tmp'))


def test_init_interrupted_after_manifest_stays_incomplete(init_home, monkeypatch):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(main_module, 'save_config_atomic', interrupt)
    assert main_module.main(['init']) == 130
    assert not is_initialized(init_home)


def test_cli_rejects_unknown_command_without_prompt(init_home, monkeypatch):
    def forbidden(_):
        pytest.fail('Unexpected prompt')
    monkeypatch.setattr('getpass.getpass', forbidden)
    with pytest.raises(SystemExit) as error:
        main_module.main(['unknown'])
    assert error.value.code == 2
    assert not init_home.home.exists()


def test_init_rollback_preserves_replaced_owned_path(init_home, monkeypatch):
    def fail_state(*args, **kwargs):
        replacement = init_home.home / 'replacement'
        replacement.write_bytes(b'foreign-config')
        replacement.replace(init_home.config_path)
        raise OSError('state denied')
    monkeypatch.setattr(main_module, 'save_runtime_state_atomic', fail_state)
    assert main_module.main(['init']) == 1
    assert init_home.config_path.read_bytes() == b'foreign-config'
    assert not init_home.manifest_path.exists()
    assert not is_initialized(init_home)


def test_init_rollback_attempts_other_files_when_cleanup_denied(init_home, monkeypatch, capsys):
    unlink = Path.unlink
    def fail_state(*args, **kwargs):
        raise OSError('state denied')
    def fail_config_cleanup(path, *args, **kwargs):
        if path == init_home.config_path:
            raise PermissionError('cleanup denied')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(main_module, 'save_runtime_state_atomic', fail_state)
    monkeypatch.setattr(Path, 'unlink', fail_config_cleanup)
    assert main_module.main(['init']) == 1
    assert 'cleanup was incomplete' in capsys.readouterr().err
    assert not init_home.manifest_path.exists()
    assert not is_initialized(init_home)


def test_init_rollback_tolerates_owned_file_already_removed(init_home, monkeypatch):
    def fail_state(*args, **kwargs):
        init_home.config_path.unlink()
        raise OSError('state denied')
    monkeypatch.setattr(main_module, 'save_runtime_state_atomic', fail_state)
    assert main_module.main(['init']) == 1
    assert not init_home.manifest_path.exists()
    assert not is_initialized(init_home)
