"""Tests for the private Bitcoin Core subprocess/state adapter."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field

import pytest

from codex32._bitcoin_core import (
    BitcoinCore,
    BitcoinCoreError,
    FingerprintMismatch,
    identifier_note,
    identifier_origin,
    parse_fingerprint,
)
from codex32.bip93 import parse_codex32
from codex32.generation import _fingerprint_identifier
from codex32.profiles.ms32 import MasterSeed
from codex32.wallet import _with_checksum

_parsed = parse_codex32("ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw")
assert isinstance(_parsed, MasterSeed)
_SEED: MasterSeed = _parsed

_ACCOUNT_XPUBS = {
    44: (
        "xpub6CeZ5XxHp6rXSwi2GCi7UT25rswWQtoPvj36MbzRBr3QEoEmBFNGgnMy329ZMk"
        "fjRKBZHtKKpYfpkrPWohTjHZZn7y1NR9EHnojaGLKdMAR"
    ),
    49: (
        "xpub6D9YUddFXuNKQvNrT9RQh8ueiTvHwF3RzdgU6uTEri73WTnBpKaDCGhTUiPBTy"
        "VJxtR5u2atDmCHE7tw369ahXddCNqJBxFpseud3j7pjX8"
    ),
    84: (
        "xpub6CNhWVRpA49Bz3LSaBibGqfBV4qa5NH1CStbQfsxWKScwrws5jioMunWKj2uM2"
        "rrfdJSroNuJBNDUmmdYXQw5LwVro39pH5nqEgAqrzTPyc"
    ),
    86: (
        "xpub6C5pT77VWNhWvrB3TqSEbpm7NCpMYEzbJreYbB68RCUoAMkT7rdhafinmdKL4M5"
        "275TyDqNAWCnssYnDNaPoXMiAg3sWvCgAiYqY8dHk1k4"
    ),
}
_ROOT_XPUB = "xpub-root-fixture"
_FINGERPRINT = bytes.fromhex("3f3521a6")
_PRIVATE_ACCOUNT = re.compile(r"/(?P<purpose>44|49|84|86)h/0h/0h/<0;1>/\*")


@pytest.fixture(autouse=True)
def _recorded_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the pre-import identity check without the address-derivation RPCs tested separately."""
    monkeypatch.setattr(BitcoinCore, "fingerprint", lambda _client, _secret: _FINGERPRINT)


def _descriptor_info(descriptor: str) -> dict[str, object]:
    """Return frozen Core-like normalization for the synthetic seed fixture."""
    raw = descriptor.strip().split("#", 1)[0]
    if "xpub" in raw:
        normalized = raw
    else:
        match = _PRIVATE_ACCOUNT.search(raw)
        if match is None:
            raise AssertionError(f"unexpected descriptor fixture: {raw}")
        purpose = int(match.group("purpose"))
        key = f"[3f3521a6/{purpose}h/0h/0h]{_ACCOUNT_XPUBS[purpose]}/<0;1>/*"
        if purpose == 44:
            normalized = f"pkh({key})"
        elif purpose == 49:
            normalized = f"sh(wpkh({key}))"
        elif purpose == 84:
            normalized = f"wpkh({key})"
        else:
            normalized = f"tr({key})"
    return {
        "descriptor": _with_checksum(normalized),
        "hasprivatekeys": False,
        "multipath_expansion": [
            _with_checksum(normalized.replace("<0;1>", str(branch))) for branch in (0, 1)
        ],
    }


def _empty_info(**changes: object) -> dict[str, object]:
    info: dict[str, object] = {
        "descriptors": True,
        "private_keys_enabled": True,
        "external_signer": False,
        "txcount": 0,
        "keypoolsize": 0,
        "keypoolsize_hd_internal": 0,
        "scanning": False,
    }
    info.update(changes)
    return info


