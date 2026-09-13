"""Neutral diagnostics; no capsule inspection, decryption or vault disclosure."""

import os
from pathlib import Path
import platform
import shutil
import stat


def display(text):
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


def render(terminal, path=None):
    width = shutil.get_terminal_size((80, 24)).columns
    label = "none"
    size = "—"
    media = "—"
    if path is not None:
        selected = Path(path)
        label = display(selected.name)
        try:
            info = selected.lstat()
            if stat.S_ISREG(info.st_mode):
                size = f"{info.st_size:,} bytes"
                media = (
                    "image/png" if selected.suffix.lower() == ".png" else "local file"
                )
        except OSError:
            size = "unavailable"
    try:
        uptime = f'{int(float(Path("/proc/uptime").read_text().split()[0]))//60} min'
    except (OSError, ValueError):
        uptime = "—"
    lines = [
        "   .--------------.",
        "===|   ·  ──  ·   |===",
        "   \u0027------||------\u0027",
        "",
        "relay / 3.0",
        "--------------------------",
        f"system     {display(platform.system())} {display(platform.release())}",
        f"uptime     {uptime}",
        "transport  local",
        "signal     · standby",
        "",
        f"carrier    {label}",
        f"media      {media}",
        f"extent     {size}",
    ]
    for line in lines:
        terminal.print(line[: max(1, width - 1)])
