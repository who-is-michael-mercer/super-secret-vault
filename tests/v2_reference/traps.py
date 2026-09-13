"""Fictional traps with explicitly gated, optional OS actions."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone

from . import os_actions
from .config import (
    AppConfig, AppPaths, ConfigError, load_runtime_state, save_runtime_state_atomic,
    validate_config,
)
from .terminal import Terminal


class TrapError(ValueError):
    """A trap request is invalid or its cooldown could not be persisted."""


@dataclass(frozen=True)
class TrapAction:
    kind: str
    value: int | float | None = None


@dataclass(frozen=True)
class TrapDefinition:
    id: str
    actions: tuple[TrapAction, ...]


@dataclass(frozen=True)
class TrapResult:
    exit_program: bool = False
    new_level: str | None = None
    cooldown_seconds: int = 0


TRAPS = {
    "signal_scramble": TrapDefinition("signal_scramble", (
        TrapAction("scramble"), TrapAction("clear"),
    )),
    "false_probe": TrapDefinition("false_probe", (
        TrapAction("fake_corruption"), TrapAction("progress", 0.35), TrapAction("reset_level"),
    )),
    "red_purge": TrapDefinition("red_purge", (
        TrapAction("progress", 0.3), TrapAction("fake_file_deletion"),
        TrapAction("fake_purge"), TrapAction("clear"), TrapAction("exit_program"),
    )),
    "seal_lockout": TrapDefinition("seal_lockout", (
        TrapAction("fake_corruption"), TrapAction("progress", 0.3),
        TrapAction("cooldown", 10), TrapAction("exit_program"),
    )),
    "auth_lockout": TrapDefinition("auth_lockout", (
        TrapAction("fake_corruption"), TrapAction("progress", 0.3),
        TrapAction("cooldown", 30), TrapAction("exit_program"),
    )),
}


def dispatch_trap(
    trap_id: str,
    terminal: Terminal,
    config: AppConfig,
    paths: AppPaths,
    *,
    reset_level: Callable[[], str | None] | None = None,
    move_backward: Callable[[], str | None] | None = None,
    lock_vault: Callable[[], None] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> TrapResult:
    """Run ordered fake actions; the caller owns game/session state and exits.

    Reset/back callbacks may return a level ID, or None after mutating their
    own game object. A missing callback is a no-op. The clock must be aware.
    Explicitly enabled, bound, allowlisted OS actions run after all fake actions.
    """
    try:
        definition = TRAPS[trap_id]
    except (KeyError, TypeError) as exc:
        raise TrapError(f"Unknown trap: {trap_id}") from exc
    config = validate_config({
        key: value for key, value in asdict(config).items() if value is not None
    })
    settings = config.traps or {}
    if not settings.get("enabled", True) or trap_id in settings.get("disabled_traps", []):
        return TrapResult()
    result = TrapResult()
    for action in definition.actions:
        if action.kind in {"countdown", "progress", "cooldown"} and (
            type(action.value) not in ((int, float) if action.kind == "progress" else (int,))
            or not 0 <= action.value < float("inf")
        ):
            raise TrapError(f"{action.kind} requires finite nonnegative seconds (integer for timers).")
        if action.kind == "scramble":
            terminal.scramble_text("relay0: carrier degraded")
        elif action.kind == "clear":
            terminal.clear()
        elif action.kind == "fake_corruption":
            terminal.fake_system_messages((
                "route: rejected", "archive0: metadata mismatch", "mount: remounted ro",
            ))
        elif action.kind == "fake_file_deletion":
            terminal.fake_system_messages(("journal: dropping scratch_07.idx", "journal: dropping mux_cache.bin"))
        elif action.kind == "fake_purge":
            terminal.fake_system_messages(("red: journal detached",))
        elif action.kind == "fake_shutdown":
            terminal.fake_system_messages(("relay0: shutdown simulation", "relay0: simulated carrier halt"))
        elif action.kind == "progress":
            terminal.progress("route: recovering" if trap_id == "false_probe"
                              else "relay0: disconnect pending", action.value)
        elif action.kind == "countdown":
            terminal.countdown(action.value, prefix="relay0: timer ")
        elif action.kind == "reset_level":
            if reset_level is not None:
                result = replace(result, new_level=reset_level())
        elif action.kind == "move_backward":
            if move_backward is not None:
                result = replace(result, new_level=move_backward())
        elif action.kind == "lock_vault":
            if lock_vault is not None:
                lock_vault()
        elif action.kind == "cooldown":
            try:
                state = load_runtime_state(paths)
                instant = now()
                if instant.utcoffset() is None:
                    raise ConfigError("Cooldown clock must include a timezone.")
                until = instant.astimezone(timezone.utc) + timedelta(seconds=action.value)
                save_runtime_state_atomic(paths, replace(state, cooldown_until=until.isoformat()))
            except (OSError, ConfigError) as exc:
                raise TrapError(f"Cannot persist cooldown: {exc}") from exc
            terminal.fake_system_messages((f"relay0: backoff {action.value}s",))
            result = replace(result, cooldown_seconds=action.value)
        elif action.kind == "exit_program":
            result = replace(result, exit_program=True)
        else:
            raise TrapError(f"Unknown trap action: {action.kind}")
    real_actions = config.real_os_actions or {}
    if real_actions.get("enabled", False):
        bound_action = real_actions.get("bindings", {}).get(trap_id)
        if bound_action is not None and bound_action in real_actions.get("allowed_actions", []):
            if bound_action not in {"close_terminal", "logout", "reboot", "shutdown"}:
                raise os_actions.UnsupportedActionError(f"Unsupported OS action: {bound_action}")
            os_actions.perform_os_action(bound_action)
    return result
