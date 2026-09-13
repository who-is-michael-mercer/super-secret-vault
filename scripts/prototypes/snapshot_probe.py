"""Measure real encrypted PNG commits using disposable files only."""

import json
import os
from pathlib import Path
import struct
import tempfile
import time
import zlib
from relayvault.vault import capsule, png, store
from relayvault.vault.session import VaultSession

for mib in (1, 100, 1023):
    with tempfile.TemporaryDirectory(prefix="relay-snapshot-probe-") as directory:
        root = Path(directory)
        os.environ["RELAY_HOME"] = str(root / "state")
        image = root / "image.png"
        with image.open("wb") as output:
            output.write(png.SIGNATURE)
            png.write_chunk(
                output, b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            )
            png.write_chunk(output, b"IDAT", zlib.compress(b"\0\x12\x34\x56"))
            png.write_chunk(output, b"IEND", b"")
        source = root / "source"
        with source.open("wb") as output:
            for _ in range(mib):
                output.write(bytes(1024 * 1024))
        header, key = capsule.metadata("probe-password")
        path = root / "carrier.png"
        store.create(path, header, bytes(key), image=image)
        key[:] = bytes(len(key))
        with VaultSession.authenticate("probe-password", path) as session:
            start = time.monotonic()
            session.store(source)
            stored = time.monotonic() - start
            start = time.monotonic()
            session.rename("source", "renamed")
            renamed = time.monotonic() - start
            session.verify()
        print(
            json.dumps(
                dict(
                    payload_mib=mib,
                    store_seconds=round(stored, 3),
                    rename_with_backup_seconds=round(renamed, 3),
                )
            ),
            flush=True,
        )
