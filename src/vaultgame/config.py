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
    """Optional sections retain legacy schema-only configuration when absent."""

    schema_version: int = 1
    traps: dict | None = None
    real_os_actions: dict | None = None
    vault_id: str | None = None


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
    if not isinstance(data, dict) or not set(data) <= {"schema_version", "traps", "real_os_actions", "vault_id"}:
        raise ConfigError("Configuration contains unsupported fields.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ConfigError("Configuration schema_version must be the integer 1.")
    if "vault_id" in data:
        vault_id = data["vault_id"]
        if not isinstance(vault_id, str) or not vault_id or ":" in vault_id:
            raise ConfigError("vault_id must be nonempty delimiter-free UTF-8 text.")
        try:
            vault_id.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConfigError("vault_id must be valid UTF-8 text.") from exc
    for name, list_key, allowed in (
        ("traps", "disabled_traps", {"enabled", "disabled_traps"}),
        ("real_os_actions", "allowed_actions", {"enabled", "allowed_actions", "bindings"}),
    ):
        if name not in data:
            continue
        section = data[name]
        if not isinstance(section, dict) or not set(section) <= allowed:
            raise ConfigError(f"{name} must be an object with supported fields.")
        if "enabled" in section and type(section["enabled"]) is not bool:
            raise ConfigError(f"{name}.enabled must be a boolean.")
        values = section.get(list_key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ConfigError(f"{name}.{list_key} must be a list of strings.")
        if name == "real_os_actions":
            bindings = section.get("bindings", {})
            if not isinstance(bindings, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in bindings.items()
            ):
                raise ConfigError("real_os_actions.bindings must map strings to strings.")
    return AppConfig(
        schema_version=1, traps=data.get("traps"), real_os_actions=data.get("real_os_actions"),
        vault_id=data.get("vault_id"),
    )


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot load JSON from {path}: {exc}") from exc


def save_config_atomic(paths: AppPaths, config: AppConfig) -> None:
    data = {key: value for key, value in asdict(config).items() if value is not None}
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
