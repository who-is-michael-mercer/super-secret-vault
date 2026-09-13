"""Relay CLI and explicit cover/access/authenticated-session lifecycle."""

import argparse
import sys
from pathlib import Path

from . import settings, cover, incidents
from .access import AccessController, AccessState
from .auth import RetryPolicy, BackoffError
from .input import TTYInput, WakeMatcher, InputTimeout
from .parser import parse_command, CommandParseError
from .terminal import Terminal
from .vault import capsule, crypto, store
from .vault.session import VaultSession, AuthenticationError, VaultLockedError
from .migration import migrate

HELP = """list                            list protected files
store <source> [name]            encrypt a file; retain source
retrieve <name> <destination>    authenticate and write a new plaintext file
remove <name>                   remove (confirmation required)
rename <old> <new>               change a logical name
info <name>                     show file metadata
lock                            return to cover
clear                           clear the display
help                            show commands
exit                            lock and exit"""


def clear(keyboard):
    keyboard._write("\x1b[2J\x1b[H")


def authenticate(path, keyboard, terminal, config, *, recovery=False):
    with store.open_regular(path) as source:
        identity = store.read_capsule(source, recovery=recovery)[0].header["vault_id"]
    policy = RetryPolicy(identity)
    for _ in range(3):
        policy.check()
        keyboard.boundary()
        password = keyboard.read_line("password: ", secret=True)
        try:
            session = VaultSession.authenticate(
                password, path, timeout=config["auto_lock_seconds"], recovery=recovery
            )
        except AuthenticationError:
            policy.failure()
            terminal.print("auth: password or authentication metadata did not verify")
        else:
            try:
                policy.success()
            except BaseException:
                session.close()
                raise
            return session
        finally:
            del password
    return None


def vault_loop(session, keyboard, terminal):
    while True:
        expired = lambda: session.is_locked() or session.timed_out.is_set()
        try:
            line = keyboard.read_line("vault0:/data> ", expired=expired)
            if expired():
                return "lock"
            session.touch_activity()
            command = parse_command(line)
            name, args = command.name, command.args
            if not name:
                continue
            arity = {
                "list": (0,),
                "store": (1, 2),
                "retrieve": (2,),
                "remove": (1,),
                "rename": (2,),
                "info": (1,),
                "lock": (0,),
                "clear": (0,),
                "help": (0,),
                "exit": (0,),
            }
            if name not in arity:
                terminal.print("command: unavailable")
                continue
            if len(args) not in arity[name]:
                terminal.print(
                    "usage: "
                    + next(
                        row for row in HELP.splitlines() if row.startswith(name + " ")
                    )
                )
                continue
            if name in {"lock", "exit"}:
                return name
            if name == "clear":
                clear(keyboard)
            elif name == "help":
                terminal.print(HELP)
            elif name == "list":
                entries = session.list_files()
                for entry in entries:
                    terminal.print(
                        f"{cover.display(entry['name'])} — {entry['size']} bytes"
                    )
                if not entries:
                    terminal.print("index: empty")
            elif name == "info":
                for key, value in session.info(args[0]).items():
                    terminal.print(f"{key}: {cover.display(value)}")
            elif name == "store":
                session.store(*args)
                terminal.print("store: verified and committed")
            elif name == "retrieve":
                session.retrieve(*args)
                terminal.print("retrieve: authenticated and written")
            elif name == "rename":
                session.rename(*args)
                terminal.print("rename: committed")
            elif name == "remove":
                answer = keyboard.read_line(
                    f"remove '{cover.display(args[0])}'? [y/N] ", expired=expired
                )
                if expired():
                    return "lock"
                if answer.lower() in {"y", "yes"}:
                    session.remove(*args)
                    terminal.print("remove: committed")
                else:
                    terminal.print("remove: canceled")
        except (InputTimeout, VaultLockedError):
            return "lock"
        except CommandParseError:
            terminal.print("command: invalid quoting")
        except (store.CommitUncertainError, store.ConcurrentWriteError):
            raise
        except crypto.IntegrityError:
            raise
        except (ValueError, OSError) as error:
            terminal.print("operation refused: " + cover.display(error))


def run_application(path, config, *, maintenance=False, armed=False):
    terminal = Terminal(effects=config["effects"])
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if maintenance:
            raise ValueError("Maintenance requires an interactive terminal.")
        cover.render(terminal, path)
        return 0
    state = AccessState.AUTHENTICATING if maintenance else AccessState.COVER
    with TTYInput(alternate=not maintenance) as keyboard:
        while True:
            if state == AccessState.COVER:
                keyboard.boundary()
                clear(keyboard)
                cover.render(terminal, path)
                matcher = WakeMatcher(config["wake"])
                while True:
                    key = keyboard.poll()
                    if key is None:
                        continue
                    if key.kind in {"RESIZE", "RESUME"}:
                        matcher.reset()
                        clear(keyboard)
                        cover.render(terminal, path)
                        continue
                    if matcher.feed(key):
                        break
                state = AccessState.WAKING
            if state == AccessState.WAKING:
                clear(keyboard)
                terminal.print("link: synchronizing")
                keyboard.transition(config["effects"])
                controller = AccessController()
                state = AccessState.ROUTE
            if state == AccessState.ROUTE:
                try:
                    line = keyboard.read_line(controller.prompt)
                    result = controller.handle(parse_command(line))
                except InputTimeout:
                    state = AccessState.COVER
                    continue
                except CommandParseError:
                    terminal.print("command: invalid quoting")
                    continue
                if result.message:
                    terminal.print(result.message)
                if result.action == "exit":
                    return 0
                if result.action == "sleep":
                    state = AccessState.COVER
                elif result.action == "clear":
                    clear(keyboard)
                elif result.action == "incident":
                    incidents.channel_reset(
                        terminal, config["real_os_actions"], armed=armed
                    )
                elif result.action == "authenticate":
                    state = AccessState.AUTHENTICATING
                if state != AccessState.AUTHENTICATING:
                    continue
            if state == AccessState.AUTHENTICATING:
                if path is None:
                    terminal.print("source: unavailable")
                    state = AccessState.COVER
                    continue
                session = None
                try:
                    session = authenticate(path, keyboard, terminal, config)
                    if session is None:
                        if maintenance:
                            return 1
                        state = AccessState.COVER
                        continue
                    state = AccessState.UNLOCKED
                    with session:
                        session.start_auto_lock()
                        keyboard.boundary()
                        terminal.print("manifest: authenticated\nsession: active")
                        outcome = vault_loop(session, keyboard, terminal)
                    if outcome == "exit" or maintenance:
                        return 0
                except (ValueError, OSError) as error:
                    terminal.print("access: " + cover.display(error))
                    if maintenance:
                        return 1
                    # Leave an actionable real error visible until the owner sleeps/exits.
                    controller = AccessController()
                    state = AccessState.ROUTE
                    continue
                state = AccessState.COVER


