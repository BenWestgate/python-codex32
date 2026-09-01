# fmt: off
"""Private, subprocess-only adapter for initializing an empty Bitcoin Core wallet."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from codex32.profiles.ms32 import MasterSeed
from codex32.wallet import core_descriptors


class BitcoinCoreError(Exception): pass


@dataclass(frozen=True)
class BitcoinCore:
    executable: str; chain: str; version: int

    @classmethod
    def connect(cls) -> BitcoinCore:
        executable = shutil.which("bitcoin-cli")
        if executable is None: raise BitcoinCoreError("Install a reviewed bitcoin-cli before creating a backup.")
        client = cls(executable, "", 0)
        network, blockchain = client._rpc("getnetworkinfo"), client._rpc("getblockchaininfo")
        version = network.get("version") if isinstance(network, dict) else None
        chain = blockchain.get("chain") if isinstance(blockchain, dict) else None
        if isinstance(version, bool) or not isinstance(version, int) or version < 300000:
            raise BitcoinCoreError("Bitcoin Core 30 or newer is required.")
        if chain not in ("main", "test", "testnet4", "signet", "regtest"):
            raise BitcoinCoreError("Bitcoin Core returned an unsupported chain.")
        return cls(executable, chain, version)

    def _rpc(self, *arguments: str, wallet: str | None = None, stdin: str | None = None) -> object:
        command = [self.executable, "-rpcconnect=127.0.0.1"]
        if wallet is not None: command.append(f"-rpcwallet={wallet}")
        if stdin is not None: command.append("-stdin")
        try:
            result = subprocess.run(
                [*command, *arguments], input=stdin, text=True, capture_output=True, check=False, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BitcoinCoreError("The local Bitcoin Core command did not complete.") from error
        if result.returncode: raise BitcoinCoreError("Bitcoin Core rejected the requested wallet operation.")
        if not result.stdout.strip(): return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise BitcoinCoreError("Bitcoin Core returned an unexpected response.") from error

    def _names(self) -> tuple[str, ...]:
        result = self._rpc("listwallets")
        if not isinstance(result, list) or not all(isinstance(name, str) for name in result):
            raise BitcoinCoreError("Unexpected listwallets response.")
        return tuple(result)

    def _target(self, name: str) -> tuple[bool, bool] | None:
        listing, info = self._rpc("listdescriptors", wallet=name), self._rpc("getwalletinfo", wallet=name)
        if not isinstance(info, dict) or not isinstance(listing, dict):
            raise BitcoinCoreError("Unexpected Bitcoin Core wallet information.")
        eligible = (
            info.get("descriptors") is True and info.get("private_keys_enabled") is True
            and info.get("external_signer", False) is False and info.get("txcount") == 0
            and info.get("keypoolsize") == 0 and info.get("keypoolsize_hd_internal", 0) == 0
            and info.get("scanning") is False and listing.get("descriptors") == [] and name.isprintable()
        )
        if not eligible: return None
        unlocked = info.get("unlocked_until")
        return unlocked is not None, unlocked == 0

    def _select(self, ask: Callable[[str], str], tell: Callable[[str], None]) -> str:
        choices = tuple(name for name in sorted(self._names()) if self._target(name) is not None)
        while True:
            if choices:
                tell("Eligible empty Bitcoin Core wallets:")
                for number, name in enumerate(choices, 1): tell(f"  {number}. {json.dumps(name)}")
                tell(f"  {len(choices) + 1}. Create another wallet in Bitcoin Core")
                answer = ask("Choose a wallet number")
                if answer.isdecimal() and 1 <= int(answer) <= len(choices):
                    name = choices[int(answer) - 1]
                    if ask(f"Use wallet {json.dumps(name)}? [y/N]").lower() in ("y", "yes"):
                        return name
                    continue
                if answer != str(len(choices) + 1):
                    tell("Enter one of the displayed numbers.")
                    continue
            before = set(self._names())
            tell("Create a blank descriptor wallet with private keys enabled in Bitcoin Core.")
            ask("Press Enter after the new wallet is loaded")
            choices = tuple(name for name in sorted(set(self._names()) - before)
                            if self._target(name) is not None)
            if not choices: tell("No new eligible wallet appeared. Check it in Bitcoin Core and try again.")

    def initialize(self, secret: MasterSeed, ask: Callable[[str], str], tell: Callable[[str], None]) -> str:
        while True:
            name = self._select(ask, tell)
            state = self._target(name)
            if state is None:
                tell("That wallet changed and is no longer eligible. Choose again.")
                continue
            encrypted, locked = state
            relock = encrypted
            try:
                while locked:
                    tell(f"Unlock wallet {json.dumps(name)} in Bitcoin Core; codex32 never reads its passphrase.")
                    ask("Press Enter to retry")
                    state = self._target(name)
                    if state is None: break
                    encrypted, locked = state; relock = relock or encrypted
                if state is None: continue
                public = core_descriptors(secret, testnet=self.chain != "main", timestamp="now")
                expected: list[tuple[str, bool, bool]] = []
                for record in public:
                    detail = self._rpc("getdescriptorinfo", stdin=str(record["desc"]) + "\n")
                    expansion = detail.get("multipath_expansion") if isinstance(detail, dict) else None
                    if not isinstance(expansion, list) or len(expansion) != 2 or not all(
                        isinstance(descriptor, str) for descriptor in expansion
                    ):
                        raise BitcoinCoreError("Bitcoin Core did not expand the expected public descriptors.")
                    expected.extend((descriptor, True, bool(position))
                                    for position, descriptor in enumerate(expansion))
                state = self._target(name)
                if state is None: raise BitcoinCoreError("The selected wallet changed before import.")
                current_encrypted, locked = state
                relock = relock or current_encrypted
                if locked:
                    tell(f"Unlock wallet {json.dumps(name)} in Bitcoin Core, then retry wallet setup.")
                    continue
                records = core_descriptors(secret, testnet=self.chain != "main", private=True, timestamp="now")
                imported = self._rpc("importdescriptors", wallet=name,
                                     stdin=json.dumps(records, separators=(",", ":")) + "\n")
                del records
                valid = isinstance(imported, list) and len(imported) == 4 and all(
                    isinstance(item, dict) and item.get("success") is True for item in imported)
                if not valid:
                    raise BitcoinCoreError("Bitcoin Core did not import every private descriptor.")
                listed = self._rpc("listdescriptors", wallet=name)
                values = listed.get("descriptors") if isinstance(listed, dict) else None
                if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
                    raise BitcoinCoreError("Bitcoin Core did not return the imported public descriptors.")
                actual = [(str(item.get("desc")), item.get("active") is True,
                           item.get("internal") is True) for item in values]
                if sorted(actual) != sorted(expected):
                    raise BitcoinCoreError("Bitcoin Core's accepted public descriptors did not match.")
            finally:
                warning = "Confirm immediately in Bitcoin Core that the wallet is locked."
                while relock:
                    try: self._rpc("walletlock", wallet=name); info = self._rpc("getwalletinfo", wallet=name)
                    except KeyboardInterrupt: continue
                    except BitcoinCoreError as error: raise BitcoinCoreError(warning) from error
                    if not isinstance(info, dict) or info.get("unlocked_until") != 0: raise BitcoinCoreError(warning)
                    relock = False
            return name
