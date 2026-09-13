import pytest
from relayvault import settings


def test_home_precedence_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULTGAME_HOME", str(tmp_path / "old"))
    assert settings.home() == tmp_path / "old"
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "new"))
    assert settings.home() == tmp_path / "new"
    data = settings.defaults()
    data["wake"] = ["x", "UP"]
    settings.save(data)
    assert settings.load() == data
    assert (settings.home() / "preferences.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("wake", [[], ["ESC"], ["\n"], ["x"] * 65])
def test_bad_wake(wake):
    with pytest.raises(ValueError):
        settings.validate(settings.defaults() | {"wake": wake})


def test_backup_ancestors_private_and_synced(tmp_path, monkeypatch):
    import os
    import stat

    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "home"))
    calls = []
    original = os.fsync

    def observe(fd):
        calls.append(os.fstat(fd).st_ino)
        original(fd)

    monkeypatch.setattr(os, "fsync", observe)
    directory = settings.private_directory(settings.home() / "backups" / "identity")
    for path in (settings.home(), directory.parent, directory):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
        assert path.parent.stat().st_ino in calls


@pytest.mark.parametrize(
    "section",
    [
        {"enabled": True, "allowed_actions": [[]], "bindings": {}},
        {"enabled": True, "allowed_actions": [], "bindings": {"channel_reset": []}},
    ],
)
def test_malformed_action_policy_is_controlled(section):
    with pytest.raises(ValueError):
        settings.validate(settings.defaults() | {"real_os_actions": section})


def test_huge_idle_value_is_controlled():
    with pytest.raises(ValueError):
        settings.validate(settings.defaults() | {"auto_lock_seconds": 10**1000})