@pytest.mark.parametrize(
    ("selected", "label"),
    (
        ("main", "mainnet"),
        ("test", "testnet3"),
        ("testnet4", "testnet4"),
        ("signet", "signet"),
        ("regtest", "regtest"),
    ),
)
def test_preflight_discovers_each_supported_chain(
    monkeypatch: pytest.MonkeyPatch, selected: str, label: str
) -> None:
    commands: list[list[str]] = []
    messages: list[str] = []

    def run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if f"-chain={selected}" not in command:
            return subprocess.CompletedProcess(command, 1, "ignored", "ignored")
        response = {"version": 320100} if command[-1] == "getnetworkinfo" else {"chain": selected}
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(subprocess, "run", run)

    client = BitcoinCore.connect(tell=messages.append)

    assert (client.executable, client.chain, client.version) == ("/reviewed/bitcoin-cli", selected, 320100)
    assert messages == [f"Using Bitcoin Core on {label}."]
    assert all(command[1].startswith("-chain=") for command in commands)
    assert all(command[2] == "-rpcconnect=127.0.0.1" for command in commands)


def test_preflight_requires_selection_when_multiple_chains_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[str] = []
    answers = iter(("0", "2"))

    def run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        chain = command[1].removeprefix("-chain=")
        if chain not in ("main", "signet"):
            return subprocess.CompletedProcess(command, 1, "", "")
        response = {"version": 320000} if command[-1] == "getnetworkinfo" else {"chain": chain}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(subprocess, "run", run)

    client = BitcoinCore.connect(lambda _prompt: next(answers), messages.append)

    assert client.chain == "signet"
    assert messages == [
        "Local Bitcoin Core networks:",
        "  1. mainnet",
        "  2. signet",
        "Enter one of the displayed numbers.",
        "Using Bitcoin Core on signet.",
    ]


def test_preflight_rejection_is_helpful_without_echoing_core_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "untrusted Core output"
    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_options: subprocess.CompletedProcess(command, 1, marker, marker),
    )

    with pytest.raises(BitcoinCoreError) as failure:
        BitcoinCore.connect()

    message = str(failure.value)
    assert message == (
        "No local Bitcoin Core RPC server found.\n"
        "Start Bitcoin Core with local RPC enabled.\n"
        "For signet practice: bitcoin-qt -signet -server"
    )
    assert marker not in message


def test_preflight_rejects_old_and_mismatched_core_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        chain = command[1].removeprefix("-chain=")
        if chain not in ("main", "signet"):
            return subprocess.CompletedProcess(command, 1, "", "")
        if command[-1] == "getnetworkinfo":
            response: dict[str, object] = {"version": 319999 if chain == "main" else 320000}
        else:
            response = {"chain": chain if chain == "main" else "main"}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(BitcoinCoreError, match="No local Bitcoin Core RPC server"):
        BitcoinCore.connect()


