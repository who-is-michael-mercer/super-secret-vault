"""Single POSIX TTY owner: no echo, bounded decoding, state-boundary draining."""

from collections import deque
from dataclasses import dataclass
import os
import select
import signal
import sys
import termios
import threading
import time
import tty
import unicodedata


@dataclass(frozen=True)
class Key:
    kind: str
    text: str = ""


class KeyDecoder:
    sequences = {
        b"\x1b[A": "UP",
        b"\x1b[B": "DOWN",
        b"\x1b[C": "RIGHT",
        b"\x1b[D": "LEFT",
        b"\x1bOA": "UP",
        b"\x1bOB": "DOWN",
        b"\x1bOC": "RIGHT",
        b"\x1bOD": "LEFT",
        b"\x1b[200~": "PASTE_START",
    }

    def __init__(self):
        self.reset()

    def reset(self):
        self.buffer = b""
        self.paste = None
        self.overflow = False
        self.pending_since = None

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        self.buffer += data
        events = []
        while self.buffer:
            if self.paste is not None:
                end = self.buffer.find(b"\x1b[201~")
                if end < 0:
                    # Keep only a suffix which may be a split terminator.
                    keep = min(5, len(self.buffer))
                    fragment = self.buffer[:-keep] if keep else self.buffer
                    self.paste += fragment
                    self.buffer = self.buffer[-keep:] if keep else b""
                    if len(self.paste) > 8192:
                        self.overflow = True
                        self.paste = self.paste[:8192]
                    break
                self.paste += self.buffer[:end]
                events.append(
                    Key("PASTE_OVERFLOW")
                    if self.overflow or len(self.paste) > 8192
                    else Key("PASTE", self.paste.decode("utf-8", errors="replace"))
                )
                self.paste = None
                self.overflow = False
                self.buffer = self.buffer[end + 6 :]
                continue
            first = self.buffer[0]
            if first == 27:
                found = next(
                    (
                        (sequence, kind)
                        for sequence, kind in self.sequences.items()
                        if self.buffer.startswith(sequence)
                    ),
                    None,
                )
                if found:
                    sequence, kind = found
                    self.buffer = self.buffer[len(sequence) :]
                    if kind == "PASTE_START":
                        self.paste = b""
                    else:
                        events.append(Key(kind))
                    self.pending_since = None
                    continue
                if any(sequence.startswith(self.buffer) for sequence in self.sequences):
                    if self.pending_since is None:
                        self.pending_since = now
                    break
                # Consume whole unknown CSI rather than echoing its tail.
                if self.buffer.startswith(b"\x1b["):
                    end = next(
                        (
                            i
                            for i in range(2, len(self.buffer))
                            if 64 <= self.buffer[i] <= 126
                        ),
                        None,
                    )
                    if end is None:
                        if len(self.buffer) > 64:
                            self.buffer = b""
                        elif self.pending_since is None:
                            self.pending_since = now
                        break
                    self.buffer = self.buffer[end + 1 :]
                else:
                    self.buffer = self.buffer[1:]
                events.append(Key("UNKNOWN"))
                self.pending_since = None
                continue
            if first < 32 or first == 127:
                self.buffer = self.buffer[1:]
                kind = {
                    3: "INTERRUPT",
                    4: "EOF",
                    10: "ENTER",
                    13: "ENTER",
                    8: "BACKSPACE",
                    9: "TAB",
                    127: "BACKSPACE",
                    26: "SUSPEND",
                }.get(first, "UNKNOWN")
                events.append(Key(kind))
                continue
            count = (
                1
                if first < 128
                else (
                    2
                    if 0xC2 <= first <= 0xDF
                    else (
                        3
                        if 0xE0 <= first <= 0xEF
                        else 4 if 0xF0 <= first <= 0xF4 else 1
                    )
                )
            )
            if len(self.buffer) < count:
                if self.pending_since is None:
                    self.pending_since = now
                break
            raw = self.buffer[:count]
            self.buffer = self.buffer[count:]
            try:
                character = raw.decode("utf-8")
            except UnicodeError:
                events.append(Key("UNKNOWN"))
                continue
            if character.isprintable():
                events.append(Key("CHAR", character))
            self.pending_since = None
        if not self.buffer:
            self.pending_since = None
        return events

    def expire(self, now=None):
        now = time.monotonic() if now is None else now
        if (
            self.paste is None
            and self.pending_since is not None
            and now - self.pending_since >= 0.08
        ):
            self.buffer = b""
            self.pending_since = None
            return [Key("UNKNOWN")]
        return []


class WakeMatcher:
    def __init__(self, sequence, timeout=5):
        self.sequence = tuple(sequence)
        self.timeout = timeout
        self.partial = ()
        self.last = None

    def reset(self):
        self.partial = ()
        self.last = None

    def feed(self, key, now=None):
        now = time.monotonic() if now is None else now
        if self.last is not None and now - self.last >= self.timeout:
            self.partial = ()
        token = key.text if key.kind == "CHAR" else key.kind
        candidate = (*self.partial, token)
        self.last = now
        for length in range(min(len(candidate), len(self.sequence)), 0, -1):
            if candidate[-length:] == self.sequence[:length]:
                if length == len(self.sequence):
                    self.reset()
                    return True
                self.partial = candidate[-length:]
                return False
        self.partial = ()
        return False


class InputTimeout(Exception):
    pass


