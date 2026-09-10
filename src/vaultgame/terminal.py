"""Standard-library terminal rendering with optional, injectable timing."""

import builtins
import os
import shutil
from contextlib import contextmanager, nullcontext
import random
import sys
import time
from collections.abc import Callable, Iterable
from types import TracebackType
from typing import Self, TextIO


class Terminal:
    """Render to a stream, animating only when effects and TTY allow it.

    Use ``with Terminal(...) as terminal`` to hide the cursor during a session
    and restore it and ANSI formatting on exit, including KeyboardInterrupt.
    Static mode writes final frames, completed progress and countdowns, and
    original text, without delays or generated ANSI controls.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        effects: bool = True,
        sleep: Callable[[float], None] = time.sleep,
        *,
        input_stream: TextIO | None = None,
        keyboard=None,
        width: int | None = None,
    ) -> None:
        self.stream = sys.stdout if stream is None else stream
        self._animated = effects and self.stream.isatty()
        self._sleep = sleep
        self.input_stream = sys.stdin if input_stream is None else input_stream
        self._keyboard = keyboard if keyboard is not None else self._tty_keyboard
        self.width = width if width is not None else shutil.get_terminal_size((80, 24)).columns

    def __enter__(self) -> Self:
        try:
            self.hide_cursor()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.reset_formatting()
        finally:
            self.show_cursor()

    def print(
        self,
        text: object = "",
        *values: object,
        sep: str = " ",
        end: str = "\n",
        flush: bool = True,
        style: str | None = None,
    ) -> None:
        """Print to the configured stream, flushing by default."""
        if style and self._animated:
            text = self.styled(str(text), style)
        builtins.print(text, *values, sep=sep, end=end, file=self.stream, flush=flush)

    def type_text(self, text: str, chars_per_second: float = 40) -> None:
        """Print one line, pausing between characters on an animated TTY."""
        if chars_per_second <= 0:
            raise ValueError("chars_per_second must be positive")
        if not self._animated:
            self.print(text)
            return
        for index, character in enumerate(text):
            self.print(character, end="")
            if index < len(text) - 1:
                self._sleep(1 / chars_per_second)
        self.print()

    def line_delay(self, milliseconds: float) -> None:
        """Pause for a visual effect; static output never waits."""
        if milliseconds < 0:
            raise ValueError("milliseconds must be nonnegative")
        if self._animated and milliseconds > 0:
            self._sleep(milliseconds / 1000)

    def clear(self) -> None:
        """Clear the screen and return to its top left corner."""
        if self._animated:
            self.print("\x1b[2J\x1b[H", end="")

    def hide_cursor(self) -> None:
        if self._animated:
            self.print("\x1b[?25l", end="")

    def show_cursor(self) -> None:
        if self._animated:
            self.print("\x1b[?25h", end="")

    def reset_formatting(self) -> None:
        if self._animated:
            self.print("\x1b[0m", end="")

    def styled(self, text: str, style: str = "accent") -> str:
        colors = {"accent": "36", "muted": "90", "warning": "33", "error": "31"}
        return f"\x1b[{colors[style]}m{text}\x1b[0m" if self._animated else text

    @contextmanager
    def _tty_keyboard(self):
        """Own temporary input mode and consume a complete skip keystroke.

        cbreak retains signal handling (Ctrl+C), unlike raw mode. Flush pending
        input on skip so escape sequences and pasted bytes cannot become a
        command. Fixed effects never enter this context or read input.
        """
        if not self.input_stream.isatty():
            yield None
            return
        if os.name == "nt":
            import msvcrt

            def poll():
                if not msvcrt.kbhit():
                    return False
                while msvcrt.kbhit():
                    if msvcrt.getwch() == "\x03":
                        raise KeyboardInterrupt
                return True

            yield poll
            return
        import select
        import termios
        import tty

        fd = self.input_stream.fileno()
        previous = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd, termios.TCSANOW)

            def poll():
                if not select.select([fd], [], [], 0)[0]:
                    return False
                key = os.read(fd, 1)
                termios.tcflush(fd, termios.TCIFLUSH)
                if key == b"\x1b":
                    # A terminal may deliver an arrow/function key in fragments.
                    try:
                        self._sleep(0.025)
                    finally:
                        termios.tcflush(fd, termios.TCIFLUSH)
                if key == b"\x03":
                    raise KeyboardInterrupt
                return True

            yield poll
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, previous)

    def _wait(self, seconds, poll):
        if poll is None:
            self._sleep(seconds)
            return False
        # Short injected sleeps bound skip latency without real-time test waits.
        while seconds > 0:
            if poll():
                return True
            interval = min(seconds, 0.025)
            self._sleep(interval)
            seconds -= interval
        return poll()

    def progress(self, label: str, duration: float, width: int = 20,
                 *, skippable: bool = True) -> None:
        """Cosmetic completion indicator; callers report only completed work."""
        if duration < 0 or width <= 0:
            raise ValueError("duration must be nonnegative and width must be positive")
        frames = (f"{label} [{'#' * n}{'-' * (width - n)}] {n * 100 // width}%"
                  for n in range(width + 1))
        self.animate_frames(frames, duration / width, skippable=skippable)

    def sequence(self, lines: Iterable[str], duration: float = 1.2) -> None:
        """A fixed verification sequence; each completed line stays in history."""
        if duration < 0:
            raise ValueError("duration must be nonnegative")
        lines = tuple(lines)
        for line in lines:
            self.print(line, style="accent")
            if self._animated:
                self._sleep(duration / len(lines))

    def countdown(self, seconds: int, prefix: str = "") -> None:
        """Count whole seconds down to zero."""
        if seconds < 0:
            raise ValueError("seconds must be nonnegative")
        if not self._animated:
            self.print(f"{prefix}0")
            return
        for remaining in range(seconds, -1, -1):
            self.print(f"\r\x1b[2K{prefix}{remaining}", end="")
            if remaining:
                self._sleep(1)
        self.print()

    def animate_frames(
        self, frames: Iterable[str], frame_delay: float, loops: int = 1,
        *, skippable: bool = True,
    ) -> None:
        """Repaint only the effect's own lines, preserving terminal history."""
        if frame_delay < 0 or loops < 0:
            raise ValueError("frame_delay and loops must be nonnegative")
        frames = tuple(frames)
        if not frames or not loops:
            return
        if not self._animated:
            self.print(frames[-1])
            return
        previous_lines = 0

        def paint(frame):
            nonlocal previous_lines
            if previous_lines:
                self.print(f"\x1b[{previous_lines}A", end="")
            columns = max(1, self.width - 1)
            lines = [part[offset:offset + columns]
                     for part in frame.split("\n")
                     for offset in range(0, max(1, len(part)), columns)]
            height = max(previous_lines, len(lines))
            for index in range(height):
                line = lines[index] if index < len(lines) else ""
                self.print("\r\x1b[2K" + line)
            previous_lines = height

        with self._keyboard() if skippable else nullcontext(None) as poll:
            for loop in range(loops):
                for index, frame in enumerate(frames):
                    paint(frame)
                    if loop < loops - 1 or index < len(frames) - 1:
                        if self._wait(frame_delay, poll):
                            paint(frames[-1])
                            return

    def fake_system_messages(self, lines: Iterable[str]) -> None:
        """Print presentation-only messages, separated by 100 milliseconds."""
        for index, line in enumerate(lines):
            if index:
                self.line_delay(100)
            self.print(line)

    def scramble_text(self, text: str, passes: int = 4) -> None:
        """Show random glyphs for 50 ms per pass, then reveal the original line."""
        if passes < 0:
            raise ValueError("passes must be nonnegative")
        if not self._animated:
            self.print(text)
            return
        frames = []
        for _ in range(passes):
            frames.append("".join(
                character if character.isspace()
                else random.choice("0123456789abcdef.-") for character in text
            ))
        self.animate_frames((*frames, text), 0.05)

    def flash_lines(self, lines: Iterable[str], delay: float = 0.1) -> None:
        """Flash a full-screen scene in reverse video, then redraw it normally."""
        if delay < 0:
            raise ValueError("delay must be nonnegative")
        scene = "\n".join(lines)
        if not self._animated:
            self.print(scene)
            return
        self.clear()
        try:
            self.print("\x1b[7m", end="")
            self.print(scene)
            self._sleep(delay)
        finally:
            self.reset_formatting()
        self.clear()
        self.print(scene)
