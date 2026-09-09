"""In-memory puzzle progression; effects and authentication belong to the caller."""

from dataclasses import dataclass, field

from .levels import LEVELS, LevelDefinition
from .parser import ParsedCommand


@dataclass
class GameState:
    current_level: str = "dormant_relay"
    flags: set[str] = field(default_factory=set)
    consecutive_unknown_commands: int = 0


@dataclass(frozen=True)
class GameResult:
    """Text and requests for the caller; no effects execute in the game layer."""

    message: str = ""
    transition_to: str | None = None
    trap_id: str | None = None
    authentication_gate: bool = False
    clear: bool = False
    unknown: bool = False
    noop: bool = False


class GameEngine:
    def __init__(self) -> None:
        self.state = GameState()

    def current_level(self) -> LevelDefinition:
        return LEVELS[self.state.current_level]

    def render_intro(self, terminal) -> None:
        level = self.current_level()
        terminal.print(level.ascii_scene)
        for line in level.intro_lines:
            terminal.print(line)

    def available_commands(self) -> tuple[str, ...]:
        level = self.current_level()
        commands = list(level.visible_commands)
        # Only the flag-gated clues explicitly reveal a hidden command.
        # Requirement-free wake and the wrong-unlock fallback stay hidden.
        for rule in level.rules:
            if (rule.hidden and rule.requires_flags
                    and rule.requires_flags <= self.state.flags
                    and rule.command not in commands):
                commands.append(rule.command)
        return tuple(commands)

    def transition(self, level_id: str) -> GameResult:
        """Keep discoveries on navigation; the gate is a signal, not a sixth level."""
        if level_id == "authentication_gate":
            return GameResult(transition_to=level_id, authentication_gate=True)
        if level_id not in LEVELS:
            raise ValueError(f"Unknown level: {level_id}")
        self.state.current_level = level_id
        self.state.consecutive_unknown_commands = 0
        return GameResult(transition_to=level_id)

    def handle(self, parsed_command: ParsedCommand) -> GameResult:
        """Match exact parsed tokens; unavailable or invalid tuples count as unknown."""
        if not parsed_command.name and not parsed_command.args:
            return GameResult(noop=True)
        if parsed_command.name == "help" and not parsed_command.args:
            self.state.consecutive_unknown_commands = 0
            return GameResult(message="\n".join(self.available_commands()))
        if parsed_command.name == "clear" and not parsed_command.args:
            self.state.consecutive_unknown_commands = 0
            return GameResult(clear=True)
        if (parsed_command.name == "back" and not parsed_command.args
                and self.current_level().back_target is not None):
            return self.move_back()
        for rule in self.current_level().rules:
            if (rule.command == parsed_command.name
                    and (rule.args == parsed_command.args
                         or (rule.args is None and parsed_command.args))):
                if not rule.requires_flags <= self.state.flags:
                    # A blocked exact rule must not fall through to a trap.
                    break
                self.state.consecutive_unknown_commands = 0
                self.state.flags.update(rule.sets_flags)
                if rule.transition_to is not None:
                    return self.transition(rule.transition_to)
                return GameResult(message=rule.message, trap_id=rule.trap_id)
        self.state.consecutive_unknown_commands += 1
        trap_id = None
        if (self.state.current_level == "dormant_relay"
                and self.state.consecutive_unknown_commands >= 3):
            trap_id = "signal_scramble"
            self.state.consecutive_unknown_commands = 0
        return GameResult(message="Unknown command.", trap_id=trap_id, unknown=True)

    def move_back(self) -> GameResult:
        target = self.current_level().back_target
        if target is None:
            return GameResult(noop=True)
        return self.transition(target)

    def reset_current_level(self) -> None:
        """Forget flags acquired here, retaining discoveries in other levels."""
        for rule in self.current_level().rules:
            self.state.flags.difference_update(rule.sets_flags)
        self.state.consecutive_unknown_commands = 0

    def reset_game(self) -> None:
        self.state = GameState()
