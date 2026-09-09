"""Application paths and validated, atomic JSON persistence."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path


class ConfigError(ValueError):
    """Configuration or runtime-state data is missing or malformed."""


@dataclass(frozen=True)
class AppPaths:
    home: Path
    config_path: Path
    state_path: Path
    vault_dir: Path
    manifest_path: Path
    objects_dir: Path


@dataclass
class AppConfig:
    schema_version: int = 1


@dataclass
class RuntimeState:
    cooldown_until: str | None = None


def resolve_paths(home_override=None) -> AppPaths:
    if home_override is None:
        home_override = os.environ.get("VAULTGAME_HOME")
    if home_override is None:
        home_override = Path.home() / ".relayvault"
    home = Path(home_override).expanduser().resolve()
    vault_dir = home / "vault"
    return AppPaths(
        home=home,
        config_path=home / "config.json",
        state_path=home / "state.json",
        vault_dir=vault_dir,
        manifest_path=vault_dir / "manifest.vlt",
        objects_dir=vault_dir / "objects",
    )


def load_config(paths: AppPaths) -> AppConfig:
    try:
        return validate_config(_load_json(paths.config_path))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration is missing: {paths.config_path}") from exc


def ensure_runtime_directories(paths: AppPaths) -> None:
    for directory in (paths.home, paths.vault_dir, paths.objects_dir):
        directory.mkdir(parents=True, exist_ok=True)


def is_initialized(paths: AppPaths) -> bool:
    """Check the expected runtime layout, without validating encrypted contents."""
    return all(
        directory.is_dir() for directory in (paths.home, paths.vault_dir, paths.objects_dir)
    ) and all(
        path.is_file() for path in (paths.config_path, paths.state_path, paths.manifest_path)
    )


def validate_config(data) -> AppConfig:
    if not isinstance(data, dict) or set(data) != {"schema_version"}:
        raise ConfigError("Configuration must contain only schema_version.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ConfigError("Configuration schema_version must be the integer 1.")
    return AppConfig(schema_version=1)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot load JSON from {path}: {exc}") from exc


def save_config_atomic(paths: AppPaths, config: AppConfig) -> None:
    data = asdict(config)
    validate_config(data)
    _save_json_atomic(paths.config_path, data)


def load_runtime_state(paths: AppPaths) -> RuntimeState:
    try:
        return _validate_runtime_state(_load_json(paths.state_path))
    except FileNotFoundError:
        return RuntimeState()


def _validate_runtime_state(data) -> RuntimeState:
    if not isinstance(data, dict) or not set(data) <= {"schema_version", "cooldown_until"}:
        raise ConfigError("Runtime state must contain schema_version and optional cooldown_until.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ConfigError("Runtime-state schema_version must be the integer 1.")
    cooldown = data.get("cooldown_until")
    if cooldown is not None:
        if not isinstance(cooldown, str):
            raise ConfigError("cooldown_until must be a UTC ISO timestamp or null.")
        try:
            timestamp = datetime.fromisoformat(cooldown)
        except ValueError as exc:
            raise ConfigError("cooldown_until must be a UTC ISO timestamp or null.") from exc
        if timestamp.utcoffset() != timedelta(0):
            raise ConfigError("cooldown_until must include the UTC timezone.")
    return RuntimeState(cooldown_until=cooldown)


def save_runtime_state_atomic(paths: AppPaths, state: RuntimeState) -> None:
    data = {"schema_version": 1, **asdict(state)}
    _validate_runtime_state(data)
    _save_json_atomic(paths.state_path, data)


def _save_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, indent=2, allow_nan=False)
            temporary.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
