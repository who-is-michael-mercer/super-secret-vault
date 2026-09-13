"""Tokenize internal commands without executing or validating them."""

import shlex
from typing import NamedTuple


class CommandParseError(ValueError):
    """An internal command contains malformed quoting or escaping."""


class ParsedCommand(NamedTuple):
    name: str
    args: tuple[str, ...]
    raw: str


def parse_command(line: str) -> ParsedCommand:
    """Preserve the input and split its command and arguments using POSIX quoting."""
    try:
        tokens = shlex.split(line.strip())
    except ValueError as error:
        raise CommandParseError(str(error)) from error
    if not tokens:
        return ParsedCommand("", (), line)
    return ParsedCommand(tokens[0].lower(), tuple(tokens[1:]), line)
