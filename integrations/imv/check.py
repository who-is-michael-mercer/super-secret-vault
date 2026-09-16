"""Build and run the isolated C checks against the patched imv checkout."""

import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

from run_probe import fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    source = args.checkout.resolve()
    here = Path(__file__).resolve().parent
    flags = shlex.split(subprocess.check_output([
        "pkg-config", "--cflags", "--libs", "libpng", "pangocairo", "gl",
        "xkbcommon", "icu-uc", "inih",
    ], text=True))
    with tempfile.TemporaryDirectory(prefix="relay-imv-check-") as root:
        root = Path(root)
        for name in ("test_probe", "test_origin"):
            binary = root / name
            command = ["cc", "-std=c99", "-D_XOPEN_SOURCE=700", "-I",
                       str(source / "src"), str(here / f"{name}.c")]
            if name == "test_origin":
                command += [str(source / "build/libimv.a"), *flags, "-pthread"]
            subprocess.run([*command, "-lm", "-o", str(binary)], check=True)
            paths = []
            if name == "test_origin":
                for variant, label in enumerate(("original.png", "replacement.png")):
                    path = root / label
                    fixture(path, variant=variant)
                    paths.append(str(path))
            subprocess.run([str(binary), *paths], check=True)


if __name__ == "__main__":
    main()
