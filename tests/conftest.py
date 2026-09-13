"""Test-process backstop: machine actions may never reach a real executor."""

import os
import sys


def audit(event, args):
    if event == "os.system":
        raise RuntimeError("Tests may not execute shell commands.")
    if event == "subprocess.Popen":
        executable = os.path.basename(os.fsdecode(args[0]))
        if executable in {
            "systemctl",
            "loginctl",
            "kitten",
            "kitty",
            "reboot",
            "shutdown",
            "poweroff",
            "halt",
        }:
            raise RuntimeError("Real machine actions are forbidden in automated tests.")


sys.addaudithook(audit)
