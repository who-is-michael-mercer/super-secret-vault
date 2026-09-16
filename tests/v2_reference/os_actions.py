"""Optional machine actions; callers must enforce explicit configuration gates."""

import os
import subprocess
import sys


class UnsupportedActionError(ValueError):
    """The action or its safe platform implementation is unavailable."""


class ActionNotAllowedError(RuntimeError):
    """The operating system could not complete the requested action."""


def close_terminal() -> None:
    """Best effort: close only the invoking local Kitty window, never a parent."""
    window_id = os.environ.get("KITTY_WINDOW_ID", "")
    if (
        sys.platform != "linux"
        or os.environ.get("TERM") != "xterm-kitty"
        or not (window_id.isascii() and window_id.isdecimal())
        or any(key in os.environ for key in (
            "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "TMUX", "STY",
            "KITTY_LISTEN_ON", "KITTY_RC_PASSWORD",
        ))
    ):
        raise UnsupportedActionError("Current terminal cannot be safely closed.")
    try:
        direct_tty = os.isatty(0) and os.isatty(1) and os.ttyname(0) == os.ttyname(1)
    except OSError as exc:
        raise UnsupportedActionError("Current terminal cannot be identified.") from exc
    if not direct_tty:
        raise UnsupportedActionError("Closing requires the same direct input/output terminal.")
    _run_linux(["/usr/bin/kitten", "@", "close-window", "--self"])


def logout() -> None:
    # loginctl's empty session ID means the caller's session, never an env value.
    _run_linux(["/usr/bin/loginctl", "--no-ask-password", "terminate-session", ""])


def reboot() -> None:
    _run_linux(["/usr/bin/systemctl", "--no-ask-password", "reboot"])


def shutdown() -> None:
    _run_linux(["/usr/bin/systemctl", "--no-ask-password", "poweroff"])


def _run_linux(command: list[str]) -> None:
    if sys.platform != "linux":
        raise UnsupportedActionError("OS actions are supported only on Linux.")
    try:
        subprocess.run(
            command, check=True, shell=False, timeout=10,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise UnsupportedActionError("Required platform executable is unavailable.") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ActionNotAllowedError("The operating system could not complete the action.") from exc


def perform_os_action(action_name: str) -> None:
    if action_name == "close_terminal":
        close_terminal()
    elif action_name == "logout":
        logout()
    elif action_name == "reboot":
        reboot()
    elif action_name == "shutdown":
        shutdown()
    else:
        raise UnsupportedActionError(f"Unsupported OS action: {action_name}")
