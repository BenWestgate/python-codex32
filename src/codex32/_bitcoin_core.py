from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import Literal

from codex32._bip32 import _master_xprv_from_seed
from codex32.profiles.ms32 import MasterSeed
from codex32.wallet import core_descriptors


class BitcoinCoreError(Exception):
    pass


_CHAINS = (
    ("main", "mainnet"),
    ("test", "testnet3"),
    ("testnet4", "testnet4"),
    ("signet", "signet"),
    ("regtest", "regtest"),
)

_ORIGIN_KEY = re.compile(
    r"\[(?P<fingerprint>[0-9a-f]{8})(?P<path>(?:/[0-9]+[h']?)*)\]"
    r"(?P<xpub>(?:xpub|tpub)[1-9A-HJ-NP-Za-km-z]+)"
)
_PRIVATE_MARKERS = ("xprv", "tprv")


@dataclass(frozen=True)
class BitcoinCore:
    executable: str
    chain: str
    version: int

    @classmethod
    def connect(
        cls,
        ask: Callable[[str], str] | None = None,
        tell: Callable[[str], None] | None = None,
    ) -> BitcoinCore:
        executable = shutil.which("bitcoin-cli")
        if executable is None:
            raise BitcoinCoreError("Install a reviewed bitcoin-cli before creating a backup.")
        choices: list[BitcoinCore] = []
        for chain, _label in _CHAINS:
            client = cls(executable, chain, 0)
            try:
                network = client._rpc("getnetworkinfo", timeout=5)
                blockchain = client._rpc("getblockchaininfo", timeout=5)
            except BitcoinCoreError:
                continue
            version = network.get("version") if isinstance(network, dict) else None
            reported = blockchain.get("chain") if isinstance(blockchain, dict) else None
            if isinstance(version, bool) or not isinstance(version, int) or reported != chain:
                continue
            if version >= 300000:
                choices.append(cls(executable, chain, version))
        if not choices:
            raise BitcoinCoreError(
                "No local Bitcoin Core RPC server found.\nStart Bitcoin Core "
                "with local RPC enabled.\nFor signet practice: bitcoin-qt -signet -server"
            )
        if len(choices) > 1:
            if ask is None or tell is None:
                raise BitcoinCoreError("More than one local Bitcoin Core network is running.")
            tell("Local Bitcoin Core networks:")
            for number, choice in enumerate(choices, 1):
                tell(f"  {number}. {dict(_CHAINS)[choice.chain]}")
            while not (
                (answer := ask("Choose a network number")).isdecimal() and 1 <= int(answer) <= len(choices)
            ):
                tell("Enter one of the displayed numbers.")
            choices = [choices[int(answer) - 1]]
        client = choices[0]
        if tell is not None:
            tell(f"Using Bitcoin Core on {dict(_CHAINS)[client.chain]}.")
        return client

    def _rpc(
        self,
        *arguments: str,
        wallet: str | None = None,
        stdin: str | None = None,
        timeout: int = 120,
    ) -> object:
        command = [self.executable, f"-chain={self.chain}", "-rpcconnect=127.0.0.1"]
        if wallet is not None:
            command.append(f"-rpcwallet={wallet}")
        if stdin is not None:
            command.append("-stdin")
        try:
            result = subprocess.run(
                [*command, *arguments],
                input=stdin,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BitcoinCoreError("The local Bitcoin Core command did not complete.") from error
        if result.returncode:
            raise BitcoinCoreError("Bitcoin Core rejected the requested wallet operation.")
        if not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise BitcoinCoreError("Bitcoin Core returned an unexpected response.") from error

    def _names(self) -> tuple[str, ...]:
        result = self._rpc("listwallets")
        if not isinstance(result, list) or not all(isinstance(name, str) for name in result):
            raise BitcoinCoreError("Unexpected Bitcoin Core wallet list.")
        return tuple(result)

    def _normalized_descriptor(self, descriptor: str) -> str:
        result = self._rpc("getdescriptorinfo", stdin=descriptor + "\n")
        normalized = result.get("descriptor") if isinstance(result, dict) else None
        if not isinstance(normalized, str) or any(marker in normalized for marker in _PRIVATE_MARKERS):
            raise BitcoinCoreError("Bitcoin Core did not return the expected public descriptor.")
        return normalized

    def _normalized_key(self, seed: bytes, path: str) -> tuple[bytes, str]:
        xprv = _master_xprv_from_seed(seed, testnet=self.chain != "main")
        normalized = self._normalized_descriptor(f"wpkh({xprv}{path})")
        match = _ORIGIN_KEY.search(normalized)
        if match is None:
            raise BitcoinCoreError("Bitcoin Core did not return the expected key origin.")
        origin_path = match.group("path").replace("'", "h")
        if origin_path != path:
            raise BitcoinCoreError("Bitcoin Core returned an unexpected derivation path.")
        return bytes.fromhex(match.group("fingerprint")), f"[{match.group('fingerprint')}{origin_path}]{match.group('xpub')}"

    def fingerprint_seed(self, seed: bytes) -> bytes:
        """Return the BIP32 master fingerprint using Bitcoin Core out of process."""
        fingerprint, _key = self._normalized_key(seed, "/0h")
        return fingerprint

    def fingerprint(self, secret: MasterSeed) -> bytes:
        """Return the BIP32 master fingerprint for a validated master seed."""
        if not isinstance(secret, MasterSeed):
            raise TypeError("wallet operations accept only MasterSeed")
        return self.fingerprint_seed(secret.seed_bytes)

    def multisig_account_xpub(self, secret: MasterSeed, *, account: int = 0) -> str:
        """Return the BIP48 native-SegWit account xpub with Core-derived origin."""
        if not isinstance(secret, MasterSeed):
            raise TypeError("wallet operations accept only MasterSeed")
        if isinstance(account, bool) or not isinstance(account, int) or not 0 <= account < 2**31:
            raise ValueError("account must be an integer from 0 through 2^31-1")
        path = f"/48h/{int(self.chain != 'main')}h/{account}h/2h"
        _fingerprint, key = self._normalized_key(secret.seed_bytes, path)
        return key

    def public_descriptors(
        self,
        secret: MasterSeed,
        *,
        account: int = 0,
        timestamp: int | Literal["now"] = 0,
    ) -> tuple[dict[str, object], ...]:
        """Normalize BIP44/49/84/86 private descriptors to public descriptors in Core."""
        private = core_descriptors(
            secret,
            account=account,
            testnet=self.chain != "main",
            private=True,
            timestamp=timestamp,
        )
        records: list[dict[str, object]] = []
        expected_fingerprint: bytes | None = None
        for purpose, record in zip((44, 49, 84, 86), private, strict=True):
            normalized = self._normalized_descriptor(str(record["desc"]).split("#", 1)[0])
            match = _ORIGIN_KEY.search(normalized)
            expected_path = f"/{purpose}h/{int(self.chain != 'main')}h/{account}h"
            if match is None or match.group("path").replace("'", "h") != expected_path:
                raise BitcoinCoreError("Bitcoin Core returned an unexpected descriptor key origin.")
            fingerprint = bytes.fromhex(match.group("fingerprint"))
            if expected_fingerprint is None:
                expected_fingerprint = fingerprint
            elif fingerprint != expected_fingerprint:
                raise BitcoinCoreError("Bitcoin Core returned inconsistent master fingerprints.")
            records.append({"desc": normalized, "active": True, "timestamp": timestamp})
        return tuple(records)

    def _target(self, name: str, *, private: bool = True) -> tuple[bool, bool] | None:
        listing, info = self._rpc("listdescriptors", wallet=name), self._rpc("getwalletinfo", wallet=name)
        if not isinstance(info, dict) or not isinstance(listing, dict):
            raise BitcoinCoreError("Unexpected Bitcoin Core wallet information.")
        eligible = (
            info.get("descriptors") is True
            and info.get("private_keys_enabled") is private
            and info.get("external_signer", False) is False
            and info.get("txcount") == 0
            and info.get("keypoolsize") == 0
            and info.get("keypoolsize_hd_internal", 0) == 0
            and info.get("scanning") is False
            and listing.get("descriptors") == []
            and name.isprintable()
        )
        unlocked = info.get("unlocked_until")
        return (unlocked is not None, unlocked == 0) if eligible else None

    def _select(
        self,
        ask: Callable[[str], str],
        tell: Callable[[str], None],
        *,
        private: bool = True,
    ) -> str:
        choices = tuple(
            name for name in sorted(self._names()) if self._target(name, private=private) is not None
        )
        if len(choices) == 1 and ask(f"Use blank wallet {json.dumps(choices[0])}? [y/N]").lower() in (
            "y",
            "yes",
        ):
            return choices[0]
        while True:
            if choices:
                tell("Eligible empty Bitcoin Core wallets:")
                for number, name in enumerate(choices, 1):
                    tell(f"  {number}. {json.dumps(name)}")
                tell(f"  {len(choices) + 1}. Create another wallet in Bitcoin Core")
                answer = ask("Choose a wallet number")
                if answer.isdecimal() and 1 <= int(answer) <= len(choices):
                    name = choices[int(answer) - 1]
                    if ask(f"Use blank wallet {json.dumps(name)}? [y/N]").lower() in (
                        "y",
                        "yes",
                    ):
                        return name
                    continue
                if answer != str(len(choices) + 1):
                    tell("Enter one of the displayed numbers.")
                    continue
            before = set(self._names())
            key_state = "enabled" if private else "disabled"
            tell(
                "In Bitcoin-Qt, choose File > Create Wallet... and create a blank descriptor wallet with "
                f"private keys {key_state}."
            )
            tell("Waiting; press Ctrl-C to stop.")
            while True:
                sleep(1)
                names = set(self._names())
                new = names - before
                appeared = tuple(
                    name for name in sorted(new) if self._target(name, private=private) is not None
                )
                if appeared:
                    break
            choices = tuple(name for name in sorted(names) if self._target(name, private=private) is not None)
            if len(appeared) == 1 and ask(f"Use blank wallet {json.dumps(appeared[0])}? [y/N]").lower() in (
                "y",
                "yes",
            ):
                return appeared[0]

    def initialize(
        self,
        secret: MasterSeed,
        ask: Callable[[str], str],
        tell: Callable[[str], None],
        *,
        private: bool = True,
        account: int = 0,
        timestamp: int | Literal["now"] = "now",
    ) -> str:
        while True:
            name = self._select(ask, tell, private=private)
            state = self._target(name, private=private)
            if state is None:
                tell("That wallet is no longer eligible. Choose again.")
                continue
            encrypted, locked = state
            relock = encrypted
            waited = False
            try:
                public = core_descriptors(
                    secret,
                    integration=self,
                    account=account,
                    testnet=self.chain != "main",
                    timestamp=timestamp,
                )
                expected: list[tuple[str, bool, bool]] = []
                for record in public:
                    detail = self._rpc("getdescriptorinfo", stdin=str(record["desc"]) + "\n")
                    expansion = detail.get("multipath_expansion") if isinstance(detail, dict) else None
                    if (
                        not isinstance(expansion, list)
                        or len(expansion) != 2
                        or not all(isinstance(descriptor, str) for descriptor in expansion)
                    ):
                        raise BitcoinCoreError("Bitcoin Core did not expand the expected public descriptors.")
                    expected.extend(
                        (descriptor, True, bool(position)) for position, descriptor in enumerate(expansion)
                    )
                while True:
                    if locked:
                        waited = True
                        tell(
                            "In Bitcoin-Qt, open Window > Console and select wallet "
                            f'{json.dumps(name)}.\nType: walletpassphrase "YOUR PASSPHRASE" 5\n'
                            "Waiting; press Ctrl-C to stop."
                        )
                    while locked:
                        sleep(1)
                        state = self._target(name, private=private)
                        if state is None:
                            break
                        encrypted, locked = state
                        relock = relock or encrypted
                    if state is None:
                        break
                    state = self._target(name, private=private)
                    if state is None:
                        raise BitcoinCoreError("The selected wallet changed before import.")
                    current_encrypted, locked = state
                    relock = relock or current_encrypted
                    if not locked:
                        break
                if state is None:
                    tell("That wallet is no longer eligible. Choose again.")
                    continue
                records = core_descriptors(
                    secret,
                    account=account,
                    testnet=self.chain != "main",
                    private=private,
                    timestamp=timestamp,
                )
                imported = self._rpc(
                    "importdescriptors",
                    wallet=name,
                    stdin=json.dumps(records, separators=(",", ":")) + "\n",
                )
                del records
                valid = (
                    isinstance(imported, list)
                    and len(imported) == 4
                    and all(isinstance(item, dict) and item.get("success") is True for item in imported)
                )
                if not valid:
                    raise BitcoinCoreError(
                        f"Bitcoin Core did not import every {'private' if private else 'public'} descriptor."
                    )
                listed = self._rpc("listdescriptors", wallet=name)
                values = listed.get("descriptors") if isinstance(listed, dict) else None
                if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
                    raise BitcoinCoreError("Bitcoin Core did not return the imported public descriptors.")
                actual = [
                    (
                        str(item.get("desc")),
                        item.get("active") is True,
                        item.get("internal") is True,
                    )
                    for item in values
                ]
                if sorted(actual) != sorted(expected):
                    raise BitcoinCoreError("Bitcoin Core's accepted public descriptors did not match.")
            finally:
                warning = "Confirm immediately in Bitcoin Core that the wallet is locked."
                while relock:
                    try:
                        self._rpc("walletlock", wallet=name)
                        info = self._rpc("getwalletinfo", wallet=name)
                    except KeyboardInterrupt:
                        continue
                    except BitcoinCoreError as error:
                        raise BitcoinCoreError(warning) from error
                    if not isinstance(info, dict) or info.get("unlocked_until") != 0:
                        raise BitcoinCoreError(warning)
                    relock = False
            if waited:
                tell("")
            return name
