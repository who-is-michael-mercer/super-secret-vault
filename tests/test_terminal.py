import random
from io import StringIO

import pytest

from vaultgame.terminal import Terminal


class TTYStream(StringIO):
    def isatty(self):
        return True


def no_sleep(seconds):
    pytest.fail(f"Unexpected sleep: {seconds}")


def test_print_uses_configured_stream_and_print_options():
    stream = StringIO()
    terminal = Terminal(stream=stream, effects=False, sleep=no_sleep)

    terminal.print()
    terminal.print("relay", "ready", sep=": ", end="!")

    assert stream.getvalue() == "\nrelay: ready!"


def test_typewriter_flushes_characters_with_injected_delays():
    stream = TTYStream()
    observations = []
    terminal = Terminal(
        stream=stream,
        sleep=lambda delay: observations.append((delay, stream.getvalue())),
    )

    terminal.type_text("ABC", chars_per_second=4)

    assert observations == [(0.25, "A"), (0.25, "AB")]
    assert stream.getvalue() == "ABC\n"


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_typewriter_is_static_without_effects_or_tty(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).type_text("static text")

    assert stream.getvalue() == "static text\n"


@pytest.mark.parametrize("stream_type,effects,expected", [
    (TTYStream, True, [0.125]),
    (TTYStream, False, []),
    (StringIO, True, []),
])
def test_line_delay_uses_milliseconds_only_for_animated_tty(stream_type, effects, expected):
    delays = []
    terminal = Terminal(stream_type(), effects=effects, sleep=delays.append)

    terminal.line_delay(125)
    terminal.line_delay(0)

    assert delays == expected


@pytest.mark.parametrize("method,sequence", [
    ("clear", "\x1b[2J\x1b[H"),
    ("hide_cursor", "\x1b[?25l"),
    ("show_cursor", "\x1b[?25h"),
    ("reset_formatting", "\x1b[0m"),
])
@pytest.mark.parametrize("stream_type,effects", [
    (TTYStream, True), (TTYStream, False), (StringIO, True),
])
def test_terminal_controls_only_emit_ansi_for_animated_tty(method, sequence, stream_type, effects):
    stream = stream_type()
    terminal = Terminal(stream, effects=effects, sleep=no_sleep)

    getattr(terminal, method)()

    assert stream.getvalue() == (sequence if effects and stream.isatty() else "")


@pytest.mark.parametrize("failure", [None, KeyboardInterrupt, RuntimeError])
def test_context_restores_cursor_and_formatting_and_propagates_errors(failure):
    stream = TTYStream()
    terminal = Terminal(stream, sleep=no_sleep)

    def session():
        with terminal as active:
            assert active is terminal
            assert stream.getvalue() == "\x1b[?25l"
            terminal.print("visible text")
            if failure:
                raise failure("interrupted")

    if failure:
        with pytest.raises(failure, match="interrupted"):
            session()
    else:
        session()

    assert stream.getvalue() == "\x1b[?25lvisible text\n\x1b[0m\x1b[?25h"


@pytest.mark.parametrize("interrupted_sequence", ["\x1b[?25l", "\x1b[0m"])
def test_cleanup_attempts_cursor_restoration_when_entry_or_reset_is_interrupted(interrupted_sequence):
    class InterruptedStream(TTYStream):
        interrupted = False

        def flush(self):
            if not self.interrupted and self.getvalue().endswith(interrupted_sequence):
                self.interrupted = True
                raise KeyboardInterrupt
            super().flush()

    stream = InterruptedStream()

    with pytest.raises(KeyboardInterrupt):
        with Terminal(stream, sleep=no_sleep):
            pass

    assert "\x1b[0m" in stream.getvalue()
    assert stream.getvalue().endswith("\x1b[?25h")


def test_progress_displays_steps_and_uses_requested_duration():
    stream = TTYStream()
    observations = []
    terminal = Terminal(stream, sleep=lambda delay: observations.append((delay, stream.getvalue())))

    terminal.progress("Loading", duration=2, width=2)

    assert [delay for delay, _ in observations] == [1, 1]
    assert observations[0][1].endswith("Loading [--] 0%\n")
    assert observations[1][1].endswith("Loading [#-] 50%\n")
    assert stream.getvalue().endswith("Loading [##] 100%\n")
    assert "\r\x1b[2K" in stream.getvalue()


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_progress_is_one_completed_static_bar(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).progress("Loading", 2, width=3)

    assert stream.getvalue() == "Loading [###] 100%\n"


