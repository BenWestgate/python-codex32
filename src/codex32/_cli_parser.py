"""The complete, non-abbreviating command-line grammar."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from importlib.metadata import version


def _integer(
    label: str, minimum: int, maximum: int | None = None
) -> Callable[[str], int]:
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


def _command(
    parsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    return parsers.add_parser(
        name, help=help_text, description=help_text, allow_abbrev=False
    )


def _pretty(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pretty", action="store_true", help="Group output for writing by hand."
    )


def _wallet_options(parser: argparse.ArgumentParser, *, timestamp: bool) -> None:
    parser.add_argument(
        "--account",
        type=_integer("account", 0, 2**31 - 1),
        default=0,
        help="Bitcoin account number (default: 0).",
    )
    if timestamp:
        parser.add_argument(
            "--timestamp",
            type=_integer("timestamp", 0),
            default=0,
            help="Earliest descriptor time for Bitcoin Core (default: 0).",
        )
    parser.add_argument("--testnet", action="store_true", help="Use testnet keys.")


def parser() -> argparse.ArgumentParser:
    """Build the installed CLI without accepting abbreviated options."""
    result = argparse.ArgumentParser(
        prog="codex32",
        description="Create, check, recover, and use codex32 Bitcoin seed backups.",
        epilog=(
            "Do not type a seed or share into the command itself.\n"
            "Enter it when prompted, or pipe it into the command."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        allow_abbrev=False,
    )
    result.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit."
    )
    result.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('codex32')}",
        help="Show the installed version and exit.",
    )
    commands = result.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    check = _command(commands, "check", "Check a secret or share for copying errors.")
    check.description = (
        "Checks format, checksum, and application rules. A valid string is not "
        "proof that it belongs to the intended wallet."
    )
    secret = _command(commands, "secret", "Recover a secret from multiple shares.")
    _pretty(secret)
    share = _command(commands, "share", "Derive an additional share.")
    share.add_argument("index", help="Index for the additional share.")
    _pretty(share)

    correct = _command(commands, "correct", "Suggest repairs for damaged backup text.")
    correct.description = (
        "Suggest repairs for damaged backup text. In a complete string, use ? for "
        "an erasure; any other invalid data character is treated as one too."
    )
    correct.add_argument(
        "--residue",
        action="store_true",
        help="Correct only the final worksheet residue.",
    )
    correct.add_argument(
        "--erasure",
        dest="erasures",
        action="append",
        default=[],
        type=_integer("erasure", 1),
        metavar="POSITION",
        help="One-based position counted backward from the end; repeat as needed.",
    )
    _pretty(correct)

    checksum = _command(
        commands, "checksum", "Complete a Codex32 Book checksum worksheet."
    )
    checksum.add_argument(
        "header", nargs="?", help="Optional worksheet header; defaults to ms."
    )
    _pretty(checksum)
    create = _command(
        commands, "create", "Create a master-seed backup or split a secret."
    )
    create.add_argument(
        "header", nargs="?", help="Threshold and four-character identifier."
    )
    create.add_argument(
        "--bytes",
        dest="byte_length",
        type=_integer("bytes", 16, 64),
        help="New seed length in bytes (default: 16).",
    )
    create.add_argument(
        "--shares",
        type=_integer("shares", 2, 31),
        help="Number of shares to produce (default: threshold plus 2).",
    )
    create.add_argument("--indices", help="Exact share indices, in output order.")
    _pretty(create)

    wallet = _command(commands, "wallet", "Export data for Bitcoin wallet software.")
    wallet_commands = wallet.add_subparsers(dest="wallet_command", required=True)
    multisig = _command(
        wallet_commands,
        "multisig-xpub",
        "Export a public account key for multisig wallet software.",
    )
    _wallet_options(multisig, timestamp=False)
    bitcoin_core = _command(
        wallet_commands,
        "bitcoin-core",
        "Export wallet-import data for Bitcoin Core.",
    )
    core_modes = bitcoin_core.add_subparsers(dest="core_mode", required=True)
    for name, help_text in (
        ("restore", "Restore signing ability using private wallet data."),
        ("watch-only", "Find transactions without providing private keys."),
    ):
        mode = _command(core_modes, name, help_text)
        _wallet_options(mode, timestamp=True)

    xprv = _command(commands, "xprv", "Export the root extended private key.")
    xprv.add_argument("--testnet", action="store_true", help="Use a testnet key.")
    return result
