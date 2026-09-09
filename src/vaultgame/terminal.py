"""Standard-library terminal rendering with optional, injectable timing."""

import builtins
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
    ) -> None:
        self.stream = sys.stdout if stream is None else stream
        self._animated = effects and self.stream.isatty()
        self._sleep = sleep

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
    ) -> None:
        """Print to the configured stream, flushing by default."""
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

    def progress(self, label: str, duration: float, width: int = 20) -> None:
        """Fill a progress bar over duration seconds."""
        if duration < 0 or width <= 0:
            raise ValueError("duration must be nonnegative and width must be positive")
        if not self._animated:
            self.print(f"{label} [{'#' * width}] 100%")
            return
        for filled in range(width + 1):
            bar = "#" * filled + "-" * (width - filled)
            self.print(f"\r\x1b[2K{label} [{bar}] {filled * 100 // width}%", end="")
            if filled < width:
                self._sleep(duration / width)
        self.print()

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
        self, frames: Iterable[str], frame_delay: float, loops: int = 1
    ) -> None:
        """Repaint full-screen ASCII frames, with frame_delay in seconds."""
        if frame_delay < 0 or loops < 0:
            raise ValueError("frame_delay and loops must be nonnegative")
        frames = tuple(frames)
        if not self._animated:
            if frames and loops:
                self.print(frames[-1])
            return
        for loop in range(loops):
            for index, frame in enumerate(frames):
                self.clear()
                self.print(frame)
                if loop < loops - 1 or index < len(frames) - 1:
                    self._sleep(frame_delay)

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
        for _ in range(passes):
            scrambled = "".join(
                character if character.isspace()
                else random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#?@")
                for character in text
            )
            self.print(f"\r\x1b[2K{scrambled}", end="")
            self._sleep(0.05)
        self.print(f"\r\x1b[2K{text}")

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