def test_frames_repaint_multiline_scenes_and_repeat_in_order():
    stream = TTYStream()
    observations = []
    terminal = Terminal(stream, sleep=lambda delay: observations.append((delay, stream.getvalue())))

    terminal.animate_frames(iter(["first\nscene", "last"]), frame_delay=0.25, loops=2)

    assert [delay for delay, _ in observations] == [0.25, 0.25, 0.25]
    assert observations[0][1].endswith("first\n\r\x1b[2Kscene\n")
    assert observations[1][1].endswith("last\n\r\x1b[2K\n")
    assert observations[2][1].endswith("first\n\r\x1b[2Kscene\n")
    assert "\x1b[2J" not in stream.getvalue()
    assert stream.getvalue().count("first") == 2
    assert stream.getvalue().count("last") == 2
    assert stream.getvalue().endswith("last\n\r\x1b[2K\n")


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_frames_degrade_to_final_scene_once(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).animate_frames(
        ["first\nscene", "last\nscene"], frame_delay=1, loops=3,
    )

    assert stream.getvalue() == "last\nscene\n"


def test_countdown_shows_each_second_and_zero_using_injected_sleeper():
    stream = TTYStream()
    observations = []
    terminal = Terminal(stream, sleep=lambda delay: observations.append((delay, stream.getvalue())))

    terminal.countdown(3, prefix="Remaining: ")

    assert [delay for delay, _ in observations] == [1, 1, 1]
    assert all(output.endswith(f"Remaining: {seconds}") for (_, output), seconds in zip(observations, [3, 2, 1]))
    assert stream.getvalue().endswith("Remaining: 0\n")


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_countdown_static_output_reports_completion_without_waiting(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).countdown(3, prefix="Remaining: ")

    assert stream.getvalue() == "Remaining: 0\n"


@pytest.mark.parametrize("stream_type,effects,expected_delays", [
    (TTYStream, True, [0.1, 0.1]), (TTYStream, False, []), (StringIO, True, []),
])
def test_fake_system_messages_print_every_line_with_optional_pacing(stream_type, effects, expected_delays):
    stream = stream_type()
    delays = []

    Terminal(stream, effects=effects, sleep=delays.append).fake_system_messages(
        iter(["link online", "scanning", "ready"]),
    )

    assert stream.getvalue() == "link online\nscanning\nready\n"
    assert delays == expected_delays


def test_scramble_displays_changed_characters_then_restores_text(monkeypatch):
    monkeypatch.setattr(random, "choice", lambda characters: "#")
    stream = TTYStream()
    observations = []
    terminal = Terminal(stream, sleep=lambda delay: observations.append((delay, stream.getvalue())))

    terminal.scramble_text("AB CD", passes=2)

    assert [delay for delay, _ in observations] == [0.05, 0.05]
    assert all(output.endswith("## ##\n") for _, output in observations)
    assert stream.getvalue().endswith("AB CD\n")


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_scramble_static_output_shows_only_original_text(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).scramble_text("AB CD", passes=2)

    assert stream.getvalue() == "AB CD\n"


def test_flash_repaints_lines_normally_after_highlight_and_delay():
    stream = TTYStream()
    observations = []
    terminal = Terminal(stream, sleep=lambda delay: observations.append((delay, stream.getvalue())))

    terminal.flash_lines(iter(["alert", "retry"]), delay=0.2)

    assert len(observations) == 1
    assert observations[0][0] == 0.2
    assert "\x1b[7m" in observations[0][1]
    assert observations[0][1].endswith("alert\nretry\n")
    assert stream.getvalue().endswith("\x1b[0m\x1b[2J\x1b[Halert\nretry\n")


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_flash_static_output_prints_each_line_once(stream_type, effects):
    stream = stream_type()

    Terminal(stream, effects=effects, sleep=no_sleep).flash_lines(["alert", "retry"], delay=1)

    assert stream.getvalue() == "alert\nretry\n"


