"""Simple CLI for codex32."""

import importlib.metadata as _im
import os
import sys
import json
from pathlib import Path

import click
from bip32 import BIP32
from codex32 import Codex32String
from codex32.bip93 import MismatchedHrp, IDX_SORT
from codex32.descriptor import (
    descriptors_from_node,
    DESCRIPTOR_TEMPLATES,
    descsum_check,
    get_key_origin_xkey_from_path,
)
from codex32.errors import CodexError
from codex32.bech32 import bech32_to_u5, InvalidLength
from bdkpython import Descriptor, Network

PUB_DESC = "pkh([fab6868a/44h/0h/0h]xpub6CEpE5YnMCzrtF49STu5YSxgSoCKQ4aMPEToGrVxpeJ9C7vUxHFwZAAs8dKhbhFty53nx1LpTnnSrCza6MSDh54Dse6WBoDD6xjSEPLyRBM/<0;1>/*)#f3ecrj0z"
XPRV = "xprv9s21ZrQH143K2NkobdHxXeyFDqE44nJYvzLFtsriatJNWMNKznGoGgW5UMTL4fyWtajnMYb5gEc2CgaKhmsKeskoi9eTimpRv2N11THhPTU"
desc = Descriptor(PUB_DESC, Network.BITCOIN)
desc.to_string_with_secret()

# validate  Validate a codex32 string or descriptor checksum

# interpolate    Derive additional shares from an existing valid k-set

# recover   Recover a codex32 secret from k valid shares

# descriptor    Produce importable descriptor
#   --private for spending wallet (xpub by default)
#   --account-path m/84'/0'/0' default from Core.
#   include fingerprint/derivation (key origin info) in descriptor.
#   auto-detect: multiple shares, the codex32 secret or an xprv


# cat shares.txt | codex32 descriptor --private --out-file core-wallet.json
# then import with bitcoind:
# bitcoin-cli createwallet mywallet true "blank" false false false "" core-wallet.json

# xprv   Output master extended private key from codex32 strings
#   autocalls `recover` internally.
#   optional if bipsea supports codex32 import directly.

# create    Create new codex32 shares (generate entropy, make n shares)
#   prints "Generated identifier: 0234"
#   --identifier  Specify identifier (4 chars) instead of generating
#   --threshold  Minimum number of shares to recover secret (default 2)
#   --shares     Total number of shares to create (default 5)
#   If input is raw bytes → treat as “new seed, never codex32-encoded.”
#   If input is valid codex32 secret → treat as “reshare” (generate fresh identifier if necessary).

# --format json for create and descriptor

# version

# correct   Produce corrections for strings
#   deferr for v2
#   if a valid descriptor is given assume the secret fingerprint is in the descriptor.
#   otherwise require --fingerprint option.

# help


# TODO see if the type= can be removed due to function type hints.


def _format_codex32_string(s: Codex32String, node: BIP32, row_len=4) -> str:
    """Group into 4-char groups separated by spaces, with an extra space every 4 groups"""
    groups = [s.s[i : i + 4] for i in range(0, len(s), 4)]
    for i, group in enumerate(groups):
        groups[i] = f"{'\x1b[22m' if i % 2 else '\x1b[1m'}{group.upper()}"
        groups[i] += " " if (i + 1) % row_len == 0 else ""  # creates double space

    formatted = " ".join(groups)
    ret = f"Threshold Scheme:    {s.k or 1}-of-N\n"
    ret += f"Codex32 Identifier:  {s.ident.upper()}\n"
    ret += f"Master Fingerprint:  {node.get_fingerprint().hex().upper()}\n\n"
    ret += (
        "\x1b[1;31mS — SECRET:   "
        if s.share_idx == "s"
        else s.share_idx.upper() + ":  "
    )

    return ret + formatted + "\x1b[0m"


