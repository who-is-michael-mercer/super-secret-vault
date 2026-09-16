"""Actual viewer tests on the selected Wayland display, with NO input synthesis.

Only launches disposable viewer windows and sends commands to their own imv IPC.
Does not query compositor windows, launch terminals, or exercise machine actions.
"""

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from run_probe import fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    binary = args.checkout.resolve() / "build/imv"
    message = args.checkout.resolve() / "build/imv-msg"
    results = {}
    with tempfile.TemporaryDirectory(prefix="relay-imv-wayland-") as root:
        root = Path(root)
        target, other = root / "grid.png", root / "other.png"
        fixture(target)
        fixture(other, variant=1)
        config = root / "imv.conf"
        config.write_text("[options]\nsuppress_default_binds = true\n")
        env = os.environ | {
            "imv_config": str(config), "RELAY_IMV_PROBE": str(target),
            "RELAY_IMV_REGION": "350 250 100 100 0.9 1.1 0.12 0.12",
        }
        events = queue.Queue()
        process = subprocess.Popen([str(binary), str(target), str(other)], env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)

        def read():
            for line in process.stdout:
                if line.startswith("{"):
                    events.put(json.loads(line))

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def wait(predicate, timeout=6):
            deadline = time.monotonic() + timeout
            last = None
            while time.monotonic() < deadline:
                try:
                    last = events.get(timeout=max(.01, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if predicate(last):
                    return last
            raise AssertionError(f"viewer condition timed out; last observation: {last}")

        def command(text):
            while not events.empty():
                events.get_nowait()
            subprocess.run([str(message), str(process.pid), text], check=True,
                           capture_output=True, env=env)

        def record(label, state):
            # Only state, never ordered input: this harness does not send keys.
            results[label] = {k: v for k, v in state.items() if k != "keys"}
            print("PASS", label, flush=True)

        extra = None
        try:
            initial = wait(lambda s: s["file_ok"] and s["focus"] and not s["pending_draw"])
            record("native_wayland_load_and_focus", initial)
            command("zoom actual")
            normal = wait(lambda s: s["eligible"])
            record("eligible_at_actual_scale", normal)
            command("zoom 30")
            record("wrong_zoom", wait(lambda s: s["zoom"] > 1.1 and not s["eligible"]))
            command("zoom actual")
            wait(lambda s: s["eligible"])
            command("pan 500 0")
            record("wrong_viewport", wait(lambda s: not s["eligible"] and s["origin"] != normal["origin"]))
            command("center")
            wait(lambda s: s["eligible"])
            command("rotate to 90")
            record("rotation_rejected", wait(lambda s: s["rotation"] == 90 and not s["eligible"]))
            command("rotate to 0")
            wait(lambda s: s["eligible"])
            command("flip horizontal")
            record("mirror_rejected", wait(lambda s: s["mirror"] and not s["eligible"]))
            command("flip horizontal")
            wait(lambda s: s["eligible"])
            command("fullscreen")
            resized = wait(lambda s: s["window"] != normal["window"] and not s["pending_draw"])
            record("window_framebuffer_resize", resized)
            command("fullscreen")
            wait(lambda s: s["window"] == normal["window"])
            # A second ordinary viewer changes focus without compositor inspection.
            extra = subprocess.Popen([str(binary), str(other)],
                                     env=env | {"RELAY_IMV_PROBE": ""},
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            record("focus_leave", wait(lambda s: not s["focus"] and not s["eligible"]))
            extra.terminate(); extra.wait(timeout=5); extra = None
            record("focus_reenter", wait(lambda s: s["focus"]))
            command("goto 2")
            record("other_image", wait(lambda s: s["generation"] > initial["generation"] and not s["file_ok"]))
            command("goto 1")
            before = wait(lambda s: s["file_ok"])
            # Preserve mtime to expose upstream's coarse automatic-reload check.
            stamp = target.stat()
            replacement = root / "new.png"
            fixture(replacement, variant=2)
            os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            replacement.replace(target)
            stale = wait(lambda s: not s["file_ok"])
            assert stale["loaded_inode"] == before["loaded_inode"]
            record("replacement_rejects_stale_display", stale)
            command("goto 2")
            wait(lambda s: s["generation"] > stale["generation"])
            command("goto 1")
            fresh = wait(lambda s: s["file_ok"])
            assert fresh["loaded_inode"] == target.stat().st_ino
            assert fresh["loaded_inode"] != before["loaded_inode"]
            record("explicit_reload_binds_new_inode", fresh)
            assert bytes.fromhex(fresh["loaded_path_hex"]).decode() == str(target)
            # No user keys should have been synthesized by this test.
            results["input_synthesis"] = False
        finally:
            if extra is not None and extra.poll() is None:
                extra.terminate(); extra.wait(timeout=5)
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)
            reader.join(timeout=2)
            results["viewer_stderr"] = process.stderr.read()
            args.report.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