def test_candidate_filter_rejects_every_unsafe_wallet_property(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wallets = {
        "eligible": (_empty_info(), []),
        "watch": (_empty_info(private_keys_enabled=False), []),
        "external": (_empty_info(external_signer=True), []),
        "legacy": (_empty_info(descriptors=False), []),
        "transactions": (_empty_info(txcount=1), []),
        "keys": (_empty_info(keypoolsize=1), []),
        "change": (_empty_info(keypoolsize_hd_internal=1), []),
        "boolean transactions": (_empty_info(txcount=False), []),
        "boolean keys": (_empty_info(keypoolsize=False), []),
        "boolean change": (_empty_info(keypoolsize_hd_internal=False), []),
        "invalid unlock": (_empty_info(unlocked_until="unlocked"), []),
        "null unlock": (_empty_info(unlocked_until=None), []),
        "scanning": (_empty_info(scanning={"duration": 1}), []),
        "descriptors": (_empty_info(), [{"desc": "public"}]),
        "bad\x1bname": (_empty_info(), []),
    }

    def rpc(
        _client: BitcoinCore, command: str, *, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        del stdin
        assert wallet is not None
        value = wallets[wallet][0 if command == "getwalletinfo" else 1]
        return value if command == "getwalletinfo" else {"descriptors": value}

    monkeypatch.setattr(BitcoinCore, "_rpc", rpc)
    client = BitcoinCore("bitcoin-cli", "main", 300000)

    assert client._target("eligible") == (False, False)
    assert client._target("watch") is None
    assert all(client._target(name) is None for name in wallets if name != "eligible")


def test_target_reads_fallible_descriptor_state_before_unlock_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def rpc(_client: BitcoinCore, command: str, **_options: object) -> object:
        calls.append(command)
        return {"descriptors": []} if command == "listdescriptors" else _empty_info(unlocked_until=100)

    monkeypatch.setattr(BitcoinCore, "_rpc", rpc)

    assert BitcoinCore("bitcoin-cli", "main", 300000)._target("wallet") == (True, False)
    assert calls == ["listdescriptors", "getwalletinfo"]


def test_selection_uses_numbers_confirms_names_and_considers_only_new_wallets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    snapshots = iter((("alpha", "beta"), ("alpha", "beta"), ("alpha", "beta", "new")))
    monkeypatch.setattr(BitcoinCore, "_names", lambda _client: next(snapshots))
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: (False, False))
    monkeypatch.setattr("codex32._bitcoin_core.sleep", lambda _seconds: None)
    answers = iter(("3", "no", "1", "yes"))
    prompts: list[str] = []
    messages: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    selected = client._select(ask, messages.append)

    assert selected == "alpha"
    assert '1. "alpha"' in "\n".join(messages)
    assert prompts[1] == 'Use blank wallet "new"? [y/N]'
    assert '3. "new"' in "\n".join(messages)
    assert prompts[-1] == 'Use blank wallet "alpha"? [y/N]'


def test_single_wallet_rejection_opens_the_numbered_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    monkeypatch.setattr(BitcoinCore, "_names", lambda _client: ("only",))
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: (False, False))
    answers = iter(("", "1", "yes"))
    prompts: list[str] = []
    messages: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    assert client._select(ask, messages.append) == "only"
    assert prompts == [
        'Use blank wallet "only"? [y/N]',
        "Choose a wallet number",
        'Use blank wallet "only"? [y/N]',
    ]
    assert '1. "only"' in "\n".join(messages)


def test_no_wallet_immediately_requests_a_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    snapshots = iter(((), (), ("new",)))
    monkeypatch.setattr(BitcoinCore, "_names", lambda _client: next(snapshots))
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: (False, False))
    monkeypatch.setattr("codex32._bitcoin_core.sleep", lambda _seconds: None)
    answers = iter(("yes",))
    prompts: list[str] = []
    messages: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    assert client._select(ask, messages.append) == "new"
    assert prompts == ['Use blank wallet "new"? [y/N]']
    assert messages[0].startswith("In Bitcoin-Qt, choose File > Create Wallet...")
    assert messages[1] == "Waiting; press Ctrl-C to stop."


