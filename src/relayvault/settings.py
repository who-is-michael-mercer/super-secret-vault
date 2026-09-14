"""Owner-local presentation and activation policy; never imported from carriers."""

import json
import math
import os
from pathlib import Path
import stat
import tempfile

from .input import TERMINAL_KEYS, VIEWER_KEYS, key_name

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
        version=2,
        image_door=None,  # Disabled until explicit image enrollment.
        inspector_sequence=["KEY_HOME", "KEY_F8", "KEY_PGUP", "KEY_END"],
        vault_sequence=["KEY_LEFT", "KEY_RIGHT", "KEY_F7", "KEY_HOME"],
        sequence_timeout_seconds=5,
        animation_speed="normal",
        presentation="ascii",
        target=None,
        wake=list(DEFAULT_WAKE),
        effects=True,
        auto_lock_seconds=300,
        real_os_actions=dict(enabled=False, allowed_actions=[], bindings={}),
    )


def validate(data):
    if isinstance(data, dict) and type(data.get("version")) is int and data["version"] == 1:
        old = {"version", "target", "wake", "effects", "auto_lock_seconds", "real_os_actions"}
        if set(data) != old:
            raise ValueError("Unsupported local settings.")
        data = defaults() | data | {"version": 2}
    if (
        not isinstance(data, dict)
        or set(data) != set(defaults())
        or type(data["version"]) is not int
        or data["version"] != 2
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
                key_name(k) in TERMINAL_KEYS
                or len(k) == 1
                and k.isascii()
                and k.isprintable()
                and k != " "
            )
            for k in keys
        )
    ):
        raise ValueError("Wake must contain 1–64 ASCII characters or supported terminal keys.")
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
    for field in ("inspector_sequence", "vault_sequence"):
        sequence(data[field], TERMINAL_KEYS)
    number(data["sequence_timeout_seconds"], 0.2, 60)
    if data["animation_speed"] not in ("slow", "normal", "fast") or data["presentation"] not in ("ascii", "text"):
        raise ValueError("Invalid presentation setting.")
    door = data["image_door"]
    if door is not None:
        if not isinstance(door, dict) or set(door) != {
            "carrier_path", "viewer", "binding", "region", "zoom", "tolerance", "sequence"
        }:
            raise ValueError("Invalid image-door policy.")
        path = door["carrier_path"]
        if not isinstance(path, str) or not Path(path).is_absolute() or any(ord(c) < 32 for c in path):
            raise ValueError("Image-door path must be absolute.")
        if door["viewer"] != "swayimg" or not isinstance(door["binding"], str) or len(door["binding"]) != 64 or any(c not in "0123456789abcdef" for c in door["binding"]):
            raise ValueError("Invalid viewer/image binding.")
        for field, size, low, high in (("region", 4, 0, 1000000), ("zoom", 2, .001, 1000), ("tolerance", 2, 0, .5)):
            values = door[field]
            if not isinstance(values, list) or len(values) != size:
                raise ValueError("Invalid image geometry.")
            for value in values:
                number(value, low, high)
        if min(door["region"][2:]) <= 0 or door["zoom"][0] > door["zoom"][1]:
            raise ValueError("Invalid image geometry.")
        sequence(door["sequence"], VIEWER_KEYS)
    return data


def number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError("Numeric setting outside supported range.")


def sequence(value, supported):
    if not isinstance(value, list) or not 1 <= len(value) <= 64 or any(
        not isinstance(k, str) or key_name(k) not in supported for k in value
    ):
        raise ValueError("Sequence contains an unsupported key for this input context.")


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