@click.group(invoke_without_command=True)
@click.option(
    "--interpolate",
    type=str,
    help="Derive codex32 string at provided share index.",
)
@click.option(
    "--pretty",
    is_flag=True,
    help="Print string metadata and use visually distinct 4 character groups.",
)
@click.option(
    "--testnet",
    is_flag=True,
    help="Use testnet for version bytes and BIP44 coin type.",
)
@click.option(
    "--account", type=int, help="Increment per new wallet joined to prevent key reuse."
)
@click.option(
    "--descriptors",
    is_flag=True,
    help="Show wallet descriptors JSON for Bitcoin Core import.",
)
@click.option(
    "--private",
    is_flag=True,
    help="Show master extended private key or private descriptors.",
)
@click.version_option(package_name="codex32", prog_name="codex32")
@click.help_option()
@click.pass_context
@click.argument("strings", nargs=-1)
def cli(
    ctx: click.Context,
    testnet: bool,
    account: int,
    descriptors: bool,
    interpolate: str,
    pretty: int,
    private: bool,
    strings: str,
) -> None:
    """codex32: BIP-0093 encode/decode/interpolate tools."""
    ctx.ensure_object(dict)
    strings = strings or try_for_pipe_input(strings)
    path = "{}/<44h;49h;84h;86h>/{}h/{}h" if descriptors else "{}/48'/{}'/{}'/2'"
    if ctx.invoked_subcommand is None and strings:
        # Recover a codex32 secret from k valid shares and output BIP32 master node."""
        # Parse and validate codex32 strings from input.
        shares = [Codex32String(s) for s in strings]
        secret = shares[0] if len(shares) == 1 else Codex32String.interpolate_at(shares)
        node = BIP32.from_seed(secret.data, "test" if testnet else "main")
        if interpolate:
            string = Codex32String.interpolate_at(shares, interpolate)
            click.echo(_format_codex32_string(string, node) if pretty else string)
            ctx.exit(0)
        if secret.share_idx != "s":
            header = secret.s[: len(secret.hrp) + 7]
            click.echo(f"Valid codex32 share with header: {header}")
            ctx.exit(0)
        if secret.hrp != "ms":
            raise MismatchedHrp("HRP must be 'ms' to recover BIP32 master node.")
        if descriptors or not private:
            path, account = next_account_for(node, path, account)
        click.echo(
            json.dumps(
                descriptors_from_node(
                    node, DESCRIPTOR_TEMPLATES, account, private, timestamp="now"
                )
            )
            if descriptors
            else get_key_origin_xkey_from_path(node, "m" if private else path, private)
        )
    else:
        click.echo(ctx.get_help())


@cli.command(
    name="correct",
    help="Produce corrections for strings.",
)
def correct() -> str:
    """Produce corrections for strings."""
    click.echo("Not yet implemented")
    sys.exit(1)


@cli.command(
    name="create",
    help="Create new codex32 backup set.",
)
@click.option("--identifier", type=str, help="Four-character backup identifier.")
@click.option("--threshold", type=click.IntRange(1, 9), default=2, show_default=True)
@click.option("--shares", type=click.IntRange(1, len(IDX_SORT) - 1), default=5, show_default=True)
@click.argument("seed", required=False)
def create(identifier: str | None, threshold: int, shares: int, seed: str | None) -> None:
    """Create new codex32 backup set."""
    if threshold > shares:
        raise click.BadParameter(
            "Threshold cannot exceed the number of shares.",
            param_hint="--threshold",
        )

    seed = seed or try_for_pipe_input(seed)
    if seed:
        try:
            source = Codex32String(seed)
            data = source.data
        except CodexError:
            try:
                data = bytes.fromhex(seed)
            except ValueError as exc:
                raise click.BadParameter(
                    "Seed must be hexadecimal bytes or a valid codex32 string.",
                    param_hint="seed",
                ) from exc
    else:
        data = os.urandom(32)

    if identifier is None:
        identifier = Codex32String.from_seed(os.urandom(16)).ident
        click.echo(f"Generated identifier: {identifier}", err=True)
    identifier = identifier.lower()
    if len(identifier) != 4 or any(char not in IDX_SORT for char in identifier):
        raise click.BadParameter(
            "Identifier must contain exactly four bech32 characters.",
            param_hint="--identifier",
        )

    indices = IDX_SORT[1 : shares + 1]
    secret = Codex32String.from_seed(data, f"ms1{threshold}{identifier}s")
    basis = [secret]
    for index in indices[: threshold - 1]:
        basis.append(
            Codex32String.from_seed(
                os.urandom(len(data)), f"ms1{threshold}{identifier}{index}"
            )
        )
    for index in indices:
        click.echo(Codex32String.interpolate_at(basis, index))


def no_empty_param(name: str, val, msg="Must not be empty."):
    """Raise BadParameter if val is empty."""
    if not val:
        raise click.BadParameter(msg, param_hint=name)


def try_for_pipe_input(val):
    """Try to read from stdin if not a tty. Raise BadParameter if empty."""
    ret = val or "" if sys.stdin.isatty() else sys.stdin.read().strip()
    return ret


base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
(DB_PATH := base / "codex32").mkdir(parents=True, exist_ok=True)


def _load_db(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r+") as f:
        return json.load(f)


def _save_db(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


def next_account_for(node: BIP32, path: str, account: None | int) -> tuple[str, int]:
    """
    key_origin_info: stable identifier per seed
    returns next account index (and increments it atomically)
    """
    fingerprint = node.get_fingerprint().hex()
    coin_type = int(node.network != "main")
    key_origin = f"[{path.format(fingerprint, coin_type, '{account}')}]"

    db = _load_db(DB_PATH / "accounts.json")
    n = int(db.get(key_origin, 0))
    db[key_origin] = n + 1
    if account is None or account == n:
        _save_db(DB_PATH / "accounts.json", db)
    elif account not in range(n):
        raise click.BadParameter(
            f"{key_origin} accounts are numbered from index `0` to `{n}` in sequentially increasing manner.",
            param_hint="--account",
        )
    account = n if account is None else account
    return path.format("m", coin_type, account), account


if __name__ == "__main__":
    cli()
