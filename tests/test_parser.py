import ast
import builtins
import os
from pathlib import Path
import subprocess

import pytest

from vaultgame import parser
from vaultgame.parser import CommandParseError, ParsedCommand, parse_command


def test_command_with_no_arguments():
    command = parse_command("scan")

    assert isinstance(command, ParsedCommand)
    assert command.name == "scan"
    assert command.args == ()
    assert command.raw == "scan"


@pytest.mark.parametrize("line", ["", " \t\n "])
def test_empty_input_returns_no_op(line):
    assert parse_command(line) == ParsedCommand(name="", args=(), raw=line)


@pytest.mark.parametrize("line", ['read "unfinished', "read 'unfinished", "read trailing\\"])
def test_malformed_quoting_raises_controlled_error(line):
    with pytest.raises(CommandParseError) as error:
        parse_command(line)

    assert str(error.value)


@pytest.mark.parametrize(
    ("line", "name", "args"),
    [
        ("probe 13", "probe", ("13",)),
        ("move North EAST", "move", ("North", "EAST")),
        ("ENTER NULL", "enter", ("NULL",)),
        (" \t InSpEcT  MixedCase\tUPPER  \n", "inspect", ("MixedCase", "UPPER")),
        ('store "/home/me/My Notes.txt" Notes.txt', "store", ("/home/me/My Notes.txt", "Notes.txt")),
        ('read "ARCHIVE INDEX"', "read", ("ARCHIVE INDEX",)),
        ("read 'ARCHIVE INDEX'", "read", ("ARCHIVE INDEX",)),
        (r"store /home/me/My\ Notes.txt Notes.txt", "store", ("/home/me/My Notes.txt", "Notes.txt")),
        (r'read "Say \"Hello\""', "read", ('Say "Hello"',)),
        (r"read 'Keep\Backslash'", "read", ("Keep\\Backslash",)),
        ('read "  Inner spacing  "', "read", ("  Inner spacing  ",)),
        ('read "" Tail', "read", ("", "Tail")),
        ('read pre"Mixed Case"post', "read", ("preMixed Casepost",)),
        ('open "red; reboot"', "open", ("red; reboot",)),
        ("open red; reboot", "open", ("red;", "reboot")),
        ('inspect "foo | cat /etc/passwd"', "inspect", ("foo | cat /etc/passwd",)),
        ("inspect foo | cat /etc/passwd", "inspect", ("foo", "|", "cat", "/etc/passwd")),
        ("read < Input.txt > Output.txt >> Append.txt", "read", ("<", "Input.txt", ">", "Output.txt", ">>", "Append.txt")),
        ('probe "$(shutdown now)"', "probe", ("$(shutdown now)",)),
        ("probe $(shutdown now)", "probe", ("$(shutdown", "now)")),
        ('probe "`reboot`"', "probe", ("`reboot`",)),
        ("read $HOME ${USER} ~/Notes *.txt && next &", "read", ("$HOME", "${USER}", "~/Notes", "*.txt", "&&", "next", "&")),
        ("read # NotAComment", "read", ("#", "NotAComment")),
        ("UNRECOGNIZED Arbitrary", "unrecognized", ("Arbitrary",)),
        ('read "Résumé Ω 🗝"', "read", ("Résumé Ω 🗝",)),
    ],
)
def test_tokenization_preserves_arguments_and_raw_input(line, name, args):
    command = parse_command(line)

    assert command.name == name
    assert command.args == args
    assert isinstance(command.args, tuple)
    assert command.raw == line


def test_parser_has_no_side_effects(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VAULTGAME_HOME", str(tmp_path / "runtime"))
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("Unchanged")
    environment = dict(os.environ)

    def forbidden_execution(*args, **kwargs):
        pytest.fail("Parser attempted execution")

    monkeypatch.setattr(os, "system", forbidden_execution)
    monkeypatch.setattr(subprocess, "Popen", forbidden_execution)
    monkeypatch.setattr(builtins, "eval", forbidden_execution)

    for line in (
        'probe "$(shutdown now)"',
        'open "red; reboot"',
        'inspect "foo | cat /etc/passwd"',
        "store data > generated.txt",
        "read $VAULTGAME_HOME *.txt",
        "unknown __import__('os').system('reboot')",
    ):
        assert parse_command(line).raw == line

    with pytest.raises(CommandParseError):
        parse_command('read "unfinished')

    assert list(tmp_path.iterdir()) == [sentinel]
    assert sentinel.read_text() == "Unchanged"
    assert dict(os.environ) == environment
    assert Path.cwd() == tmp_path
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_parser_has_no_execution_or_application_dependencies():
    tree = ast.parse(Path(parser.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in {"shlex", "typing"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in {"shlex", "typing"}
            assert node.level == 0
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__"}
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"eval", "exec", "system", "Popen"}
