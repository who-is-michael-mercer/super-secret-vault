"""Owner-local presentation and activation policy; never imported from carriers."""

import json
import math
import os
from pathlib import Path
import stat
import tempfile

DEFAULT_WAKE = ("r", "e", "l", "a", "y", "UP", "UP", "DOWN", "LEFT", "RIGHT")
ACTIONS = {"logout", "reboot", "shutdown", "close_terminal"}


def home():
    return (
        Path(
            os.environ.get("RELAY_HOME")
            or os.environ.get("VAULTGAME_HOME")
            or Path.home() / ".relayvault"
        )
        .expanduser()
        .absolute()
    )


def private_directory(path):
    path = Path(path)
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("Relay state may not contain symlinks.")
    state_home = home()
    if path != state_home and path.is_relative_to(state_home):
        private_directory(state_home)
    if not path.parent.exists():
        private_directory(path.parent)
    created = not path.exists()
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Relay state must be an owner-controlled directory.")
    path.chmod(0o700)
    if created:
        # A synced backup file is not durable if an ancestor entry can vanish.
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return path


def defaults():
    return dict(
        version=1,
        target=None,
        wake=list(DEFAULT_WAKE),
        effects=True,
        auto_lock_seconds=300,
        real_os_actions=dict(enabled=False, allowed_actions=[], bindings={}),
    )


def validate(data):
    if (
        not isinstance(data, dict)
        or set(data) != set(defaults())
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError("Unsupported local settings.")
    if data["target"] is not None and (
        not isinstance(data["target"], str) or "\0" in data["target"]
    ):
        raise ValueError("Invalid default target.")
    keys = data["wake"]
    if (
        not isinstance(keys, list)
        or not 1 <= len(keys) <= 64
        or any(
            not isinstance(k, str)
            or not (
                k in {"UP", "DOWN", "LEFT", "RIGHT"}
                or len(k) == 1
                and k.isascii()
                and k.isprintable()
                and k != " "
            )
            for k in keys
        )
    ):
        raise ValueError("Wake must contain 1–64 ASCII characters or named arrows.")
    timeout = data["auto_lock_seconds"]
    if (
        type(timeout) not in (int, float)
        or timeout <= 0
        or timeout > 1e308
        or not math.isfinite(timeout)
        or type(data["effects"]) is not bool
    ):
        raise ValueError("Invalid idle/effects setting.")
    policy = data["real_os_actions"]
    if (
        not isinstance(policy, dict)
        or set(policy) != {"enabled", "allowed_actions", "bindings"}
        or type(policy["enabled"]) is not bool
    ):
        raise ValueError("Invalid OS-action policy.")
    if not isinstance(policy["allowed_actions"], list) or any(
        not isinstance(a, str) or a not in ACTIONS for a in policy["allowed_actions"]
    ):
        raise ValueError("Unknown OS action.")
    if not isinstance(policy["bindings"], dict) or any(
        k != "channel_reset" or not isinstance(v, str) or v not in ACTIONS
        for k, v in policy["bindings"].items()
    ):
        raise ValueError("Only channel_reset can bind a fixed OS action.")
    return data


def load():
    path = home() / "preferences.json"
    if not path.exists() and not path.is_symlink():
        return defaults()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Invalid local settings file.")
    return validate(json.loads(path.read_text()))


def save(data):
    data = validate(data)
    directory = private_directory(home())
    fd, temporary = tempfile.mkstemp(prefix=".preferences-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / "preferences.json")
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)
