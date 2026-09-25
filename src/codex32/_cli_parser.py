# The complete, non-abbreviating command-line grammar.

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from importlib.metadata import version
from typing import Literal, NoReturn

from codex32.profiles.ms32 import SEED_BYTE_LENGTHS


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        if message.startswith("the following arguments are required: "):
            message = (
                "Choose an index for the additional share."
                if message.endswith("INDEX")
                else "Choose a command."
            )
        elif message.startswith("unrecognized arguments: "):
            message = "Remove or correct these arguments: " + message.removeprefix("unrecognized arguments: ")
        else:
            message = message[0].upper() + message[1:]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {message}\n")


def _integer(label: str, minimum: int, maximum: int | None = None) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
        if parsed < minimum or (maximum is not None and parsed > maximum):
            bound = f" through {maximum}" if maximum is not None else " or greater"
            raise argparse.ArgumentTypeError(f"{label} must be {minimum}{bound}")
        return parsed

    return parse


def _timestamp(value: str) -> int | Literal["now"]:
    return "now" if value == "now" else _integer("timestamp", 0)(value)


def _correction_bytes(value: str) -> int | Literal["?"]:
    if value == "?":
        return "?"
    parsed = _integer("bytes", 16, 64)(value)
    if parsed not in SEED_BYTE_LENGTHS:
        raise argparse.ArgumentTypeError("bytes must be 16, 20, 24, 28, 32, 64, or ?")
    return parsed


def _command(parsers: argparse._SubParsersAction[_Parser], name: str, summary: str) -> _Parser:
    description = summary[0].upper() + summary[1:] + "."
    return parsers.add_parser(name, help=summary, description=description, allow_abbrev=False)


def _terminal_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plain", action="store_true", help="print unformatted backup text")


def _wallet_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--account",
        type=_integer("account", 0, 2**31 - 1),
        default=0,
        help="account number (default: 0)",
    )
    parser.add_argument(
        "--timestamp",
        type=_timestamp,
        default=0,
        help="search for transactions since this Unix timestamp; use 0 for all history or now for a new wallet",
    )


def parser(prog: str = "codex32", *, master_seed: bool = False) -> argparse.ArgumentParser:
    result = _Parser(
        prog=prog,
        description=(
            "Create, check, and recover codex32 backups and restore wallets from them."
            if master_seed
            else "Check, correct, recover, and derive shares from codex32 backups."
        ),
        epilog="Never put a secret or share in command arguments or shell command text.\n"
        "Enter it when prompted; some commands also accept redirected standard input.\n"
        "Protect redirected sources separately: shells, terminals, and wrappers may retain text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    result.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('codex32')}",
        help="show the installed version and exit",
    )
    commands = result.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    check = _command(commands, "check", "check a secret or share for errors")
    check.description = "Check a secret or share for format, checksum, or content errors."
    secret = _command(commands, "secret", "recover a secret from shares")
    secret.description = (
        "Recover the secret using exactly the threshold number of shares from the same set. "
        "Use different share indices. You can also enter an existing secret to display it."
    )
    _terminal_output(secret)
    share = _command(
        commands,
        "share",
        "derive a share from codex32 strings",
    )
    share.description = (
        "Derive a share at INDEX using exactly the threshold number of codex32 strings from the same set. "
        "Use different input indices; one input may be the secret. "
        "INDEX must differ from S and the input indices."
    )
    share.add_argument("index", metavar="INDEX", help="index for the derived share")
    share.add_argument("--plain", action="store_true", help="print without formatting or card confirmation")

    correct = _command(commands, "correct", "suggest repairs for a damaged codex32 string")
    correct.description = (
        "Suggest repairs for wrong, unreadable, missing, extra, or swapped characters or "
        "four-character groups. "
        "Use ? for each unreadable character. Check suggested repairs against the original backup."
    )
    correct.add_argument(
        "--residue",
        action="store_true",
        help="correct only the final worksheet residue",
    )
    correct.add_argument(
        "-e",
        "--erasure",
        dest="erasures",
        action="append",
        default=[],
        type=_integer("erasure", 1),
        metavar="POSITION",
        help="one-based position counted backward from the end; repeat as needed",
    )
    if master_seed:
        correct.add_argument(
            "--bytes",
            dest="byte_length",
            type=_correction_bytes,
            metavar="BYTES",
            help="expected master-seed bytes: 16, 20, 24, 28, 32, or 64; ? searches every size",
        )
    _terminal_output(correct)

    if not master_seed:
        return result

    create = _command(commands, "create", "create or confirm a backup, or split an existing secret")
    create.description = "Create and confirm recovery cards, then initialize a Bitcoin Core wallet."
    create.add_argument(
        "header",
        nargs="?",
        metavar="HEADER",
        help="backup header or sharing threshold, such as 3cash or 3; omit for a single recovery card",
    )
    create.add_argument(
        "--bytes",
        dest="byte_length",
        type=_integer("bytes", 16, 64),
        choices=SEED_BYTE_LENGTHS,
        metavar="BYTES",
        help="length of a new Bitcoin master seed: 16, 20, 24, 28, 32, or 64 bytes (default: 16)",
    )
    create.add_argument(
        "--shares",
        type=_integer("shares", 2, 31),
        metavar="COUNT",
        help="number of shares to output (defaults: 3 for threshold 2; 5 for threshold 3)",
    )
    create.add_argument("--indices", metavar="INDICES", help="exact share indices, in output order")
    create.add_argument(
        "--existing",
        action="store_true",
        help="use an existing Bitcoin codex32 secret or hexadecimal seed",
    )

    wallet = _command(commands, "wallet", "restore a Bitcoin Core wallet")
    _wallet_options(wallet)

    xprv = _command(commands, "xprv", "export the root extended private key")
    xprv.add_argument("--testnet", action="store_true", help="use a testnet key")
    return result