class TTYInput:
    def __init__(self, stream=None, output=None, *, alternate=True):
        self.stream = sys.stdin if stream is None else stream
        self.output = sys.stdout if output is None else output
        self.fd = self.stream.fileno()
        self.alternate = alternate
        self.decoder = KeyDecoder()
        self.queue = deque()
        self.previous = None
        self.handlers = {}
        self.resize = False
        self.suspended = False

    def _write(self, text):
        self.output.write(text)
        self.output.flush()

    def _enable(self):
        tty.setcbreak(self.fd, termios.TCSANOW)
        mode = termios.tcgetattr(self.fd)
        mode[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(self.fd, termios.TCSANOW, mode)
        self._write(("\x1b[?1049h" if self.alternate else "") + "\x1b[?2004h\x1b[?25l")

    def _restore(self):
        try:
            if self.previous is not None:
                termios.tcsetattr(self.fd, termios.TCSANOW, self.previous)
        finally:
            self._write(
                "\x1b[0m\x1b[?25h\x1b[?2004l"
                + ("\x1b[?1049l" if self.alternate else "")
            )

    def __enter__(self):
        if not self.stream.isatty() or not self.output.isatty():
            raise ValueError("Interactive access requires a terminal.")
        self.previous = termios.tcgetattr(self.fd)
        try:
            self._enable()
            if threading.current_thread() is threading.main_thread():
                for sig in (
                    signal.SIGWINCH,
                    signal.SIGTSTP,
                    signal.SIGHUP,
                    signal.SIGTERM,
                ):
                    self.handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, self._signal)
            self.boundary()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *_):
        try:
            self._restore()
        finally:
            for sig, handler in self.handlers.items():
                signal.signal(sig, handler)
            self.handlers.clear()
            self.decoder.reset()
            self.queue.clear()

    def _signal(self, sig, _):
        if sig == signal.SIGWINCH:
            self.resize = True
            return
        if sig in (signal.SIGHUP, signal.SIGTERM):
            raise EOFError()
        # Restore before stopping; re-enter only after the process is continued.
        self._restore()
        os.kill(os.getpid(), signal.SIGSTOP)
        self._enable()
        self.boundary()
        self.suspended = True

    def boundary(self):
        self.decoder.reset()
        self.queue.clear()
        termios.tcflush(self.fd, termios.TCIFLUSH)

    def poll(self, timeout=0.1):
        if self.suspended:
            self.suspended = False
            return Key("RESUME")
        if self.resize:
            self.resize = False
            return Key("RESIZE")
        self.queue.extend(self.decoder.expire())
        if not self.queue and select.select([self.fd], [], [], timeout)[0]:
            data = os.read(self.fd, 4096)
            if not data:
                raise EOFError()
            self.queue.extend(self.decoder.feed(data))
        if not self.queue:
            return None
        key = self.queue.popleft()
        if key.kind == "INTERRUPT":
            raise KeyboardInterrupt()
        if key.kind == "EOF":
            raise EOFError()
        return key

    def transition(self, effects=True):
        self.boundary()
        deadline = time.monotonic() + (0.25 if effects else 0)
        while time.monotonic() < deadline:
            self.poll(min(0.025, max(0, deadline - time.monotonic())))
        self.boundary()

    def read_line(self, prompt, *, secret=False, expired=lambda: False):
        self._write(prompt)
        text = ""
        cursor = 0
        if not secret:
            self._write("\x1b[?25h")

        def redraw():
            if not secret:

                def cells(value):
                    return sum(
                        (
                            0
                            if unicodedata.combining(c)
                            else (
                                2
                                if unicodedata.east_asian_width(c) in {"W", "F"}
                                else 1
                            )
                        )
                        for c in value
                    )

                columns = max(
                    8, os.get_terminal_size(self.output.fileno()).columns or 80
                )
                label = prompt
                while cells(label) > columns // 2:
                    label = label[1:]
                budget = max(1, columns - cells(label) - 1)
                start = cursor
                used = 0
                while start and used + cells(text[start - 1]) < budget:
                    start -= 1
                    used += cells(text[start])
                end = cursor
                while end < len(text) and cells(text[start : end + 1]) <= budget:
                    end += 1
                self._write("\r\x1b[2K" + label + text[start:end])
                backward = cells(text[cursor:end])
                if backward:
                    self._write(f"\x1b[{backward}D")

        try:
            while True:
                if expired():
                    self.boundary()
                    raise InputTimeout()
                key = self.poll()
                if key is None:
                    continue
                if key.kind == "RESUME":
                    self.boundary()
                    raise InputTimeout()
                if key.kind == "ENTER":
                    self._write("\n")
                    return text
                if key.kind == "RESIZE":
                    redraw()
                    continue
                if key.kind == "PASTE_OVERFLOW":
                    raise ValueError("Pasted input exceeds the input limit.")
                if key.kind == "CHAR":
                    insert = key.text
                elif key.kind == "TAB" and secret:
                    insert = "\t"
                elif key.kind == "PASTE":
                    # Password bytes are never normalized, trimmed or filtered.
                    insert = (
                        key.text
                        if secret
                        else "".join(
                            c for c in key.text.rstrip("\r\n") if c.isprintable()
                        )
                    )
                else:
                    insert = ""
                if insert:
                    if len(text) + len(insert) > 8192:
                        raise ValueError("Input exceeds the input limit.")
                    text = text[:cursor] + insert + text[cursor:]
                    cursor += len(insert)
                elif key.kind == "BACKSPACE" and cursor:
                    text = text[: cursor - 1] + text[cursor:]
                    cursor -= 1
                elif key.kind == "LEFT":
                    cursor = max(0, cursor - 1)
                elif key.kind == "RIGHT":
                    cursor = min(len(text), cursor + 1)
                redraw()
        finally:
            text = ""
            self._write("\x1b[?25l")
