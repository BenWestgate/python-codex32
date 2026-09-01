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


def test_preflight_resolves_core_30_and_reads_its_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    responses = iter(({"version": 310100}, {"chain": "signet"}))

    def run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(next(responses)) + "\n", "")

    monkeypatch.setattr("codex32._bitcoin_core.shutil.which", lambda _name: "/reviewed/bitcoin-cli")
    monkeypatch.setattr(subprocess, "run", run)

    client = BitcoinCore.connect()

    assert (client.executable, client.chain, client.version) == ("/reviewed/bitcoin-cli", "signet", 310100)
    assert [command[-1] for command in commands] == ["getnetworkinfo", "getblockchaininfo"]
    assert all(command[1] == "-rpcconnect=127.0.0.1" for command in commands)


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
    answers = iter(("3", "", "1", "yes"))
    messages: list[str] = []

    selected = client._select(lambda _prompt: next(answers), messages.append)

    assert selected == "new"
    assert '1. "alpha"' in "\n".join(messages)
    assert '1. "new"' in "\n".join(messages)


@dataclass
class _ImportRPC:
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
            return _empty_info(**({"unlocked_until": 0 if self.locked else 100} if self.encrypted else {}))
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
    answers = iter(("1", "yes", ""))
    messages: list[str] = []

    def ask(prompt: str) -> str:
        if "retry" in prompt.lower():
            rpc.locked = False
        return next(answers)

    assert client.initialize(_SEED, ask, messages.append) == "signer"
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
    assert any("never reads its passphrase" in message for message in messages)


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
    answers = iter(("1", "yes"))

    with pytest.raises(BitcoinCoreError, match="did not import every private descriptor"):
        client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None)
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
    answers = iter(("1", "yes"))

    with pytest.raises(BitcoinCoreError, match="accepted public descriptors did not match"):
        client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None)
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
    answers = iter(("1", "yes"))

    with pytest.raises(BitcoinCoreError, match="suppressed failure"):
        client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None)
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
    answers = iter(("1", "yes"))

    with pytest.raises(KeyboardInterrupt):
        client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None)
    assert rpc.locked


def test_ineligibility_after_operator_unlock_relocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC()
    selections = 0

    def select(_client: BitcoinCore, _ask: object, _tell: object) -> str:
        nonlocal selections
        selections += 1
        if selections > 1:
            raise KeyboardInterrupt
        return "signer"

    states = iter(((True, True), None))
    monkeypatch.setattr(BitcoinCore, "_select", select)
    monkeypatch.setattr(BitcoinCore, "_target", lambda _client, _name: next(states))
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )

    def ask(_prompt: str) -> str:
        rpc.locked = False
        return ""

    with pytest.raises(KeyboardInterrupt):
        BitcoinCore("bitcoin-cli", "main", 300000).initialize(_SEED, ask, lambda _message: None)
    assert rpc.locked
    assert any(arguments == ("walletlock",) for arguments, _wallet, _stdin in rpc.calls)


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
    answers = iter(("1", "yes"))

    assert client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None) == "signer"
    assert rpc.locked and lock_calls == 2


def test_unencrypted_wallet_imports_without_a_lock_call(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _ImportRPC(encrypted=False, locked=False)
    monkeypatch.setattr(
        BitcoinCore,
        "_rpc",
        lambda client, *args, wallet=None, stdin=None: rpc(client, *args, wallet=wallet, stdin=stdin),
    )
    client = BitcoinCore("bitcoin-cli", "main", 300000)
    answers = iter(("1", "yes"))

    assert client.initialize(_SEED, lambda _prompt: next(answers), lambda _message: None) == "signer"
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
        client.initialize(_SEED, lambda _prompt: "", lambda _message: None)
    assert rpc.locked
    assert not any(arguments == ("importdescriptors",) for arguments, _wallet, _stdin in rpc.calls)


def test_subprocess_adapter_uses_loopback_and_never_repeats_raw_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "xprv-private-marker"

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        assert marker not in command
        assert command[1] == "-rpcconnect=127.0.0.1"
        assert command[-2:] == ["-stdin", "importdescriptors"]
        assert options["input"] == marker + "\n"
        return subprocess.CompletedProcess(command, 1, marker, marker)

    monkeypatch.setattr(subprocess, "run", run)
    client = BitcoinCore("/reviewed/bitcoin-cli", "main", 300000)

    with pytest.raises(BitcoinCoreError) as failure:
        client._rpc("importdescriptors", wallet="wallet", stdin=marker + "\n")
    assert marker not in str(failure.value)
