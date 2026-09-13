"""Fictional channel incidents and the sole optional machine-action boundary."""

from . import os_actions


def channel_reset(terminal, policy, *, armed=False, maintenance=False, session=None):
    if session is not None:
        # Wait for any in-flight operation before invoking a machine action.
        with session._operation_lock:
            session.lock()
    terminal.print("link: channel reset")
    if maintenance or not armed or not policy.get("enabled", False):
        return
    action = policy.get("bindings", {}).get("channel_reset")
    if action in {
        "logout",
        "reboot",
        "shutdown",
        "close_terminal",
    } and action in policy.get("allowed_actions", []):
        os_actions.perform_os_action(action)
