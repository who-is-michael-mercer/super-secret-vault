"""Explicit development session; only the latest aggregate observation is retained.

No Relay launch. No keyboard devices, clipboard or desktop inspection. Ctrl+C
stops only the child viewer created by this script. Use disposable images only.
"""

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


def fixture(path, width=800, height=600, variant=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(
            ">I", zlib.crc32(kind + data)
        )

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            grid = x % 100 < 2 or y % 100 < 2
            center = abs(x - width // 2) < 4 or abs(y - height // 2) < 4
            rows.extend((220, 140, 40) if center else
                        (100, 120, 140) if grid else (28 + variant * 30, 40, 52))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    directory = args.directory or Path(tempfile.mkdtemp(prefix="relay-imv-probe-"))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = directory.resolve()
    config = directory / "imv.conf"
    config.write_text("""[options]
suppress_default_binds = true
[binds]
q = quit
z = zoom 1
x = zoom -1
h = pan 30 0
l = pan -30 0
j = pan 0 -30
k = pan 0 30
r = reset
f = fullscreen
""")
    image = directory / "grid.png"
    fixture(image)
    env = os.environ | {
        "imv_config": str(config),
        "RELAY_IMV_PROBE": str(image),
        "RELAY_IMV_REGION": "350 250 100 100 0.1 20 0.12 0.12",
    }
    # Caller must choose the display explicitly for automated input tests.
    with (directory / "viewer-errors.txt").open("w") as errors:
        process = subprocess.Popen(
            [str(args.binary.resolve()), str(image)], env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
            text=True,
        )
        print(json.dumps({"pid": process.pid, "directory": str(directory)}), flush=True)
        try:
            for line in process.stdout:
                if not line.startswith("{"):
                    continue
                state = json.loads(line)
                temporary = directory / "latest.tmp"
                temporary.write_text(json.dumps(state, indent=2) + "\n")
                temporary.replace(directory / "latest.json")
            return process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
