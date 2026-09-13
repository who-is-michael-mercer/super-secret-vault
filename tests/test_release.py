"""Independent decoder acceptance using disposable generated carriers."""

import io
import shutil
import subprocess
import pytest
from relayvault.vault import capsule, store
from test_carrier import image_bytes


@pytest.mark.parametrize("decoder", ["magick", "ffmpeg"])
def test_production_carrier_decodes_original_pixels(tmp_path, monkeypatch, decoder):
    if not shutil.which(decoder):
        pytest.skip(f"{decoder} is not installed; run release decoder checks on Linux")
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "home"))
    image = tmp_path / "source.png"
    image.write_bytes(image_bytes())
    header, key = capsule.metadata("decoder-password")
    target = tmp_path / "carrier.png"
    store.create(target, header, bytes(key), image=image)
    command = (
        [decoder, str(target), "-depth", "8", "rgb:-"]
        if decoder == "magick"
        else [
            decoder,
            "-v",
            "error",
            "-i",
            str(target),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
    )
    result = subprocess.run(command, capture_output=True, timeout=10)
    assert result.returncode == 0 and result.stdout == b"\x12\x34\x56"
