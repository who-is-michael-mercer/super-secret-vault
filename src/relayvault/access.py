"""Small access procedure, independent of cryptographic state."""

from dataclasses import dataclass
from enum import Enum, auto
from .topology import RESOURCES, PROMPTS


class AccessState(Enum):
    COVER = auto()
    WAKING = auto()
    ROUTE = auto()
    AUTHENTICATING = auto()
    UNLOCKED = auto()


@dataclass
class AccessResult:
    message: str = ""
    action: str = ""


class AccessController:
    def __init__(self):
        self.node = "link"

    @property
    def prompt(self):
        return PROMPTS[self.node]

    def handle(self, command):
        name, args = command.name, command.args
        if not name:
            return AccessResult()
        if not args and name in {"sleep", "exit", "clear"}:
            return AccessResult(action=name)
        if name == "attach" and args == ("13",) and self.node == "link":
            self.node = "control"
            return AccessResult("sealctl: channel attached")
        if name == "unlock" and not args and self.node == "control":
            return AccessResult(action="authenticate")
        if name == "attach" and args == ("diagnostics",) and self.node == "link":
            self.node = "diagnostics"
            return AccessResult("telemetry: retained")
        if name == "back" and not args:
            self.node = "link"
            return AccessResult("link: local")
        if name == "ls" and not args:
            return AccessResult("  ".join(RESOURCES[self.node]))
        if name == "cat" and len(args) == 1 and args[0] in RESOURCES[self.node]:
            return AccessResult(RESOURCES[self.node][args[0]])
        if name == "status" and not args:
            return AccessResult("transport: local\nchannel: " + self.node)
        if name == "reset" and args == ("channel",):
            self.node = "link"
            return AccessResult(action="incident")
        return AccessResult("command: unavailable")
