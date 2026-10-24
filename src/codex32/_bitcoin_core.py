from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import Literal

from codex32._bip32 import _master_xprv_from_seed
from codex32.bech32 import _u5_to_chars, convertbits
from codex32.generation import _fingerprint_identifier
from codex32.profiles.ms32 import MasterSeed


class BitcoinCoreError(Exception):
    pass


class FingerprintMismatch(BitcoinCoreError):
    """The recovered seed is not the wallet the operator's record describes."""


_CHAINS = (
    ("main", "mainnet"),
    ("test", "testnet3"),
    ("testnet4", "testnet4"),
    ("signet", "signet"),
    ("regtest", "regtest"),
)

_PRIVATE_MARKERS = ("xprv", "tprv")
_OUTPUT_TYPES = ("legacy", "p2sh-segwit", "bech32", "bech32m")


def parse_fingerprint(text: str) -> bytes:
    """Read a master fingerprint as written on a wallet record: 8 hex digits, any case or spacing."""
    compact = "".join(text.split())
    if len(compact) != 8 or not all(character in string.hexdigits for character in compact):
        raise ValueError("A master fingerprint is 8 characters, each 0-9 or A-F.")
    return bytes.fromhex(compact)


NO_RECORD_WARNING = (
    "Without the wallet record, nothing can prove these cards are the wallet you expect. Compare the "
    "fingerprint with any other copy, such as a watch-only wallet or a descriptor backup. "
    "After restoring, let Bitcoin Core finish scanning and check that the balance, past payments and "
    "addresses are ones you recognise before sending money here. Replaced cards can come with a history "
    "too: if you do not know what this wallet should hold, have someone you trust check it. Once you are "
    "sure, write the fingerprint on a new wallet record."
)


def identifier_note(origin: str | None) -> str:
    # Say what `identifier_origin` found, for an operator restoring without a record.
    if origin is None:
        return (
            "The backup identifier was not made from this seed. That can be normal for codex32 backups "
            "made from split shares, supplied seed bytes or an explicit identifier. Bails made every "
            "identifier from its seed, so for a Bails backup these are the wrong or mixed-up cards."
        )
    return (
        f"The backup identifier matches this seed ({origin} rule). That rules out most mixed-up cards, "
        "but not cards replaced on purpose."
    )