def parser():
    result = argparse.ArgumentParser(
        prog="relay", description="Local encrypted vault and Relay interface"
    )
    result.add_argument(
        "--arm-os-actions",
        action="store_true",
        help="Arm locally enabled, bound and allowlisted actions for this launch",
    )
    commands = result.add_subparsers(dest="command")
    for name in ("open", "maintenance", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("path")
    for name in ("init", "migrate", "export", "backup", "recover"):
        sub = commands.add_parser(name)
        if name != "init":
            sub.add_argument("source")
        sub.add_argument("destination")
        if name in ("init", "migrate", "export"):
            sub.add_argument("--image")
    configure = commands.add_parser("configure")
    configure.add_argument("--target")
    configure.add_argument(
        "--wake", nargs="+", help="ASCII characters or UP DOWN LEFT RIGHT"
    )
    configure.add_argument("--reset-wake", action="store_true")
    configure.add_argument("--effects", choices=("on", "off"))
    configure.add_argument("--idle", type=float)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = settings.load()
        if args.command == "configure":
            changed = False
            for key, value in [
                (
                    "target",
                    (
                        str(Path(args.target).expanduser().absolute())
                        if args.target
                        else None
                    ),
                ),
                ("wake", list(settings.DEFAULT_WAKE) if args.reset_wake else args.wake),
                ("effects", args.effects == "on" if args.effects else None),
                ("auto_lock_seconds", args.idle),
            ]:
                if value is not None:
                    config[key] = value
                    changed = True
            if changed:
                settings.save(config)
            for key in ("target", "wake", "effects", "auto_lock_seconds"):
                print(f"{key}: {cover.display(config[key])}")
            return 0
        if args.command in (None, "open", "maintenance"):
            path = getattr(args, "path", None) or config["target"]
            return run_application(
                path,
                config,
                maintenance=args.command == "maintenance",
                armed=args.arm_os_actions,
            )
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError(
                "Password operations require an interactive terminal; passwords are never accepted as arguments or redirected input."
            )
        terminal = Terminal(effects=False)
        with TTYInput(alternate=False) as keyboard:
            if args.command == "init":
                password = keyboard.read_line("password: ", secret=True)
                keyboard.boundary()
                confirmation = keyboard.read_line("confirm password: ", secret=True)
                try:
                    if not password or password != confirmation:
                        raise ValueError("Passwords must match and must not be empty.")
                    header, key = capsule.metadata(password)
                finally:
                    del password, confirmation
                try:
                    store.create(args.destination, header, bytes(key), image=args.image)
                finally:
                    key[:] = bytes(len(key))
                terminal.print("created: " + cover.display(args.destination))
                return 0
            if args.command == "migrate":
                if (
                    settings.home()
                    .resolve()
                    .is_relative_to(store.target_path(args.source))
                ):
                    raise store.StorageError(
                        "Set RELAY_HOME outside the legacy source before migration."
                    )
                policy = RetryPolicy("legacy:" + str(store.target_path(args.source)))
                for _ in range(3):
                    policy.check()
                    keyboard.boundary()
                    password = keyboard.read_line("password: ", secret=True)
                    try:
                        destination, orphans = migrate(
                            args.source, args.destination, password, image=args.image
                        )
                    except crypto.IntegrityError:
                        policy.failure()
                        terminal.print("legacy authentication/integrity check failed")
                    else:
                        policy.success()
                        terminal.print(
                            f"migrated: {cover.display(destination)}\nunreferenced source items retained: {orphans}"
                        )
                        return 0
                    finally:
                        del password
                return 1
            source = args.path if args.command == "verify" else args.source
            session = authenticate(
                source, keyboard, terminal, config, recovery=args.command == "recover"
            )
            if session is None:
                return 1
            with session:
                manifest = session.verify()
                terminal.print(
                    f"verified: generation {manifest['generation']} / {manifest['created_at']}"
                )
                if args.command == "verify":
                    return 0
                if args.command == "recover":
                    answer = keyboard.read_line(
                        "recover this snapshot to a new destination? [y/N] "
                    )
                    if answer.lower() not in {"y", "yes"}:
                        terminal.print("recovery canceled")
                        return 0
                session.export(args.destination, image=getattr(args, "image", None))
                terminal.print("written: " + cover.display(args.destination))
                return 0
    except (KeyboardInterrupt, EOFError):
        return 130
    except (ValueError, OSError) as error:
        print("relay: " + cover.display(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
