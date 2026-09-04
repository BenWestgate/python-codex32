"""Tests for the private Bitcoin Core subprocess/state adapter."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

import pytest

from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError
from codex32.bip93 import parse_codex32
from codex32.profiles.ms32 import MasterSeed

_parsed = parse_codex32("ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw")
assert isinstance(_parsed, MasterSeed)
_SEED: MasterSeed = _parsed


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
        response = {"version": 310100} if command[-1] == "getnetworkinfo" else {"chain": selected}
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(subprocess, "run", run)

    client = BitcoinCore.connect(tell=messages.append)

    assert (client.executable, client.chain, client.version) == ("/reviewed/bitcoin-cli", selected, 310100)
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
        response = {"version": 300000} if command[-1] == "getnetworkinfo" else {"chain": chain}
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
            response: dict[str, object] = {"version": 299999 if chain == "main" else 310000}
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
    assert client._target("watch", private=False) == (False, False)
    assert all(client._target(name) is None for name in wallets if name not in ("eligible", "watch"))


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
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name, *, private=True: (False, False))
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
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name, *, private=True: (False, False))
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
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name, *, private=True: (False, False))
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
    calls: list[tuple[tuple[str, ...], str | None, str | None]] = field(default_factory=list)
    expansions: list[str] = field(default_factory=list)

    def __call__(
        self,
        _client: BitcoinCore,
        *arguments: str,
        wallet: str | None = None,
        stdin: str | None = None,
    ) -> object:
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
                {"desc": descriptor, "active": True, "internal": bool(position % 2)}
                for position, descriptor in enumerate(self.expansions)
            ]
            return {"wallet_name": "signer", "descriptors": records}
        if command == "getdescriptorinfo":
            position = len(self.expansions) // 2
            pair = [f"public-{position}-0", f"public-{position}-1"]
            self.expansions.extend(pair)
            return {"multipath_expansion": pair}
        if command == "importdescriptors":
            self.imported = True
            return [{"success": True} for _ in range(4)]
        if command == "walletlock":
            self.locked = True
            return None
        raise AssertionError(command)


def test_encrypted_import_retries_without_a_passphrase_verifies_and_relocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC()
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    messages: list[str] = []
    delays: list[int] = []

    def unlock(seconds: int) -> None:
        delays.append(seconds)
        rpc.locked = False

    monkeypatch.setattr("codex32._bitcoin_core.sleep", unlock)

    assert client.initialize(_SEED, lambda _prompt: "yes", messages.append) == "signer"
    private_calls = [call for call in rpc.calls if "xprv" in (call[2] or "")]
    assert len(private_calls) == 1
    arguments, wallet, private_stdin = private_calls[0]
    assert arguments == ("importdescriptors",) and wallet == "signer"
    assert private_stdin is not None and private_stdin.endswith("\n")
    records = json.loads(private_stdin)
    assert len(records) == 4 and all(record["timestamp"] == "now" for record in records)
    assert all("xprv" in record["desc"] for record in records)
    assert all("xprv" not in " ".join((*args, selected or "")) for args, selected, _data in rpc.calls)
    assert rpc.locked
    assert delays == [1]
    assert (
        messages.count(
            'In Bitcoin-Qt, open Window > Console and select wallet "signer".\n'
            'Type: walletpassphrase "YOUR PASSPHRASE" 5\nWaiting; press Ctrl-C to stop.'
        )
        == 1
    )


def test_failed_import_is_generic_and_relocks_encrypted_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def fail(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments == ("importdescriptors",):
            rpc.calls.append((arguments, wallet, stdin))
            return [{"success": True}, {"success": False}, {"success": True}, {"success": True}]
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", fail)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(BitcoinCoreError, match="did not import every private descriptor"):
        client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None)
    assert rpc.locked
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


@pytest.mark.parametrize("change", ("missing", "extra"))
def test_exact_public_descriptor_verification_rejects_missing_or_extra_records(
    change: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def alter(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        result = original(client, *arguments, wallet=wallet, stdin=stdin)
        if arguments == ("listdescriptors",) and rpc.imported and isinstance(result, dict):
            descriptors = result["descriptors"]
            assert isinstance(descriptors, list)
            if change == "missing":
                descriptors.pop()
            else:
                descriptors.append({"desc": "unexpected", "active": True, "internal": False})
        return result

    monkeypatch.setattr(BitcoinCore, "_rpc", alter)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(BitcoinCoreError, match="accepted public descriptors did not match"):
        client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None)
    assert rpc.locked


@pytest.mark.parametrize("command", ("getdescriptorinfo", "listdescriptors"))
def test_public_preparation_and_verification_failures_relock(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def fail(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments == (command,) and (command == "getdescriptorinfo" or rpc.imported):
            raise BitcoinCoreError("suppressed failure")
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", fail)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(BitcoinCoreError, match="suppressed failure"):
        client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None)
    assert rpc.locked
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_interruption_after_unlock_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(locked=False)
    original = rpc.__call__

    def interrupt(
        client: BitcoinCore, *arguments: str, wallet: str | None = None, stdin: str | None = None
    ) -> object:
        if arguments == ("getdescriptorinfo",):
            raise KeyboardInterrupt
        return original(client, *arguments, wallet=wallet, stdin=stdin)

    monkeypatch.setattr(BitcoinCore, "_rpc", interrupt)
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    with pytest.raises(KeyboardInterrupt):
        client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None)
    assert rpc.locked


def test_ineligibility_after_operator_unlock_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC()
    selections = 0
    messages: list[str] = []

    def select(_client: BitcoinCore, _ask: object, _tell: object, *, private: bool = True) -> str:
        del private
        nonlocal selections
        selections += 1
        if selections > 1:
            raise KeyboardInterrupt
        return "signer"

    states = iter(((True, True), None))
    monkeypatch.setattr(BitcoinCore, "_select", select)
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name, *, private=True: next(states))
    monkeypatch.setattr("codex32._bitcoin_core.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )

    with pytest.raises(KeyboardInterrupt):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(_SEED, lambda _prompt: "yes", messages.append)
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
            _SEED, lambda _prompt: "", lambda _message: None
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
            _SEED, lambda _prompt: "", lambda _message: None
        )
        == "signer"
    )
    assert delays == [1]
    assert sum(arguments == ("getdescriptorinfo",) for arguments, _wallet, _stdin in rpc.calls) == 4
    assert sum(arguments == ("importdescriptors",) for arguments, _wallet, _stdin in rpc.calls) == 1


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
    assert client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None) == "signer"
    assert rpc.locked and lock_calls == 2


def test_unencrypted_wallet_imports_without_a_lock_call(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(encrypted=False, locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    assert client.initialize(_SEED, lambda _prompt: "yes", lambda _message: None) == "signer"
    assert not any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_watch_only_import_requires_disabled_private_keys_and_never_relocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _ImportRPC(private=False, encrypted=False, locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    assert (
        client.initialize(
            _SEED,
            lambda _prompt: "yes",
            lambda _message: None,
            private=False,
            account=7,
            timestamp=123,
        )
        == "signer"
    )
    imported = next(data for args, _wallet, data in rpc.calls if args == ("importdescriptors",))
    assert imported is not None
    records = json.loads(imported)
    assert all("xprv" not in record["desc"] for record in records)
    assert all(record["timestamp"] == 123 for record in records)
    assert not any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


def test_immediate_revalidation_stops_before_private_import_and_relocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    states = iter(((True, False), None))
    rpc = _ImportRPC(locked=False)
    monkeypatch.setattr(BitcoinCore, "_select", lambda _client, _ask, _tell, *, private=True: "changed")
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name, *, private=True: next(states))
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
        client.initialize(_SEED, lambda _prompt: "", lambda _message: None)
    assert rpc.locked
    assert not any(arguments == ("importdescriptors",) for arguments, _wallet, _stdin in rpc.calls)


def test_subprocess_adapter_uses_loopback_and_never_repeats_raw_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "xprv-private-marker"

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        assert marker not in command
        assert command[1:3] == ["-chain=main", "-rpcconnect=127.0.0.1"]
        assert command[-2:] == ["-stdin", "importdescriptors"]
        assert options["input"] == marker + "\n"
        return subprocess.CompletedProcess(command, 1, marker, marker)

    monkeypatch.setattr(subprocess, "run", run)
    client = BitcoinCore("/reviewed/bitcoin-cli", "main", 300000)

    with pytest.raises(BitcoinCoreError) as failure:
        client._rpc("importdescriptors", wallet="wallet", stdin=marker + "\n")
    assert marker not in str(failure.value)
