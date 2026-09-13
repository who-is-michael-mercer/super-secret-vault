import io
import os
import pty
import select
import termios
import threading
import time
import pytest
from relayvault.input import Key, KeyDecoder, WakeMatcher, TTYInput, InputTimeout
from relayvault.settings import DEFAULT_WAKE
from relayvault.access import AccessController
from relayvault.parser import parse_command


def test_fragmented_keys_unicode_and_unknown_escape():
    d = KeyDecoder()
    assert d.feed(b"\x1b[") == []
    assert d.feed(b"A") == [Key("UP")]
    assert d.feed("é".encode()[:1]) == []
    assert d.feed("é".encode()[1:]) == [Key("CHAR", "é")]
    assert d.feed(b"\x1b[99~") == [Key("UNKNOWN")]
    assert d.feed(b"x") == [Key("CHAR", "x")]


def test_paste_fragmentation_bounded_and_not_wake():
    d = KeyDecoder()
    assert d.feed(b"\x1b[200~relay\x1b[20") == []
    assert d.feed(b"1~") == [Key("PASTE", "relay")]
    d.feed(b"\x1b[200~" + b"x" * 100000)
    assert d.feed(b"\x1b[201~") == [Key("PASTE_OVERFLOW")]
    m = WakeMatcher(("relay",))
    assert not m.feed(Key("PASTE", "relay"))


def test_overlap_timeout_and_default_wake():
    m = WakeMatcher(("a", "a", "b"))
    assert not m.feed(Key("CHAR", "a"), 0)
    assert not m.feed(Key("CHAR", "a"), 1)
    assert not m.feed(Key("CHAR", "a"), 2)
    assert m.feed(Key("CHAR", "b"), 3)
    m.feed(Key("CHAR", "a"), 4)
    assert not m.feed(Key("CHAR", "a"), 10)
    assert not m.feed(Key("CHAR", "b"), 11)
    m = WakeMatcher(DEFAULT_WAKE)
    for token in DEFAULT_WAKE[:-1]:
        assert not m.feed(Key(token) if len(token) > 1 else Key("CHAR", token))
    assert m.feed(Key(DEFAULT_WAKE[-1]))


def test_escape_expiry_drops_fragment():
    d = KeyDecoder()
    d.feed(b"\x1b[", now=0)
    assert d.expire(0.1) == [Key("UNKNOWN")]
    assert d.feed(b"x") == [Key("CHAR", "x")]


@pytest.fixture
def tty_pair():
    master, slave = pty.openpty()
    input_stream = os.fdopen(os.dup(slave), "r", buffering=1)
    output = os.fdopen(os.dup(slave), "w", buffering=1)
    original = termios.tcgetattr(slave)
    yield master, slave, input_stream, output, original
    input_stream.close()
    output.close()
    os.close(master)
    os.close(slave)


def drain(master):
    data = b""
    while select.select([master], [], [], 0)[0]:
        data += os.read(master, 65536)
    return data


def test_tty_silent_wake_and_restore_even_exception(tty_pair):
    master, slave, ins, outs, original = tty_pair
    with pytest.raises(RuntimeError):
        with TTYInput(ins, outs) as keyboard:
            drain(master)
            assert not termios.tcgetattr(slave)[3] & termios.ECHO
            os.write(master, b"wrong")
            assert keyboard.poll().text == "w"
            assert b"wrong" not in drain(master)
            raise RuntimeError("exit")
    assert termios.tcgetattr(slave) == original
    assert b"\x1b[?1049l" in drain(master)


def test_boundary_removes_queue_os_bytes_and_partial_escape(tty_pair):
    master, slave, ins, outs, _ = tty_pair
    with TTYInput(ins, outs) as keyboard:
        os.write(master, b"old\x1b[")
        assert keyboard.poll().text == "o"
        keyboard.boundary()
        assert keyboard.poll(0.01) is None
        os.write(master, b"new")
        assert "".join(keyboard.poll().text for _ in range(3)) == "new"


def test_password_paste_requires_enter_and_never_echoes(tty_pair):
    master, slave, ins, outs, _ = tty_pair
    result = []
    with TTYInput(ins, outs) as keyboard:
        thread = threading.Thread(
            target=lambda: result.append(keyboard.read_line("password: ", secret=True))
        )
        thread.start()
        os.write(master, b"\x1b[200~SECRET\n\x1b[201~")
        time.sleep(0.04)
        assert result == []
        os.write(master, b"\r")
        thread.join(1)
        assert not thread.is_alive() and result == ["SECRET\n"]
        assert b"SECRET" not in drain(master)


def test_idle_read_redraw_breaks_without_more_input(tty_pair):
    _, _, ins, outs, _ = tty_pair
    with TTYInput(ins, outs) as keyboard:
        start = time.monotonic()
        with pytest.raises(InputTimeout):
            keyboard.read_line(
                "vault> ", expired=lambda: time.monotonic() - start > 0.01
            )
        assert time.monotonic() - start < 0.25


def test_eof_in_queued_batch_is_not_ignored(tty_pair):
    master, _, ins, outs, _ = tty_pair
    with TTYInput(ins, outs) as keyboard:
        os.write(master, b"x\x04")
        assert keyboard.poll().text == "x"
        with pytest.raises(EOFError):
            keyboard.poll()


def test_two_commands_no_discovery_and_no_shell(tmp_path):
    controller = AccessController()
    assert controller.handle(parse_command("attach 13")).message
    assert controller.handle(parse_command("unlock")).action == "authenticate"
    for command in ("$(touch /tmp/nope)", "cat /etc/passwd", "ls /", "attach 03"):
        assert (
            controller.handle(parse_command(command)).message == "command: unavailable"
        )
