"""Pre-auth diagnostics: public configuration and opaque directory counts only."""

import math
import os
import platform
import re
import stat
from datetime import datetime, timezone

from .config import is_initialized, load_runtime_state


SCHEMATIC = r"""       .----------------------.
       |  +----------------+  |
   ====|==| o            o |==|====
       |  |    .------.    |  |
       |  |   /  .--.  \   |  |
   ----|--|--(---+--+---)--|--|----
       |  |   \  '--'  /   |  |
       |  |    '------'    |  |
   ====|==| o            o |==|====
       |  +----------------+  |
       '----------||----------'
                  ||
             [ interlock ]"""


def opaque_object_count(paths):
    """Count regular UUID object envelopes, never open one or follow links."""
    try:
        for directory in (paths.home, paths.vault_dir, paths.objects_dir):
            if not stat.S_ISDIR(directory.lstat().st_mode):
                return "unavailable"
        with os.scandir(paths.objects_dir) as entries:
            return str(sum(bool(re.fullmatch(r"[0-9a-f]{32}\.vlt", entry.name))
                           and entry.is_file(follow_symlinks=False) for entry in entries)).zfill(2)
    except FileNotFoundError:
        return "00"
    except OSError:
        return "unavailable"


def render_dashboard(terminal, paths, config=None, *, now=None):
    initialized = is_initialized(paths)
    state = load_runtime_state(paths)
    remaining = 0
    if state.cooldown_until:
        instant = datetime.now(timezone.utc) if now is None else now
        remaining = max(0, math.ceil((datetime.fromisoformat(state.cooldown_until) - instant).total_seconds()))
    fields = [
        "relay", "------------------------------",
        "node       :: relay0", "carrier    :: detected", "route      :: unresolved",
        "archive    :: sealed" if initialized else "archive    :: offline",
        "", "system", "------------------------------",
        f"runtime    :: python {platform.python_version()}",
        f"cipher     :: {config.encryption['algorithm'].lower() if config and config.encryption else 'aes-256-gcm'}",
        "kdf        :: argon2id",
        f"vault      :: {'initialized' if initialized else 'uninitialized'}",
        f"objects    :: {opaque_object_count(paths)}", "session    :: locked",
        f"cooldown   :: {str(remaining) + 's' if remaining else 'clear'}",
    ]
    art = SCHEMATIC.splitlines()
    if terminal.width < max(map(len, art)):
        art = ["  +-----------+", "==|  (--+--)  |==", "  +-----||----+", "     [ seal ]"]
    art_width = max(map(len, art))
    if terminal.width >= art_width + 4 + max(map(len, fields)):
        for index in range(max(len(art), len(fields))):
            left = art[index] if index < len(art) else ""
            right = fields[index] if index < len(fields) else ""
            terminal.print(terminal.styled(left.ljust(art_width)) + "    " + right)
    else:
        for line in art:
            terminal.print(line, style="accent")
        terminal.print()
        for line in fields:
            terminal.print(line)
    terminal.print()