def test_interrupted_flash_resets_its_formatting_even_without_a_context():
    stream = TTYStream()

    def interrupt(delay):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Terminal(stream, sleep=interrupt).flash_lines(["alert"])

    assert stream.getvalue().endswith("\x1b[0m")


@pytest.mark.parametrize("method,args,kwargs", [
    ("type_text", ("AB",), {"chars_per_second": 0}),
    ("type_text", ("AB",), {"chars_per_second": -1}),
    ("line_delay", (-1,), {}),
    ("progress", ("Loading", -1), {}),
    ("progress", ("Loading", 1), {"width": 0}),
    ("animate_frames", (["a", "b"], -1), {}),
    ("animate_frames", (["a", "b"], 1), {"loops": -1}),
    ("countdown", (-1,), {}),
    ("scramble_text", ("AB",), {"passes": -1}),
    ("flash_lines", (["alert"],), {"delay": -1}),
])
@pytest.mark.parametrize("stream_type", [TTYStream, StringIO])
def test_invalid_rates_durations_and_counts_are_rejected_before_output(method, args, kwargs, stream_type):
    stream = stream_type()
    terminal = Terminal(stream, sleep=no_sleep)

    with pytest.raises(ValueError):
        getattr(terminal, method)(*args, **kwargs)

    assert stream.getvalue() == ""


@pytest.mark.parametrize("stream_type,effects", [(TTYStream, False), (StringIO, True)])
def test_static_session_has_readable_output_without_ansi_or_delays(stream_type, effects):
    stream = stream_type()

    with Terminal(stream, effects=effects, sleep=no_sleep) as terminal:
        terminal.print("start")
        terminal.clear()
        terminal.type_text("ready")
        terminal.line_delay(100)
        terminal.progress("Loading", 1, width=2)
        terminal.animate_frames(["before", "after"], 0.5, loops=2)
        terminal.countdown(2, prefix="Remaining: ")
        terminal.fake_system_messages(["connected", "online"])
        terminal.scramble_text("decoded")
        terminal.flash_lines(["alert"])

    output = stream.getvalue()
    assert output == (
        "start\nready\nLoading [##] 100%\nafter\nRemaining: 0\n"
        "connected\nonline\ndecoded\nalert\n"
    )
    assert "\x1b" not in output
    assert "\r" not in output


# V2 effects own their input mode; all clocks below are injected.
from contextlib import contextmanager
import os


@pytest.mark.parametrize('skip', [False, True])
def test_animation_skip_consumes_key_restores_mode_and_renders_final(skip):
    events = []
    keys = ['x'] if skip else []
    @contextmanager
    def keyboard():
        events.append('enter')
        def poll():
            if keys:
                events.append(keys.pop())
                return True
            return False
        try:
            yield poll
        finally:
            events.append('restore')
    sleeps = []
    stream = TTYStream()
    terminal = Terminal(stream, sleep=sleeps.append, keyboard=keyboard)
    terminal.progress('verify', .3)
    assert stream.getvalue().endswith('verify [####################] 100%\n')
    assert keys == []
    assert events == (['enter', 'x', 'restore'] if skip else ['enter', 'restore'])
    assert sum(sleeps) == pytest.approx(0 if skip else .3)


def test_fixed_animation_never_reads_input_and_runs_injected_duration():
    def forbidden():
        pytest.fail('Fixed animation must not consume input')
    sleeps = []
    stream = TTYStream()
    terminal = Terminal(stream, sleep=sleeps.append, keyboard=forbidden)
    terminal.progress('bootstrap', 1.2, skippable=False)
    assert sum(sleeps) == pytest.approx(1.2)
    assert stream.getvalue().endswith('bootstrap [####################] 100%\n')
    sleeps.clear()
    terminal.sequence(['key check       ok', 'manifest        verified', 'session         active'])
    assert sum(sleeps) == pytest.approx(1.2)
    assert stream.getvalue().endswith('session         active\x1b[0m\n')


