"""Administrative CLI routing for Relay."""

import argparse
import sys

from vaultgame.config import resolve_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relay", description="Relay terminal vault")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init", help="Initialize a vault (unavailable in this build)")
    args = parser.parse_args(argv)

    if args.command == "init":
        print("Vault initialization is not available in this build.", file=sys.stderr)
        return 1

    print(f"Relay package ready. Application data: {resolve_paths().home}")
    return 0
