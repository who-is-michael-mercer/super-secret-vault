"""Install a wheel into a disposable environment and exercise real PTY entrypoints."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from test_cli import Process
from test_carrier import image_bytes
import conftest  # installs the machine-action audit backstop


def main():
    wheel = next((REPO / "dist").glob("super_secret_vault-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert not any(
            "v2_reference" in name or name.startswith("tests/")
            for name in archive.namelist()
        )
        assert sorted(
            name for name in archive.namelist() if name.startswith("vaultgame/")
        ) == ["vaultgame/__init__.py", "vaultgame/__main__.py"]
    with tempfile.TemporaryDirectory(prefix="relay-installed-") as directory:
        root = Path(directory)
        subprocess.run([sys.executable, "-m", "venv", str(root / "env")], check=True)
        python = str(root / "env" / "bin" / "python")
        result = subprocess.run(
            [python, "-m", "pip", "install", str(wheel)], capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        environment = {
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONPATH", "VAULTGAME_HOME", "RELAY_HOME"}
        }
        environment["RELAY_HOME"] = str(root / "state")
        environment["PYTHONSAFEPATH"] = "1"
        previous = Path.cwd()
        os.chdir(root)
        try:
            imported = subprocess.check_output(
                [python, "-c", "import relayvault; print(relayvault.__file__)"],
                env=environment,
                text=True,
            ).strip()
            assert imported.startswith(str(root / "env"))
            image = root / "source.png"
            image.write_bytes(image_bytes())
            target = root / "carrier.png"
            with Process(
                ["init", str(target), "--image", str(image)],
                root / "state",
                python=python,
                env=environment,
            ) as app:
                app.wait_for("password: ")
                app.send("installed-password\r")
                app.wait_for("confirm password: ")
                app.send("installed-password\r")
                app.wait_for("created:")
                app.finish()
            with Process(
                ["open", str(target)], root / "state", python=python, env=environment
            ) as app:
                app.wait_for("extent")
                app.send(b"relay\x1b[A\x1b[A\x1b[B\x1b[D\x1b[C")
                app.wait_for("relay0:/link> ")
                app.send("attach 13\r")
                app.wait_for("sealctl:/control> ")
                app.send("unlock\r")
                app.wait_for("password: ")
                app.send("installed-password\r")
                app.wait_for("vault0:/data> ")
                app.send("exit\r")
                app.finish()
            with Process(
                ["verify", str(target)],
                root / "state",
                module="vaultgame",
                python=python,
                env=environment,
            ) as app:
                app.wait_for("password: ")
                app.send("installed-password\r")
                app.wait_for("verified:")
                app.finish()
            result = subprocess.run(
                [str(root / "env" / "bin" / "relay"), "--help"],
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "maintenance" in result.stdout
            print(
                "Installed wheel: PNG initialization, dormant wake, two-command route, authentication, verification, relay executable and legacy module shim passed outside checkout."
            )
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    main()
