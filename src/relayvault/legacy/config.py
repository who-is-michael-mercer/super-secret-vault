"""Read-only legacy path and cryptographic metadata validation."""

import base64
import binascii
import math
import os
from dataclasses import dataclass, asdict
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
    kdf: dict | None = None
    encryption: dict | None = None
    key_check: dict | None = None
    auto_lock_seconds: float | None = None


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


def validate_config(data) -> AppConfig:
    if not isinstance(data, dict) or not set(data) <= {
        "schema_version",
        "traps",
        "real_os_actions",
        "vault_id",
        "kdf",
        "encryption",
        "key_check",
        "auto_lock_seconds",
    }:
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
        (
            "real_os_actions",
            "allowed_actions",
            {"enabled", "allowed_actions", "bindings"},
        ),
    ):
        if name not in data:
            continue
        section = data[name]
        if not isinstance(section, dict) or not set(section) <= allowed:
            raise ConfigError(f"{name} must be an object with supported fields.")
        if "enabled" in section and type(section["enabled"]) is not bool:
            raise ConfigError(f"{name}.enabled must be a boolean.")
        values = section.get(list_key, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise ConfigError(f"{name}.{list_key} must be a list of strings.")
        if name == "real_os_actions":
            bindings = section.get("bindings", {})
            if not isinstance(bindings, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in bindings.items()
            ):
                raise ConfigError(
                    "real_os_actions.bindings must map strings to strings."
                )
    if any(
        field in data
        for field in ("kdf", "encryption", "key_check", "auto_lock_seconds")
    ):
        _validate_initialized_fields(data)
    return AppConfig(
        schema_version=1,
        traps=data.get("traps"),
        real_os_actions=data.get("real_os_actions"),
        vault_id=data.get("vault_id"),
        kdf=data.get("kdf"),
        encryption=data.get("encryption"),
        key_check=data.get("key_check"),
        auto_lock_seconds=data.get("auto_lock_seconds"),
    )


def _binary_field(value, size=None):
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (AttributeError, UnicodeError, ValueError, binascii.Error) as error:
        raise ConfigError("Invalid base64 configuration field.") from error
    if size is not None and len(decoded) != size:
        raise ConfigError("Invalid binary configuration field length.")
    return decoded


def _validate_initialized_fields(data):
    required = {"vault_id", "kdf", "encryption", "key_check", "auto_lock_seconds"}
    if not required <= data.keys():
        raise ConfigError("Initialized vault configuration is incomplete.")
    kdf = data["kdf"]
    parameters = {"iterations": 3, "memory_kib": 65536, "lanes": 4, "length": 32}
    if (
        not isinstance(kdf, dict)
        or set(kdf) != {"salt", *parameters}
        or any(
            type(kdf[name]) is not int or kdf[name] != value
            for name, value in parameters.items()
        )
    ):
        raise ConfigError("Invalid version-1 Argon2id configuration.")
    _binary_field(kdf["salt"], 16)
    encryption = data["encryption"]
    if (
        not isinstance(encryption, dict)
        or encryption != {"algorithm": "AES-256-GCM", "format_version": 1}
        or type(encryption["format_version"]) is not int
    ):
        raise ConfigError("Invalid version-1 encryption configuration.")
    check = data["key_check"]
    if not isinstance(check, dict) or set(check) != {"nonce", "ciphertext"}:
        raise ConfigError("Invalid encrypted key check.")
    _binary_field(check["nonce"], 12)
    if len(_binary_field(check["ciphertext"])) < 16:
        raise ConfigError("Truncated encrypted key check.")
    timeout = data["auto_lock_seconds"]
    if (
        type(timeout) not in (int, float)
        or timeout <= 0
        or timeout > 1e308
        or not math.isfinite(timeout)
    ):
        raise ConfigError("auto_lock_seconds must be finite and positive.")


def validate_initialized_config(config: AppConfig) -> AppConfig:
    """Require the complete fixed-format configuration before authentication."""
    if not isinstance(config, AppConfig):
        raise ConfigError("Expected application configuration.")
    data = {key: value for key, value in asdict(config).items() if value is not None}
    validated = validate_config(data)
    _validate_initialized_fields(data)
    return validated
