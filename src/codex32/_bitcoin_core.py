# fmt: off
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import Literal

from codex32.profiles.ms32 import MasterSeed
from codex32.wallet import core_descriptors


class BitcoinCoreError(Exception): pass

_CHAINS = (("main", "mainnet"), ("test", "testnet3"), ("testnet4", "testnet4"),
           ("signet", "signet"), ("regtest", "regtest"))


@dataclass(frozen=True)
class BitcoinCore:
    executable: str; chain: str; version: int

    @classmethod
    def connect(cls, ask: Callable[[str], str] | None = None,
                tell: Callable[[str], None] | None = None) -> BitcoinCore:
        executable = shutil.which("bitcoin-cli")
        if executable is None: raise BitcoinCoreError("Install a reviewed bitcoin-cli before creating a backup.")
        choices: list[BitcoinCore] = []
        for chain, _label in _CHAINS:
            client = cls(executable, chain, 0)
            try: network = client._rpc("getnetworkinfo", timeout=5); blockchain = client._rpc(
                "getblockchaininfo", timeout=5)
            except BitcoinCoreError: continue
            version = network.get("version") if isinstance(network, dict) else None
            reported = blockchain.get("chain") if isinstance(blockchain, dict) else None
            if isinstance(version, bool) or not isinstance(version, int) or reported != chain: continue
            if version >= 300000: choices.append(cls(executable, chain, version))
        if not choices: raise BitcoinCoreError("No local Bitcoin Core RPC server found.\nStart Bitcoin Core "
            "with local RPC enabled.\nFor signet practice: bitcoin-qt -signet -server")
        if len(choices) > 1:
            if ask is None or tell is None: raise BitcoinCoreError(
                "More than one local Bitcoin Core network is running.")
            tell("Local Bitcoin Core networks:")
            for number, choice in enumerate(choices, 1): tell(f"  {number}. {dict(_CHAINS)[choice.chain]}")
            while not ((answer := ask("Choose a network number")).isdecimal()
                       and 1 <= int(answer) <= len(choices)): tell("Enter one of the displayed numbers.")
            choices = [choices[int(answer) - 1]]
        client = choices[0]
        if tell is not None: tell(f"Using Bitcoin Core on {dict(_CHAINS)[client.chain]}.")
        return client

    def _rpc(self, *arguments: str, wallet: str | None = None, stdin: str | None = None,
             timeout: int = 120) -> object:
        command = [self.executable, f"-chain={self.chain}", "-rpcconnect=127.0.0.1"]
        if wallet is not None: command.append(f"-rpcwallet={wallet}")
        if stdin is not None: command.append("-stdin")
        try: result = subprocess.run([*command, *arguments], input=stdin, text=True,
                                     capture_output=True, check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BitcoinCoreError("The local Bitcoin Core command did not complete.") from error
        if result.returncode: raise BitcoinCoreError("Bitcoin Core rejected the requested wallet operation.")
        if not result.stdout.strip(): return None
        try: return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise BitcoinCoreError("Bitcoin Core returned an unexpected response.") from error

    def _names(self) -> tuple[str, ...]:
        result = self._rpc("listwallets")
        if not isinstance(result, list) or not all(isinstance(name, str) for name in result): raise BitcoinCoreError(
            "Unexpected Bitcoin Core wallet list.")
        return tuple(result)

    def _target(self, name: str, *, private: bool = True) -> tuple[bool, bool] | None:
        listing, info = self._rpc("listdescriptors", wallet=name), self._rpc("getwalletinfo", wallet=name)
        if not isinstance(info, dict) or not isinstance(listing, dict):
            raise BitcoinCoreError("Unexpected Bitcoin Core wallet information.")
        eligible = (
            info.get("descriptors") is True and info.get("private_keys_enabled") is private
            and info.get("external_signer", False) is False and info.get("txcount") == 0
            and info.get("keypoolsize") == 0 and info.get("keypoolsize_hd_internal", 0) == 0
            and info.get("scanning") is False and listing.get("descriptors") == [] and name.isprintable()
        )
        unlocked = info.get("unlocked_until")
        return (unlocked is not None, unlocked == 0) if eligible else None

    def _select(self, ask: Callable[[str], str], tell: Callable[[str], None], *,
                private: bool = True) -> str:
        choices = tuple(name for name in sorted(self._names()) if self._target(name, private=private) is not None)
        if len(choices) == 1 and ask(f"Use blank wallet {json.dumps(choices[0])}? [y/N]").lower() in (
            "y", "yes"
        ): return choices[0]
        while True:
            if choices:
                tell("Eligible empty Bitcoin Core wallets:")
                for number, name in enumerate(choices, 1): tell(f"  {number}. {json.dumps(name)}")
                tell(f"  {len(choices) + 1}. Create another wallet in Bitcoin Core")
                answer = ask("Choose a wallet number")
                if answer.isdecimal() and 1 <= int(answer) <= len(choices):
                    name = choices[int(answer) - 1]
                    if ask(f"Use blank wallet {json.dumps(name)}? [y/N]").lower() in ("y", "yes"): return name
                    continue
                if answer != str(len(choices) + 1): tell("Enter one of the displayed numbers."); continue
            before = set(self._names()); key_state = "enabled" if private else "disabled"
            tell("In Bitcoin-Qt, choose File > Create Wallet... and create a blank descriptor wallet with "
                 f"private keys {key_state}.")
            tell("Waiting; press Ctrl-C to stop.")
            while True:
                sleep(1); names = set(self._names()); new = names - before
                appeared = tuple(name for name in sorted(new) if self._target(name, private=private) is not None)
                if appeared: break
            choices = tuple(name for name in sorted(names) if self._target(name, private=private) is not None)
            if len(appeared) == 1 and ask(f"Use blank wallet {json.dumps(appeared[0])}? [y/N]").lower() in (
                "y", "yes"
            ): return appeared[0]

    def initialize(self, secret: MasterSeed, ask: Callable[[str], str], tell: Callable[[str], None], *,
                   private: bool = True, account: int = 0, timestamp: int | Literal["now"] = "now") -> str:
        while True:
            name = self._select(ask, tell, private=private)
            state = self._target(name, private=private)
            if state is None: tell("That wallet is no longer eligible. Choose again."); continue
            encrypted, locked = state; relock = encrypted
            try:
                public = core_descriptors(secret, account=account, testnet=self.chain != "main", timestamp=timestamp)
                expected: list[tuple[str, bool, bool]] = []
                for record in public:
                    detail = self._rpc("getdescriptorinfo", stdin=str(record["desc"]) + "\n")
                    expansion = detail.get("multipath_expansion") if isinstance(detail, dict) else None
                    if not isinstance(expansion, list) or len(expansion) != 2 or not all(
                        isinstance(descriptor, str) for descriptor in expansion):
                        raise BitcoinCoreError("Bitcoin Core did not expand the expected public descriptors.")
                    expected.extend((descriptor, True, bool(position))
                                    for position, descriptor in enumerate(expansion))
                while True:
                    if locked: tell(
                        "In Bitcoin-Qt, open Window > Console and select wallet "
                        f"{json.dumps(name)}.\nType: walletpassphrase \"YOUR PASSPHRASE\" 5\n"
                        "Waiting; press Ctrl-C to stop.")
                    while locked:
                        sleep(1); state = self._target(name, private=private)
                        if state is None: break
                        encrypted, locked = state; relock = relock or encrypted
                    if state is None: break
                    state = self._target(name, private=private)
                    if state is None: raise BitcoinCoreError("The selected wallet changed before import.")
                    current_encrypted, locked = state; relock = relock or current_encrypted
                    if not locked: break
                if state is None: tell("That wallet is no longer eligible. Choose again."); continue
                records = core_descriptors(secret, account=account, testnet=self.chain != "main", private=private,
                                           timestamp=timestamp)
                imported = self._rpc("importdescriptors", wallet=name,
                    stdin=json.dumps(records, separators=(",", ":")) + "\n"); del records
                valid = isinstance(imported, list) and len(imported) == 4 and all(isinstance(item, dict)
                    and item.get("success") is True for item in imported)
                if not valid: raise BitcoinCoreError(
                    f"Bitcoin Core did not import every {'private' if private else 'public'} descriptor.")
                listed = self._rpc("listdescriptors", wallet=name)
                values = listed.get("descriptors") if isinstance(listed, dict) else None
                if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
                    raise BitcoinCoreError("Bitcoin Core did not return the imported public descriptors.")
                actual = [(str(item.get("desc")), item.get("active") is True, item.get("internal") is True)
                          for item in values]
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
