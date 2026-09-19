"""Every Bitcoin Core interaction this program performs, including the passphrase.

`docs/security/invariants.md` invariant 9 states that codex32 has no passphrase
channel, and the library still has none: it tells the operator to unlock the
wallet in Bitcoin-Qt. The graphical program declares one deliberate exception,
confined to this file, because a person who has just written three cards by hand
should not have to open a second application and type a console command.

The passphrase reaches `bitcoin-cli` through `-stdinwalletpassphrase` and
`-stdin`, never through a command argument, so it is absent from `/proc` and
`ps`. It is never stored, never logged, and never written to disk. Import,
verification, and relocking remain the library's `BitcoinCore.initialize`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from codex32 import MasterSeed
from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError

__all__ = [
    "UNLOCK_SECONDS",
    "BitcoinCore",
    "BitcoinCoreError",
    "Offer",
    "Wallet",
    "connect",
    "create",
    "eligible",
    "fingerprint",
    "fingerprint_provider",
    "initialize",
    "network",
    "require_unlocked",
    "unlock",
    "version_text",
]

UNLOCK_SECONDS = 180
_WAITING = "press Ctrl-C to stop."
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


class Offer(BitcoinCoreError):
    """The library asked the operator to choose, and no choice has been made yet."""

    def __init__(self, options: tuple[str, ...]) -> None:
        super().__init__("Bitcoin Core no longer offers that choice. Look at the list again.")
        self.options = options


def _name(text: str) -> str | None:
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, str) else None


class _Answer:
    """Answer one library selection prompt with the choice the operator already made.

    The library prompts in free text. Nothing here guesses. A wallet is accepted
    only when the prompt names it exactly, and any prompt this cannot answer from
    the operator's choice raises `Offer` so that the choice is made on screen.
    """

    def __init__(self, chosen: str | None, *, quoted: bool) -> None:
        self._chosen, self._quoted = chosen, quoted
        self._listed: list[str] = []
        self._numbered = False

    def tell(self, message: str) -> None:
        if message.rstrip().endswith(_WAITING):
            raise BitcoinCoreError(
                "Bitcoin Core is waiting for something to be done in its own window. "
                "Check that the wallet is still empty and unlocked, then try again."
            )
        number, _, rest = message.strip().partition(". ")
        if not number.isdecimal() or not rest:
            return
        decoded = _name(rest) if _QUOTED.fullmatch(rest) else None
        if self._quoted == (decoded is not None):
            self._listed.append(rest if decoded is None else decoded)

    def ask(self, prompt: str) -> str:
        quoted = _QUOTED.search(prompt)
        if quoted is not None:
            return "y" if _name(quoted.group()) == self._chosen else "n"
        if not self._numbered and self._chosen is not None and self._chosen in self._listed:
            self._numbered = True
            return str(self._listed.index(self._chosen) + 1)
        raise Offer(tuple(dict.fromkeys(self._listed)))


@dataclass(frozen=True, slots=True)
class Wallet:
    """One Bitcoin Core wallet that codex32 is willing to fill."""

    name: str
    encrypted: bool
    locked: bool


def connect(chain: str | None = None) -> BitcoinCore:
    """Discover local Bitcoin Core before any entropy or recovery input is taken."""
    answer = _Answer(chain, quoted=False)
    return BitcoinCore.connect(answer.ask, answer.tell)


def network(core: BitcoinCore) -> str:
    """Return the chain this connection selected."""
    return core.chain


def fingerprint(core: BitcoinCore, secret: MasterSeed) -> str:
    """Return the BIP32 master fingerprint, derived by Bitcoin Core out of process."""
    return core.fingerprint(secret).hex()


def fingerprint_provider(core: BitcoinCore) -> Callable[[bytes], bytes]:
    """Hand the library the same out-of-process derivation for a raw seed."""
    return core.fingerprint_seed


def version_text(core: BitcoinCore) -> str:
    """Return the running Bitcoin Core version the way its own about box does."""
    return f"{core.version // 10000}.{core.version // 100 % 100}.{core.version % 100}"


def eligible(core: BitcoinCore) -> tuple[Wallet, ...]:
    """List the empty descriptor wallets Bitcoin Core would accept an import into."""
    found = []
    for name in sorted(core._names()):
        state = core._target(name)
        if state is not None:
            found.append(Wallet(name, state[0], state[1]))
    return tuple(found)


def _wallet_name(name: str) -> str:
    """Accept only names Bitcoin Core can carry on one standard-input line."""
    if not name or name != name.strip() or not name.isprintable():
        raise BitcoinCoreError("A wallet name must be printable text without leading or trailing spaces.")
    return name


def _passphrase(passphrase: str) -> str:
    """Accept only passphrases that survive the one-argument-per-line channel."""
    if not passphrase or "\n" in passphrase or "\r" in passphrase:
        raise BitcoinCoreError("A wallet passphrase cannot be empty or contain a line break.")
    return passphrase


def create(core: BitcoinCore, name: str, passphrase: str) -> None:
    """Create one blank descriptor wallet with private keys enabled, and nothing else."""
    arguments = [f"wallet_name={_wallet_name(name)}", "disable_private_keys=false", "blank=true"]
    if passphrase:
        arguments.append(f"passphrase={_passphrase(passphrase)}")
    try:
        core._rpc("-named", "createwallet", stdin="\n".join(arguments) + "\n")
    except BitcoinCoreError as error:
        raise BitcoinCoreError(
            "Bitcoin Core would not create a wallet with that name. A wallet of that name may exist already."
        ) from error
    if core._target(name) is None:
        raise BitcoinCoreError("Bitcoin Core did not create an empty wallet that codex32 can fill.")


def unlock(core: BitcoinCore, name: str, passphrase: str) -> None:
    """Unlock one wallet with a passphrase that only ever travels on standard input."""
    line = _passphrase(passphrase) + "\n"
    try:
        core._rpc(
            "-stdinwalletpassphrase",
            "walletpassphrase",
            str(UNLOCK_SECONDS),
            wallet=name,
            stdin=line,
        )
    except BitcoinCoreError as error:
        raise BitcoinCoreError("Bitcoin Core did not accept that passphrase.") from error
    state = core._target(name)
    if state is None or state[1]:
        raise BitcoinCoreError("Bitcoin Core did not accept that passphrase.")


def require_unlocked(core: BitcoinCore, name: str) -> None:
    """Confirm the operator unlocked the wallet in Bitcoin Core themselves."""
    state = [item for item in eligible(core) if item.name == name]
    if not state or state[0].locked:
        raise BitcoinCoreError("That wallet is still locked in Bitcoin Core.")


def initialize(
    core: BitcoinCore,
    secret: MasterSeed,
    name: str,
    *,
    account: int = 0,
    timestamp: int | Literal["now"] = "now",
) -> str:
    """Hand the library the wallet the operator named, and let it do the import."""
    answer = _Answer(name, quoted=True)
    return core.initialize(secret, answer.ask, answer.tell, account=account, timestamp=timestamp)