def identifier_origin(secret: MasterSeed, fingerprint: bytes) -> str | None:
    """Check codex32's fingerprint or Bails' three-character seed-digest identifier."""
    identifier = secret.header.identifier
    if identifier == _fingerprint_identifier(fingerprint):
        return "codex32"
    for name, digest in (("Bails", "ripemd160"), ("Bails alpha", "sha256")):
        try:
            hashed = hashlib.new(digest, secret.seed_bytes).digest()
        except ValueError:
            continue
        derived = convertbits(hashed, 8, 5, pad=True)
        if identifier[:3] == _u5_to_chars(tuple(derived[:3])):
            return name
    return None


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
            raise BitcoinCoreError(
                "bitcoin-cli was not found. Install a reviewed Bitcoin Core 32 or newer and run it with RPC "
                "enabled. An unsynced regtest or signet node is enough for practice."
            )
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
            if version >= 320000:
                choices.append(cls(executable, chain, version))
        if not choices:
            raise BitcoinCoreError(
                "No local Bitcoin Core 32 or newer RPC server found.\nStart Bitcoin Core "
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

    def fingerprint_seed(self, seed: bytes) -> bytes:
        """Return the BIP32 master fingerprint using Bitcoin Core out of process."""
        xprv = _master_xprv_from_seed(seed, testnet=self.chain != "main")
        descriptor = self._normalized_descriptor(f"pkh({xprv})")
        addresses = self._rpc("deriveaddresses", stdin=descriptor + "\n")
        if not isinstance(addresses, list) or len(addresses) != 1 or not isinstance(addresses[0], str):
            raise BitcoinCoreError("Bitcoin Core did not derive the expected master-key address.")
        decoded = self._rpc("validateaddress", addresses[0])
        script = decoded.get("scriptPubKey") if isinstance(decoded, dict) else None
        if (
            not isinstance(script, str)
            or len(script) != 50
            or not script.startswith("76a914")
            or not script.endswith("88ac")
        ):
            raise BitcoinCoreError("Bitcoin Core did not return the expected master-key script.")
        try:
            return bytes.fromhex(script[6:14])
        except ValueError as error:
            raise BitcoinCoreError("Bitcoin Core returned an invalid master-key script.") from error

    def fingerprint(self, secret: MasterSeed) -> bytes:
        """Return the BIP32 master fingerprint for a validated master seed."""
        if not isinstance(secret, MasterSeed):
            raise TypeError("wallet operations accept only MasterSeed")
        return self.fingerprint_seed(secret.seed_bytes)

    def verify_identity(self, secret: MasterSeed, expected_fingerprint: bytes | None) -> None:
        """Refuse a recovered seed that is not the recorded wallet before any wallet is touched."""
        if expected_fingerprint is not None and self.fingerprint(secret) != expected_fingerprint:
            raise FingerprintMismatch(
                "The recovered master fingerprint does not match the one from the wallet record. "
                "Bitcoin Core was not changed."
            )

    def _target(self, name: str) -> tuple[bool, bool] | None:
        listing, info = self._rpc("listdescriptors", wallet=name), self._rpc("getwalletinfo", wallet=name)
        if not isinstance(info, dict) or not isinstance(listing, dict):
            raise BitcoinCoreError("Unexpected Bitcoin Core wallet information.")
        eligible = (
            info.get("descriptors") is True
            and info.get("private_keys_enabled") is True
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

    def _create_account_zero(self, secret: MasterSeed, wallet: str) -> None:
        root = _master_xprv_from_seed(secret.seed_bytes, testnet=self.chain != "main")
        added = self._rpc("addhdkey", wallet=wallet, stdin=root + "\n")
        xpub = added.get("xpub") if isinstance(added, dict) else None
        if not isinstance(xpub, str) or not xpub.startswith("xpub" if self.chain == "main" else "tpub"):
            raise BitcoinCoreError("Bitcoin Core did not accept the master HD key.")
        options = json.dumps({"hdkey": xpub}, separators=(",", ":"))
        for output_type in _OUTPUT_TYPES:
            created = self._rpc(
                "-named", "createwalletdescriptor", f"type={output_type}", f"options={options}", wallet=wallet
            )
            descriptors = created.get("descs") if isinstance(created, dict) else None
            if (
                not isinstance(descriptors, list)
                or len(descriptors) != 2
                or not all(
                    isinstance(desc, str) and not any(key in desc for key in _PRIVATE_MARKERS)
                    for desc in descriptors
                )
            ):
                raise BitcoinCoreError("Bitcoin Core did not create both wallet descriptors.")

    def _rescan_from_timestamp(self, wallet: str, timestamp: int) -> None:
        # createwalletdescriptor has no timestamp option. Re-import one of its
        # existing active descriptors so Core applies its own two-hour time
        # window and scans the whole wallet, without guessing a block height.
        listing = self._rpc("listdescriptors", "true", wallet=wallet)
        records = listing.get("descriptors") if isinstance(listing, dict) else None
        if not isinstance(records, list):
            raise BitcoinCoreError("Bitcoin Core did not list the wallet descriptors.")
        candidates = [
            record
            for record in records
            if isinstance(record, dict) and record.get("active") is True and record.get("internal") is False
        ]
        if len(candidates) != len(_OUTPUT_TYPES):
            raise BitcoinCoreError("Bitcoin Core did not return the expected receiving descriptors.")
        descriptor = candidates[0]
        private = descriptor.get("desc")
        span = descriptor.get("range")
        next_index = descriptor.get("next_index")
        if (
            not isinstance(private, str)
            or not any(marker in private for marker in _PRIVATE_MARKERS)
            or not isinstance(span, list)
            or len(span) != 2
            or any(type(bound) is not int for bound in span)
            or type(next_index) is not int
            or not span[0] <= next_index <= span[1]
        ):
            raise BitcoinCoreError("Bitcoin Core returned an unexpected private descriptor.")
        request = [
            {
                "desc": private,
                "timestamp": timestamp,
                "active": True,
                "internal": False,
                "range": span,
                "next_index": next_index,
            }
        ]
        result = self._rpc(
            "importdescriptors",
            wallet=wallet,
            stdin=json.dumps(request, separators=(",", ":")) + "\n",
            timeout=86400,
        )
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], dict)
            or result[0].get("success") is not True
        ):
            raise BitcoinCoreError("Bitcoin Core did not complete the timestamped wallet rescan.")

    def _select(
        self,
        ask: Callable[[str], str],
        tell: Callable[[str], None],
    ) -> str:
        choices = tuple(name for name in sorted(self._names()) if self._target(name) is not None)
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
            tell(
                "In Bitcoin-Qt, choose File > Create Wallet... and create a blank descriptor wallet with "
                "private keys enabled."
            )
            tell("Waiting; press Ctrl-C to stop.")
            while True:
                sleep(1)
                names = set(self._names())
                new = names - before
                appeared = tuple(name for name in sorted(new) if self._target(name) is not None)
                if appeared:
                    break
            choices = tuple(name for name in sorted(names) if self._target(name) is not None)
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
        expected_fingerprint: bytes | None,
        account: int = 0,
        timestamp: int | Literal["now"] = "now",
    ) -> str:
        """Validate input and identity before selecting or changing a wallet."""
        if not isinstance(secret, MasterSeed):
            raise TypeError("wallet operations accept only MasterSeed")
        if type(account) is not int or account != 0:
            raise ValueError("Bitcoin Core wallet initialization currently supports only account 0")
        if timestamp != "now" and (type(timestamp) is not int or timestamp < 0):
            raise ValueError("timestamp must be a nonnegative integer or 'now'")
        self.verify_identity(secret, expected_fingerprint)
        while True:
            name = self._select(ask, tell)
            state = self._target(name)
            if state is None:
                tell("That wallet is no longer eligible. Choose again.")
                continue
            encrypted, locked = state
            relock = encrypted
            waited = False
            try:
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
                        state = self._target(name)
                        if state is None:
                            break
                        encrypted, locked = state
                        relock = relock or encrypted
                    if state is None:
                        break
                    state = self._target(name)
                    if state is None:
                        raise BitcoinCoreError("The selected wallet changed before import.")
                    current_encrypted, locked = state
                    relock = relock or current_encrypted
                    if not locked:
                        break
                if state is None:
                    tell("That wallet is no longer eligible. Choose again.")
                    continue
                self._create_account_zero(secret, name)
                if timestamp != "now":
                    self._rescan_from_timestamp(name, timestamp)
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


