# fmt: off
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
            message = "Choose an index for the additional share." if message.endswith("INDEX") else "Choose a command."
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
    if value == "?": return "?"
    parsed = _integer("bytes", 16, 64)(value)
    if parsed not in SEED_BYTE_LENGTHS: raise argparse.ArgumentTypeError(
        "bytes must be 16, 20, 24, 28, 32, 64, or ?")
    return parsed

def _command(parsers: argparse._SubParsersAction[_Parser], name: str, summary: str) -> _Parser:
    description = summary[0].upper() + summary[1:] + "."
    return parsers.add_parser(name, help=summary, description=description, allow_abbrev=False)

def _terminal_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plain", action="store_true", help="print without transcription formatting")

def _wallet_options(parser: argparse.ArgumentParser, *, timestamp: bool) -> None:
    parser.add_argument("--account", type=_integer("account", 0, 2**31 - 1), default=0,
                        help="account number (default: 0)")
    if timestamp:
        parser.add_argument("--timestamp", type=_timestamp, default=0,
                            help="earliest descriptor time or now for Bitcoin Core (default: 0)")
    parser.add_argument("--testnet", action="store_true", help="use testnet keys")

def parser() -> argparse.ArgumentParser:
    result = _Parser(prog="codex32",
                     description="Create, check, recover, and use codex32 Bitcoin seed backups.",
                     epilog="Do not type a seed or share into the command itself.\n"
                            "Enter it when prompted, or pipe it into the command.",
                     formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    result.add_argument("--version", action="version", version=f"%(prog)s {version('codex32')}",
                        help="show the installed version and exit")
    commands = result.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    check = _command(commands, "check", "check whether a secret or share is intact")
    check.description = "Checks format, checksum, and application rules."
    secret = _command(commands, "secret", "recover a secret from shares")
    secret.description = ("Recover and display the complete secret. This removes the protection "
                          "provided by splitting it into shares.")
    _terminal_output(secret)
    share = _command(commands, "share", "derive a share from codex32 strings")
    share.description = "Derive an additional share from existing codex32 strings."
    share.add_argument("index", metavar="INDEX", help="index for the derived share")
    _terminal_output(share)

    correct = _command(commands, "correct", "suggest repairs for damaged backup text")
    correct.description = ("Suggest repairs for damaged backup text. Corrects up to four arbitrary missing "
        "or extra characters, including mixtures; up to two skipped or extra four-character groups, "
        "including one of each; use ? for an erasure.")
    correct.add_argument("--residue", action="store_true", help="correct only the final worksheet residue")
    correct.add_argument("-e", "--erasure", dest="erasures", action="append", default=[],
        type=_integer("erasure", 1), metavar="POSITION",
        help="one-based position counted backward from the end; repeat as needed")
    correct.add_argument("--bytes", dest="byte_length", type=_correction_bytes, metavar="BYTES",
        help="expected master-seed bytes: 16, 20, 24, 28, 32, or 64; ? searches every size")
    _terminal_output(correct)

    checksum = _command(commands, "checksum", "finish a codex32 checksum worksheet")
    checksum.description = "Finish a codex32 checksum worksheet using its non-pink bold squares."
    checksum.add_argument(
        "header", nargs="?", metavar="HEADER", help="worksheet header; omit to enter it at the prompt"
    )
    _terminal_output(checksum)
    create = _command(commands, "create", "create a new backup or split an existing secret")
    create.description = "Create a backup. Fresh Bitcoin creation confirms cards and initializes Bitcoin Core."
    create.add_argument("header", nargs="?", metavar="HEADER",
        help="backup header or sharing threshold, such as 3cash or 3; omit to create a new "
             "unshared Bitcoin master seed")
    create.add_argument("--bytes", dest="byte_length", type=_integer("bytes", 16, 64),
        choices=SEED_BYTE_LENGTHS, metavar="BYTES",
        help="length of a new Bitcoin master seed: 16, 20, 24, 28, 32, or 64 bytes (default: 16)")
    create.add_argument("--shares", type=_integer("shares", 2, 31), metavar="COUNT",
        help="number of shares to output (defaults: 3 for threshold 2; 5 for threshold 3)")
    create.add_argument("--indices", metavar="INDICES", help="exact share indices, in output order")
    create.add_argument("--existing", action="store_true",
                        help="use an existing codex32 secret or hexadecimal seed")
    _terminal_output(create)

    wallet = _command(commands, "wallet", "initialize or export data for Bitcoin wallet software")
    wallet_commands = wallet.add_subparsers(dest="wallet_command", required=True)
    multisig = _command(wallet_commands, "multisig-xpub", "export an account xpub for multisig coordinators")
    _wallet_options(multisig, timestamp=False)
    bitcoin_core = _command(wallet_commands, "bitcoin-core", "initialize a Bitcoin Core wallet")
    core_modes = bitcoin_core.add_subparsers(dest="core_mode", required=True)
    for name, help_text in (
        ("restore", "restore signing ability using private wallet data"),
        ("watch-only", "find transactions without providing private keys"),
    ):
        mode = _command(core_modes, name, help_text)
        _wallet_options(mode, timestamp=True)

    xprv = _command(commands, "xprv", "export the root extended private key")
    xprv.add_argument("--testnet", action="store_true", help="use a testnet key")
    return result