@dataclass
class _ImportRPC:
    private: bool = True
    encrypted: bool = True
    locked: bool = True
    imported: bool = False
    created: int = 0
    rescan_success: bool = True
    calls: list[tuple[tuple[str, ...], str | None, str | None]] = field(default_factory=list)
    expansions: list[str] = field(default_factory=list)

    def __call__(
        self,
        _client: BitcoinCore,
        *arguments: str,
        wallet: str | None = None,
        stdin: str | None = None,
        timeout: int = 120,
    ) -> object:
        del timeout
        self.calls.append((arguments, wallet, stdin))
        command = arguments[0]
        if command == "listwallets":
            return ["signer"]
        if command == "getwalletinfo":
            encryption = {"unlocked_until": 0 if self.locked else 100} if self.encrypted else {}
            return _empty_info(private_keys_enabled=self.private, **encryption)
        if command == "listdescriptors":
            if not self.imported:
                return {"wallet_name": "signer", "descriptors": []}
            records = [
                {
                    "desc": f"{descriptor}-xprv" if arguments[1:] == ("true",) else descriptor,
                    "active": True,
                    "internal": bool(position % 2),
                    "range": [0, 999],
                    "next_index": 0,
                }
                for position, descriptor in enumerate(self.expansions)
            ]
            return {"wallet_name": "signer", "descriptors": records}
        if command == "addhdkey":
            assert wallet == "signer" and stdin is not None and stdin.startswith("xprv")
            return {"xpub": _ROOT_XPUB}
        if arguments[:2] == ("-named", "createwalletdescriptor"):
            assert wallet == "signer" and stdin is None
            assert json.loads(arguments[3].removeprefix("options=")) == {"hdkey": _ROOT_XPUB}
            output_type = arguments[2].removeprefix("type=")
            self.created += 1
            self.imported = True
            self.expansions.extend((f"{output_type}-receive", f"{output_type}-change"))
            return {"descs": self.expansions[-2:]}
        if command == "getdescriptorinfo":
            assert stdin is not None
            return _descriptor_info(stdin)
        if command == "importdescriptors":
            assert arguments == ("importdescriptors",) and wallet == "signer" and self.created == 4
            assert stdin is not None
            return [{"success": self.rescan_success}]
        if command == "walletlock":
            self.locked = True
            return None
        raise AssertionError(command)


def test_encrypted_wallet_uses_core_descriptors_and_relocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC()
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None, timeout=120: rpc(
            client, *args, wallet=wallet, stdin=stdin, timeout=timeout
        ),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    messages: list[str] = []
    delays: list[int] = []

    def unlock(seconds: int) -> None:
        delays.append(seconds)
        rpc.locked = False

    monkeypatch.setattr("codex32._bitcoin_core.sleep", unlock)

    assert (
        client.initialize(_SEED, lambda _prompt: "yes", messages.append, expected_fingerprint=_FINGERPRINT)
        == "signer"
    )
    private_calls = [call for call in rpc.calls if "xprv" in (call[2] or "")]
    assert len(private_calls) == 1
    arguments, wallet, private_stdin = private_calls[0]
    assert arguments == ("addhdkey",) and wallet == "signer"
    assert private_stdin is not None and private_stdin.endswith("\n")
    assert private_stdin.startswith("xprv")
    assert all("xprv" not in " ".join((*args, selected or "")) for args, selected, _data in rpc.calls)
    assert [
        args[2] for args, _wallet, _stdin in rpc.calls if args[:2] == ("-named", "createwalletdescriptor")
    ] == ["type=legacy", "type=p2sh-segwit", "type=bech32", "type=bech32m"]
    assert not any(args == ("rescanblockchain", "0") for args, _wallet, _stdin in rpc.calls)
    assert not any(args == ("importdescriptors",) for args, _wallet, _stdin in rpc.calls)
    assert rpc.locked
    assert delays == [1]
    assert (
        messages.count(
            'In Bitcoin-Qt, open Window > Console and select wallet "signer".\n'
            'Type: walletpassphrase "YOUR PASSPHRASE" 5\nWaiting; press Ctrl-C to stop.'
        )
        == 1
    )
    assert messages[-1] == ""


@pytest.mark.parametrize("account", (1, 7, True))
def test_nonzero_or_noninteger_account_is_rejected_before_wallet_selection(
    account: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(BitcoinCore, "_select", lambda *_args: pytest.fail("selected a wallet"))
    with pytest.raises(ValueError, match="only account 0"):
        BitcoinCore("bitcoin-cli", "main", 320000).initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=_FINGERPRINT,
            account=account,
        )