class CoreEntropy:
    """Draw randomness from fresh Bitcoin Core HD keys, in a new temporary encrypted wallet per draw."""

    def __init__(self, core: BitcoinCore, tell: Callable[[str], None]) -> None:
        self._core, self._tell, self._folder, self._disk, self._loaded = core, tell, "", "", ""
        self._passphrase, self._warned = secrets.token_hex(32), False

    def __call__(self, length: int) -> bytes:
        """Return ``length`` bytes; the draw's wallet is gone before they are used, even if it fails."""
        try:
            try:
                data = self._draw(length)
            except BaseException:
                try:
                    self._close()
                except BitcoinCoreError as left:
                    self._tell(str(left))  # the error already on its way says what the cards are worth
                raise
            self._close()  # A stuck wallet stops creation here, before the next card.
            return data
        except BitcoinCoreError as error:
            raise BitcoinCoreError(
                f"{error} New cards need Bitcoin Core's randomness, so creation stopped. "
                "Mark any cards from it void."
            ) from error

    def _draw(self, length: int) -> bytes:
        wallet = self._wallet()
        self._core._rpc("walletpassphrase", wallet=wallet, stdin=f"{self._passphrase}\n60\n")
        data = b""
        try:
            while len(data) < length:
                added = self._core._rpc("addhdkey", wallet=wallet)
                keys = self._core._rpc("-named", "gethdkeys", "private=true", wallet=wallet)
                xpub = added.get("xpub") if isinstance(added, dict) else None
                listed = keys if isinstance(keys, list) else []
                xprvs = [
                    key.get("xprv") for key in listed if isinstance(key, dict) and key.get("xpub") == xpub
                ]
                if not isinstance(xpub, str) or len(xprvs) != 1 or not isinstance(xprvs[0], str):
                    raise BitcoinCoreError("Bitcoin Core did not return a fresh HD key.")
                # Hashing keeps the plaintext xpub in the wallet file from checking guesses of a share. The
                # OS bytes keep that xpub from capping the key near 128 bits while the OS generator works.
                data += hashlib.sha256(xprvs[0].encode() + secrets.token_bytes(32)).digest()
        finally:
            self._core._rpc("walletlock", wallet=wallet)
        return data[:length]

    def _wallet(self) -> str:
        if not self._folder:
            self._folder = self._ram_folder()
            # Track the wallet first: Core may load it even if its answer never arrives.
            wallet = self._loaded = os.path.join(self._folder, "w")
            try:
                self._core._rpc(
                    "-named",
                    "createwallet",
                    f"wallet_name={wallet}",
                    "blank=true",
                    "load_on_startup=false",
                    stdin=f"passphrase={self._passphrase}\n",
                )
            except BitcoinCoreError as error:
                raise BitcoinCoreError(
                    f"Bitcoin Core could not create a wallet in {self._folder}. "
                    "Run Core as your own user, outside any sandbox."
                ) from error
        return os.path.join(self._folder, "w")

    def _ram_folder(self) -> str:
        if os.path.isdir("/dev/shm"):
            return tempfile.mkdtemp(prefix="codex32-", dir="/dev/shm")
        if sys.platform == "darwin":
            # A RAM disk needs no admin rights on macOS. Bitcoin Core's test guide uses the same commands:
            # https://github.com/bitcoin/bitcoin/blob/v29.0/test/README.md#speed-up-test-runs-with-a-ram-disk
            volume = f"/Volumes/codex32-{secrets.token_hex(4)}"
            attach = ("/usr/bin/hdiutil", "attach", "-nomount", "ram://32768")
            self._disk = subprocess.run(attach, capture_output=True, text=True, check=False).stdout.strip()
            erase = ("/usr/sbin/diskutil", "erasevolume", "HFS+", os.path.basename(volume), self._disk)
            erased = self._disk and not subprocess.run(erase, capture_output=True, check=False).returncode
            if erased and os.path.ismount(volume):
                return volume
        folder = tempfile.mkdtemp(prefix="codex32-")
        if self._warned:
            return folder
        self._warned = True
        self._tell(
            f"No RAM folder was found, so Bitcoin Core's temporary encrypted wallets will be on disk in "
            f"{os.path.dirname(folder)} while they draw. If this computer's own random generator is "
            "broken, anyone who later recovers those deleted files could recover the new cards. To avoid "
            "that, press Ctrl-C and use Tails, or point TMPDIR at a RAM drive and run create again. On "
            r"Windows with WinFsp's Developer files, `net use R: \\memfs64\codex32` and `set TMPDIR=R:\` do "
            "that without admin rights; `net use R: /delete` removes the drive afterwards."
        )
        return folder

    def _close(self) -> None:
        """Unload and delete the temporary wallet and any RAM disk made for it, or raise.

        Every step is tried, even after Ctrl-C, which is raised again once they have all run.
        """
        interrupted = False
        if self._loaded:
            # A call that fails or is interrupted may still have reached Core, so ask what it has loaded.
            try:
                self._core._rpc("unloadwallet", self._loaded)
                self._loaded = ""
            except BitcoinCoreError:
                pass
            except KeyboardInterrupt:
                interrupted = True
            try:
                if self._loaded and self._loaded not in self._core._names():
                    self._loaded = ""
            except BitcoinCoreError:
                pass
            except KeyboardInterrupt:
                interrupted = True
        if self._folder:
            shutil.rmtree(self._folder, ignore_errors=True)
        detach = ("/usr/bin/hdiutil", "detach", "-force", self._disk)
        if self._disk and not subprocess.run(detach, capture_output=True, check=False).returncode:
            self._disk = ""
        if not os.path.exists(self._folder):
            self._folder = ""
        left = self._folder or self._disk
        if self._loaded or left:
            raise BitcoinCoreError(
                "Bitcoin Core's temporary wallet was not removed."
                + (" Restart Core to unload it." if self._loaded else "")
                + (f" Delete or eject {left}." if left else "")
            )
        if interrupted:
            raise KeyboardInterrupt
