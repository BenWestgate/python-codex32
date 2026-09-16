"""Bitcoin wallet interoperability for validated master seeds."""

from typing import Literal, Protocol

from codex32._bip32 import _master_xprv_from_seed
from codex32.bech32 import _u5_to_chars
from codex32.checksums import DESCSUM
from codex32.profiles.ms32 import MasterSeed

_DESCRIPTOR_CHARSET = (
    "0123456789()[],'/*abcdefgh@:$%{}IJKLMNOPQRSTUVWXYZ&+-.;<=>?!^_|~ijklmnopqrstuvwxyzABCDEFGH`#\"\\ "
)
_TEMPLATES = (
    ("pkh({key})", 44),
    ("sh(wpkh({key}))", 49),
    ("wpkh({key})", 84),
    ("tr({key})", 86),
)


class WalletPublicDeriver(Protocol):
    """Out-of-process provider for EC-dependent BIP32 public derivation."""

    def fingerprint(self, secret: MasterSeed) -> bytes: ...

    def multisig_account_xpub(self, secret: MasterSeed, *, account: int = 0) -> str: ...

    def public_descriptors(
        self,
        secret: MasterSeed,
        *,
        account: int = 0,
        timestamp: int | Literal["now"] = 0,
    ) -> tuple[dict[str, object], ...]: ...


def _master(secret: MasterSeed) -> MasterSeed:
    if not isinstance(secret, MasterSeed):
        raise TypeError("wallet operations accept only MasterSeed")
    return secret


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
    """Return the root BIP32 extended private key with authority over all children."""
    return _master_xprv_from_seed(_master(secret).seed_bytes, testnet=testnet)


def multisig_account_xpub(
    secret: MasterSeed,
    *,
    integration: WalletPublicDeriver,
    account: int = 0,
) -> str:
    """Return a public BIP48 native-SegWit account key with its key origin."""
    _master(secret)
    account = _account(account)
    return integration.multisig_account_xpub(secret, account=account)


def core_descriptors(
    secret: MasterSeed,
    *,
    integration: WalletPublicDeriver | None = None,
    account: int = 0,
    testnet: bool = False,
    private: bool = False,
    timestamp: int | Literal["now"] = 0,
) -> tuple[dict[str, object], ...]:
    """Return fixed Bitcoin Core records.

    Private records are constructed with stdlib-only root xprv serialization.
    Public records require an explicit out-of-process integration provider.
    """
    _master(secret)
    account = _account(account)
    if not isinstance(testnet, bool):
        raise TypeError("testnet must be bool")
    if not isinstance(private, bool):
        raise TypeError("private must be bool")
    if timestamp != "now" and (
        isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0
    ):
        raise ValueError("timestamp must be a nonnegative integer or 'now'")
    if not private:
        if integration is None:
            raise TypeError("public descriptors require a wallet integration")
        return integration.public_descriptors(secret, account=account, timestamp=timestamp)
    coin_type = int(testnet)
    xprv = master_xprv(secret, testnet=testnet)
    records = []
    for template, purpose in _TEMPLATES:
        path = f"m/{purpose}h/{coin_type}h/{account}h"
        key = xprv + path[1:] + "/<0;1>/*"
        descriptor = template.format(key=key)
        records.append({"desc": _with_checksum(descriptor), "active": True, "timestamp": timestamp})
    return tuple(records)