@pytest.mark.parametrize('failure', [RuntimeError, KeyboardInterrupt])
def test_skip_context_restores_on_timing_failure(failure):
    events = []
    @contextmanager
    def keyboard():
        try:
            yield lambda: False
        finally:
            events.append('restored')
    def fail(_):
        raise failure()
    stream = TTYStream()
    with pytest.raises(failure):
        with Terminal(stream, sleep=fail, keyboard=keyboard) as terminal:
            terminal.progress('mount', .3)
    assert events == ['restored']
    assert stream.getvalue().endswith('\x1b[0m\x1b[?25h')


@pytest.mark.parametrize('stream_type,effects', [(TTYStream, False), (StringIO, True)])
def test_static_animation_never_reads_skip_keys(stream_type, effects):
    def forbidden():
        pytest.fail('Static animation must not read input')
    stream = stream_type()
    terminal = Terminal(stream, effects=effects, sleep=no_sleep, keyboard=forbidden)
    terminal.progress('sync', .4)
    terminal.sequence(['verified', 'active'])
    terminal.print('warning', style='warning')
    assert stream.getvalue() == 'sync [####################] 100%\nverified\nactive\nwarning\n'


@pytest.mark.skipif(os.name != 'posix', reason='POSIX terminal modes')
@pytest.mark.parametrize('failure', [None, RuntimeError, KeyboardInterrupt])
def test_real_pty_input_restored_and_skip_sequence_consumed(failure):
    import pty
    import select
    import termios
    master, slave = pty.openpty()
    try:
        with os.fdopen(os.dup(slave), 'r') as input_stream:
            previous = termios.tcgetattr(slave)
            injected = []
            def tick(_):
                current = termios.tcgetattr(slave)
                assert not current[3] & (termios.ICANON | termios.ECHO)
                assert current[3] & termios.ISIG == previous[3] & termios.ISIG
                if failure:
                    raise failure()
                os.write(master, b'\x1b[A\n')
                assert select.select([slave], [], [], 1)[0]
                injected.append(True)
            terminal = Terminal(TTYStream(), input_stream=input_stream, sleep=tick)
            if failure:
                with pytest.raises(failure):
                    terminal.progress('mount', .3)
            else:
                terminal.progress('mount', .3)
                assert injected == [True, True]
                assert not select.select([slave], [], [], 0)[0]
                # A subsequent command contains no escape sequence or newline from skip.
                os.write(master, b'status\n')
                assert input_stream.readline() == 'status\n'
            assert termios.tcgetattr(slave) == previous
    finally:
        os.close(master)
        os.close(slave)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX terminal modes')
def test_partial_cbreak_setup_failure_restores_original_mode(monkeypatch):
    import pty
    import termios
    import tty
    master, slave = pty.openpty()
    try:
        with os.fdopen(os.dup(slave), 'r') as reader:
            previous = termios.tcgetattr(slave)
            original = tty.setcbreak
            def interrupted(fd, when):
                original(fd, when)
                raise KeyboardInterrupt
            monkeypatch.setattr(tty, 'setcbreak', interrupted)
            with pytest.raises(KeyboardInterrupt):
                Terminal(TTYStream(), input_stream=reader, sleep=no_sleep).progress('sync', .3)
            assert termios.tcgetattr(slave) == previous
    finally:
        os.close(master)
        os.close(slave)


def test_local_multiline_animation_keeps_prior_history_and_final_frame():
    stream = TTYStream()
    terminal = Terminal(stream, input_stream=StringIO(), sleep=lambda _: None)
    terminal.print('history retained')
    terminal.animate_frames(['mount\npending', 'active'], .1)
    output = stream.getvalue()
    assert output.startswith('history retained\n')
    assert '\x1b[2J' not in output
    assert output.endswith('\r\x1b[2Kactive\n\r\x1b[2K\n')


def test_narrow_effect_wraps_locally_instead_of_overwriting_history():
    stream = TTYStream()
    terminal = Terminal(stream, width=15, input_stream=StringIO(), sleep=lambda _: None)
    terminal.progress('verify', .3)
    assert '\x1b[2J' not in stream.getvalue()
    assert '\x1b[3A' in stream.getvalue()
    final = stream.getvalue().rsplit('\x1b[3A', 1)[1]
    assert final.replace('\r\x1b[2K', '').replace('\n', '') == 'verify [####################] 100%'
