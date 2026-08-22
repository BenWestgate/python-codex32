"""Stateless Bitcoin wallet interoperability for validated master seeds."""

from bip32 import BIP32

from codex32.bech32 import _u5_to_chars
from codex32.bip93 import MasterSeed
from codex32.checksums import DESCSUM

_DESCRIPTOR_CHARSET = (
    "0123456789()[],'/*abcdefgh@:$%{}IJKLMNOPQRSTUVWXYZ&+-.;<=>?!^_|~"
    'ijklmnopqrstuvwxyzABCDEFGH`#"\\ '
)
_TEMPLATES = (
    ("pkh({key})", 44),
    ("sh(wpkh({key}))", 49),
    ("wpkh({key})", 84),
    ("tr({key})", 86),
)


def _master(secret: MasterSeed, testnet: bool) -> BIP32:
    if not isinstance(secret, MasterSeed):
        raise TypeError("wallet operations accept only MasterSeed")
    if not isinstance(testnet, bool):
        raise TypeError("testnet must be bool")
    return BIP32.from_seed(secret.seed_bytes, "test" if testnet else "main")


def _account(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
        raise ValueError("account must be an integer from 0 through 2^31-1")
    return value


def _descriptor_symbols(text: str) -> list[int]:
    groups: list[int] = []
    symbols: list[int] = []
    for character in text:
        position = _DESCRIPTOR_CHARSET.find(character)
        if position < 0:
            raise ValueError(f"unsupported descriptor character {character!r}")
        symbols.append(position & 31)
        groups.append(position >> 5)
        if len(groups) == 3:
            symbols.append(groups[0] * 9 + groups[1] * 3 + groups[2])
            groups.clear()
    if groups:
        symbols.append(groups[0] if len(groups) == 1 else groups[0] * 3 + groups[1])
    return symbols


def _with_checksum(descriptor: str) -> str:
    return descriptor + "#" + _u5_to_chars(DESCSUM.create(_descriptor_symbols(descriptor)))


def master_xprv(secret: MasterSeed, *, testnet: bool = False) -> str:
    """Return the BIP32 master extended private key."""
    return str(_master(secret, testnet).get_xpriv())


def multisig_account_xpub(
    secret: MasterSeed,
    *,
    account: int = 0,
    testnet: bool = False,
) -> str:
    """Return a BIP48 native-SegWit account xpub with key origin."""
    node = _master(secret, testnet)
    account = _account(account)
    coin_type = int(testnet)
    path = f"m/48h/{coin_type}h/{account}h/2h"
    origin = f"{node.get_fingerprint().hex()}{path[1:]}"
    return f"[{origin}]{node.get_xpub_from_path(path)}"


def core_descriptors(
    secret: MasterSeed,
    *,
    account: int = 0,
    testnet: bool = False,
    private: bool = False,
    timestamp: int = 0,
) -> tuple[dict[str, object], ...]:
    """Return fixed single-key Bitcoin Core importdescriptors records."""
    node = _master(secret, testnet)
    account = _account(account)
    if not isinstance(private, bool):
        raise TypeError("private must be bool")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
        raise ValueError("timestamp must be a nonnegative integer")
    coin_type = int(testnet)
    fingerprint = node.get_fingerprint().hex()
    records = []
    for template, purpose in _TEMPLATES:
        path = f"m/{purpose}h/{coin_type}h/{account}h"
        if private:
            key = node.get_xpriv() + path[1:] + "/<0;1>/*"
        else:
            origin = f"{fingerprint}{path[1:]}"
            key = f"[{origin}]{node.get_xpub_from_path(path)}/<0;1>/*"
        descriptor = template.format(key=key)
        records.append(
            {
                "desc": _with_checksum(descriptor),
                "active": True,
                "timestamp": timestamp,
            }
        )
    return tuple(records)
