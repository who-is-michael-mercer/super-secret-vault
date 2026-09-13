"""Disposable PNG compatibility and sequential-write probe; no personal files."""

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import zlib


def chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix="relay-probe-") as directory:
        root = Path(directory)
        prefix = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\x12\x34\x56"))
        )
        suffix = chunk(b"IEND", b"")
        for mib in (1, 100, 1024):
            path = root / "probe.png"
            start = time.monotonic()
            with path.open("wb") as output:
                output.write(prefix)
                for index in range(mib):
                    output.write(
                        chunk(
                            b"rvLt",
                            b"RLYP\1"
                            + bytes(16)
                            + struct.pack(">II", index, mib)
                            + bytes(1024 * 1024),
                        )
                    )
                output.write(suffix)
                output.flush()
                os.fsync(output.fileno())
            elapsed = time.monotonic() - start
            row = {"payload_mib": mib, "write_fsync_seconds": round(elapsed, 3)}
            for name, command in (
                ("imagemagick", ["magick", str(path), "-depth", "8", "rgb:-"]),
                (
                    "ffmpeg",
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        str(path),
                        "-f",
                        "rawvideo",
                        "-pix_fmt",
                        "rgb24",
                        "-",
                    ],
                ),
            ):
                started = time.monotonic()
                process = subprocess.run(command, capture_output=True, timeout=60)
                row[name] = {
                    "success": process.returncode == 0
                    and process.stdout == b"\x12\x34\x56",
                    "seconds": round(time.monotonic() - started, 3),
                    "error": process.stderr.decode(errors="replace")[:300],
                }
            results.append(row)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