def test_failed_descriptor_creation_relocks_encrypted_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def fail(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments[:3] == ("-named", "createwalletdescriptor", "type=bech32"):
            rpc.calls.append((arguments, wallet, stdin))
            return {"descs": []}
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", fail)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(BitcoinCoreError, match="did not create both wallet descriptors"):
        client.initialize(
            _SEED, lambda _prompt: "yes", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
    assert rpc.locked
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_fingerprint_uses_stateless_core_address_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []

    def rpc(
        _client: BitcoinCore,
        *arguments: str,
        wallet: str | None = None,
        stdin: str | None = None,
    ) -> object:
        del stdin
        calls.append((arguments, wallet))
        if arguments == ("getdescriptorinfo",):
            return {"descriptor": "pkh(xpub-root)#checksum"}
        if arguments == ("deriveaddresses",):
            return ["1synthetic"]
        if arguments == ("validateaddress", "1synthetic"):
            return {"scriptPubKey": "76a9143f3521a6" + "00" * 16 + "88ac"}
        raise AssertionError(arguments)

    monkeypatch.setattr(BitcoinCore, "_rpc", rpc)

    assert BitcoinCore("bitcoin-cli", "main", 320000).fingerprint_seed(_SEED.seed_bytes) == _FINGERPRINT
    assert calls == [
        (("getdescriptorinfo",), None),
        (("deriveaddresses",), None),
        (("validateaddress", "1synthetic"), None),
    ]


@pytest.mark.parametrize("timestamp", (0, 123))
def test_numeric_timestamp_rescans_history(monkeypatch: pytest.MonkeyPatch, timestamp: int) -> None:
    rpc = _ImportRPC(locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None, timeout=120: rpc(
            client, *args, wallet=wallet, stdin=stdin, timeout=timeout
        ),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    assert (
        client.initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=_FINGERPRINT,
            timestamp=timestamp,
        )
        == "signer"
    )
    calls = [(args, data) for args, _wallet, data in rpc.calls if args == ("importdescriptors",)]
    assert len(calls) == 1
    args, data = calls[0]
    assert args == ("importdescriptors",)
    assert data is not None
    assert json.loads(data) == [
        {
            "desc": "legacy-receive-xprv",
            "timestamp": timestamp,
            "active": True,
            "internal": False,
            "range": [0, 999],
            "next_index": 0,
        }
    ]
    assert not any(args[0] == "rescanblockchain" for args, _wallet, _data in rpc.calls)
    assert all("xprv" not in " ".join(args) for args, _wallet, _data in rpc.calls)
    assert rpc.locked


def test_failed_timestamped_rescan_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False, rescan_success=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None, timeout=120: rpc(
            client, *args, wallet=wallet, stdin=stdin, timeout=timeout
        ),
    )
    with pytest.raises(BitcoinCoreError, match="did not complete the timestamped wallet rescan"):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=_FINGERPRINT,
            timestamp=123,
        )
    assert rpc.locked


