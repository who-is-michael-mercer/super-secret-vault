import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path
import pytest
from relayvault.vault import capsule, store
from relayvault import main, settings


class Process:
    def __init__(self, args, home, *, module="relayvault", python=None, env=None):
        self.master, slave = pty.openpty()
        self.data = b""
        environment = os.environ | {
            "RELAY_HOME": str(home),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        }
        if env is not None:
            environment = env
        self.process = subprocess.Popen(
            [python or sys.executable, "-m", module, *args],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=environment,
        )
        os.close(slave)

    def send(self, text):
        os.write(self.master, text.encode() if isinstance(text, str) else text)

    def wait_for(self, needle, timeout=8):
        needle = needle.encode() if isinstance(needle, str) else needle
        deadline = time.monotonic() + timeout
        start = len(self.data)
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                self.data += chunk
                if needle in self.data[start:]:
                    return self.data[start:]
            if self.process.poll() is not None:
                break
        raise AssertionError(
            f"Missing {needle!r}; output={self.data!r}; exit={self.process.poll()}"
        )

    def finish(self, status=0):
        assert self.process.wait(timeout=8) == status

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        os.close(self.master)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@pytest.fixture
def vault(tmp_path, monkeypatch):
    home = tmp_path / "state"
    monkeypatch.setenv("RELAY_HOME", str(home))
    header, key = capsule.metadata("CLI-password")
    path = tmp_path / "vault.relayvault"
    store.create(path, header, bytes(key))
    key[:] = bytes(len(key))
    return path, home


def test_real_dormant_wake_two_command_auth_lock(vault):
    path, home = vault
    with Process(["open", str(path)], home) as app:
        output = app.wait_for("extent")
        for absent in (b"password", b"help", b"cipher", b"objects", b">"):
            assert absent not in output
        app.send("wrong")
        time.sleep(0.03)
        app.send(b"relay\x1b[A\x1b[A\x1b[B\x1b[D\x1b[C")
        output = app.wait_for("relay0:/link> ")
        assert b"wrong" not in output
        app.send("attach 13\r")
        app.wait_for("sealctl:/control> ")
        app.send("unlock\r")
        app.wait_for("password: ")
        app.send("CLI-password\r")
        output = app.wait_for("vault0:/data> ")
        assert b"CLI-password" not in output
        app.send("list\r")
        app.wait_for("vault0:/data> ")
        app.send("lock\r")
        app.wait_for("extent")
        app.send(b"\x04")
        app.finish(130)


def test_maintenance_file_operations_and_legacy_module(vault, tmp_path):
    path, home = vault
    source = tmp_path / "source"
    source.write_text("CLI data")
    destination = tmp_path / "plaintext"
    with Process(["maintenance", str(path)], home, module="vaultgame") as app:
        app.wait_for("password: ")
        app.send("CLI-password\r")
        app.wait_for("vault0:/data> ")
        app.send(f'store "{source}" name\r')
        app.wait_for("vault0:/data> ")
        app.send(f'retrieve name "{destination}"\r')
        app.wait_for("vault0:/data> ")
        app.send("exit\r")
        app.finish()
    assert destination.read_text() == "CLI data"


def test_init_verify_export_and_recovery_cli(tmp_path):
    home = tmp_path / "state"
    path = tmp_path / "new.relayvault"
    with Process(["init", str(path)], home) as app:
        app.wait_for("password: ")
        app.send("new-password\r")
        app.wait_for("confirm password: ")
        app.send("new-password\r")
        app.wait_for("created:")
        app.finish()
    for command in ("verify", "backup", "recover"):
        destination = tmp_path / f"{command}.relayvault"
        args = (
            [command, str(path)]
            if command == "verify"
            else [command, str(path), str(destination)]
        )
        with Process(args, home) as app:
            app.wait_for("password: ")
            app.send("new-password\r")
            if command == "recover":
                app.wait_for("[y/N] ")
                app.send("yes\r")
            app.finish()
        if command != "verify":
            assert destination.exists()


def test_static_cover_no_auth_or_disclosure(vault, capsys):
    path, _ = vault
    assert main.main(["open", str(path)]) == 0
    output = capsys.readouterr().out
    assert (
        "password" not in output
        and "cipher" not in output
        and "initialized" not in output
    )


def test_auth_backoff_and_effects_off(vault):
    path, home = vault
    config = settings.defaults()
    config["effects"] = False
    settings.save(config)
    with Process(["maintenance", str(path)], home) as app:
        for _ in range(3):
            app.wait_for("password: ")
            app.send("WRONG\r")
        app.finish(1)
        assert b"WRONG" not in app.data
    with Process(["maintenance", str(path)], home) as app:
        output = app.wait_for("backoff")
        assert b"password:" not in output
        app.finish(1)


def test_idle_timeout_clears_without_keypress(vault):
    path, home = vault
    config = settings.defaults()
    config["auto_lock_seconds"] = 0.1
    settings.save(config)
    with Process(["open", str(path)], home) as app:
        app.wait_for("extent")
        app.send(b"relay\x1b[A\x1b[A\x1b[B\x1b[D\x1b[C")
        app.wait_for("relay0:/link> ")
        app.send("attach 13\r")
        app.wait_for("sealctl:/control> ")
        app.send("unlock\r")
        app.wait_for("password: ")
        app.send("CLI-password\r")
        app.wait_for("vault0:/data> ")
        app.wait_for("extent")
        app.send(b"\x04")
        app.finish(130)


def test_suspend_resume_and_signal_exit_restore_terminal(vault):
    import signal

    path, home = vault
    with Process(["open", str(path)], home) as app:
        app.wait_for("extent")
        app.process.send_signal(signal.SIGTSTP)
        app.wait_for(b"\x1b[?1049l")
        app.process.send_signal(signal.SIGCONT)
        app.wait_for("extent")
        app.process.send_signal(signal.SIGTERM)
        app.wait_for(b"\x1b[?1049l")
        app.finish(130)
