"""Fetch the pinned imv revision and build the probe without installing anything.

Requires meson/ninja on PATH; the destination must not exist. Never modifies the
system viewer, desktop configuration, associations, Relay settings or vault data.
"""

import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    target = args.destination.absolute()
    if target.exists():
        parser.error("destination must not exist; use a fresh isolated checkout")
    here = Path(__file__).resolve().parent
    pin = json.loads((here / "upstream.json").read_text())
    subprocess.run(["git", "clone", "--no-checkout", pin["url"], str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", pin["revision"]], check=True)
    actual = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if actual != pin["revision"]:
        raise RuntimeError("upstream revision does not match the pin")
    subprocess.run(["git", "-C", str(target), "apply", "--check", str(here / "relay-probe.patch")], check=True)
    subprocess.run(["git", "-C", str(target), "apply", str(here / "relay-probe.patch")], check=True)
    subprocess.run([
        "meson", "setup", str(target / "build"), str(target),
        "-Dwindows=wayland", "-Dc_std=c11", "-Dauto_features=disabled", "-Dlibpng=enabled",
        "-Dtest=disabled", "-Dman=disabled",
    ], check=True)
    subprocess.run(["meson", "compile", "-C", str(target / "build")], check=True)
    print("Isolated probe:", target / "build/imv")


if __name__ == "__main__":
    main()