@pytest.mark.parametrize("command", ("addhdkey", "createwalletdescriptor"))
def test_core_creation_failures_relock(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def fail(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments[0] == command or (
            command == "createwalletdescriptor" and arguments[:2] == ("-named", command)
        ):
            raise BitcoinCoreError("suppressed failure")
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", fail)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(BitcoinCoreError, match="suppressed failure"):
        client.initialize(
            _SEED, lambda _prompt: "yes", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
    assert rpc.locked
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_interruption_after_unlock_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def interrupt(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments == ("addhdkey",):
            raise KeyboardInterrupt
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", interrupt)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(KeyboardInterrupt):
        client.initialize(
            _SEED, lambda _prompt: "yes", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
    assert rpc.locked


def test_ineligibility_after_operator_unlock_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC()
    selections = 0
    messages: list[str] = []

    def select(_client: BitcoinCore, _ask: object, _tell: object) -> str:
        nonlocal selections
        selections += 1
        if selections > 1:
            raise KeyboardInterrupt
        return "signer"

    states = iter(((True, True), None))
    monkeypatch.setattr(BitcoinCore, "_select", select)
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: next(states))
    monkeypatch.setattr("codex32._bitcoin_core.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )

    with pytest.raises(KeyboardInterrupt):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED, lambda _prompt: "yes", messages.append, expected_fingerprint=_FINGERPRINT
        )
    assert rpc.locked
    assert "That wallet is no longer eligible. Choose again." in messages
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_interruption_while_waiting_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC()
    monkeypatch.setattr(BitcoinCore, "_select", lambda *_args, **_options: "signer")
    monkeypatch.setattr(BitcoinCore, "_target", lambda *_args, **_options: (True, True))
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )

    def interrupt(_seconds: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("codex32._bitcoin_core.sleep", interrupt)

    with pytest.raises(KeyboardInterrupt):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED, lambda _prompt: "", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
    assert rpc.locked


def test_wallet_relocking_before_import_repeats_wait_without_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    states = iter(((True, False), (True, True), (True, False), (True, False)))
    delays: list[int] = []
    target_calls = 0

    def target(*_args: object, **_options: object) -> tuple[bool, bool]:
        nonlocal target_calls
        target_calls += 1
        return next(states)

    monkeypatch.setattr(BitcoinCore, "_select", lambda *_args, **_options: "signer")
    monkeypatch.setattr(BitcoinCore, "_target", target)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )
    monkeypatch.setattr("codex32._bitcoin_core.sleep", delays.append)

    assert (
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED, lambda _prompt: "", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
        == "signer"
    )
    assert delays == [1]
    assert (
        sum(arguments[:2] == ("-named", "createwalletdescriptor") for arguments, _wallet, _stdin in rpc.calls)
        == 4
    )
    assert sum(arguments == ("addhdkey",) for arguments, _wallet, _stdin in rpc.calls) == 1


def test_interruption_during_walletlock_retries_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__
    lock_calls = 0

    def interrupt_once(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        nonlocal lock_calls
        if arguments == ("walletlock",):
            lock_calls += 1
            if lock_calls == 1:
                raise KeyboardInterrupt
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", interrupt_once)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    assert (
        client.initialize(
            _SEED, lambda _prompt: "yes", lambda _message: None, expected_fingerprint=_FINGERPRINT
        )
        == "signer"
    )
    assert rpc.locked and lock_calls == 2


def test_walletlock_failure_requires_manual_lock_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def fail_lock(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments == ("walletlock",):
            raise BitcoinCoreError("suppressed lock failure")
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", fail_lock)
    with pytest.raises(
        BitcoinCoreError, match="Confirm immediately in Bitcoin Core that the wallet is locked"
    ):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=_FINGERPRINT,
        )


@pytest.mark.parametrize("unlocked_until", (100, False, "locked"))
def test_failed_lock_verification_requires_manual_confirmation(
    monkeypatch: pytest.MonkeyPatch, unlocked_until: object
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__
    lock_requested = False

    def remain_unlocked(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        nonlocal lock_requested
        if arguments == ("walletlock",):
            lock_requested = True
            return None
        if lock_requested and arguments == ("getwalletinfo",):
            return _empty_info(unlocked_until=unlocked_until)
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", remain_unlocked)
    with pytest.raises(
        BitcoinCoreError, match="Confirm immediately in Bitcoin Core that the wallet is locked"
    ):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=_FINGERPRINT,
        )


def test_unencrypted_wallet_imports_without_a_lock_call(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(encrypted=False, locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None, timeout=120: rpc(
            client, *args, wallet=wallet, stdin=stdin, timeout=timeout
        ),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    messages: list[str] = []
    assert (
        client.initialize(_SEED, lambda _prompt: "yes", messages.append, expected_fingerprint=_FINGERPRINT)
        == "signer"
    )
    assert messages == []
    assert not any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_immediate_revalidation_stops_before_private_import_and_relocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    states = iter(((True, False), None))
    rpc = _ImportRPC(locked=False)
    monkeypatch.setattr(BitcoinCore, "_select", lambda _client, _ask, _tell: "changed")
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: next(states))
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda core, *args, wallet=None, stdin=None: rpc(
            core,
            *args,
            wallet=wallet,
            stdin=stdin,
        ),
    )

    with pytest.raises(BitcoinCoreError, match="changed before import"):
        client.initialize(_SEED, lambda _prompt: "", lambda _message: None, expected_fingerprint=_FINGERPRINT)
    assert rpc.locked
    assert not any(arguments == ("addhdkey",) for arguments, _wallet, _stdin in rpc.calls)


def test_subprocess_adapter_uses_loopback_and_never_repeats_raw_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "xprv-private-marker"

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        assert marker not in command
        assert command[1:3] == ["-chain=main", "-rpcconnect=127.0.0.1"]
        assert command[-2:] == ["-stdin", "addhdkey"]
        assert options["input"] == marker + "\n"
        return subprocess.CompletedProcess(command, 1, marker, marker)

    monkeypatch.setattr(subprocess, "run", run)
    client = BitcoinCore("/reviewed/bitcoin-cli", "main", 300000)

    with pytest.raises(BitcoinCoreError) as failure:
        client._rpc("addhdkey", wallet="wallet", stdin=marker + "\n")
    assert marker not in str(failure.value)


@pytest.mark.parametrize("text", ("3f3521a6", "3F35 21A6", " 3f35\t21a6 "))
def test_parse_fingerprint_accepts_record_spellings(text: str) -> None:
    assert parse_fingerprint(text) == _FINGERPRINT


@pytest.mark.parametrize("text", ("", "3f3521a", "3f3521a6ff", "3f3521ag", "0x3f3521"))
def test_parse_fingerprint_rejects_other_text(text: str) -> None:
    with pytest.raises(ValueError, match="8 characters"):
        parse_fingerprint(text)


def test_identity_mismatch_stops_before_any_wallet_call(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )

    with pytest.raises(FingerprintMismatch, match="Bitcoin Core was not changed"):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            expected_fingerprint=bytes.fromhex("3f3521a7"),
        )
    assert rpc.calls == []


def test_no_record_is_the_operators_choice_and_checks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def unused(_client: BitcoinCore, _secret: MasterSeed) -> bytes:
        raise AssertionError("no fingerprint is compared without a record")

    monkeypatch.setattr(BitcoinCore, "fingerprint", unused)
    BitcoinCore("bitcoin-cli", "main", 300000).verify_identity(_SEED, None)


# Frozen from Bails' own ms32.seed_identifier for this seed: master (RIPEMD-160) and the
# June 2023 alpha (SHA-256). Bails checked three characters and kept the fourth for re-sharing.
_BAILS_SEED = bytes(range(16))


@pytest.mark.parametrize(
    ("identifier", "origin"),
    (
        (_fingerprint_identifier(_FINGERPRINT), "codex32"),
        ("d9k8", "Bails"),
        ("d9kq", "Bails"),
        ("hezu", "Bails alpha"),
        ("test", None),
    ),
)
def test_identifier_origin_names_the_rule_that_made_it(identifier: str, origin: str | None) -> None:
    secret = MasterSeed.from_seed(_BAILS_SEED, identifier=identifier)
    assert identifier_origin(secret, _FINGERPRINT) == origin
    assert ("matches this seed" in identifier_note(origin)) is (origin is not None)


@pytest.mark.parametrize(
    ("identifier", "expected"),
    (("hezu", "Bails alpha"), ("d9k8", "Bails check unavailable")),
)
def test_identifier_origin_without_ripemd160(
    monkeypatch: pytest.MonkeyPatch, identifier: str, expected: str
) -> None:
    original_new = hashlib.new

    def without_ripemd160(name: str, data: bytes = b"") -> object:
        if name == "ripemd160":
            raise ValueError("unsupported hash type ripemd160")
        return original_new(name, data)

    monkeypatch.setattr(hashlib, "new", without_ripemd160)
    secret = MasterSeed.from_seed(_BAILS_SEED, identifier=identifier)
    assert identifier_origin(secret, _FINGERPRINT) == expected
    if expected == "Bails check unavailable":
        assert "could not be checked" in identifier_note(expected)
        assert "does not prove" in identifier_note(expected)


def test_identifier_note_allows_supported_nonderived_codex32_identifiers() -> None:
    note = identifier_note(None)
    assert "split shares" in note
    assert "supplied seed bytes" in note
    assert "explicit identifier" in note
