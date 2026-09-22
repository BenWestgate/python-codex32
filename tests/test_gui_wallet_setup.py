"""The graphical program's Bitcoin Core boundary: naming, passphrases, and refusals."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

import pytest

from codex32 import parse_codex32
from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError
from codex32_gui import wallet_setup

_SEED = parse_codex32("MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW")

PASSPHRASE = 'a pass phrase with = and "quotes"'


def _lines(supplied: str) -> list[str]:
    """Split standard input the way bitcoin-cli's own `std::getline` does: on newlines only."""
    parts = supplied.split("\n")
    return parts[:-1] if parts and parts[-1] == "" else parts


@dataclass
class _Wallet:
    encrypted: bool = False
    locked: bool = False
    filled: bool = False


@dataclass
class _Core:
    """A stand-in for bitcoin-cli that answers only what wallet selection needs."""

    wallets: dict[str, _Wallet]
    runs: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)

    def run(self, command: list[str], **keywords: Any) -> subprocess.CompletedProcess[str]:
        supplied = keywords.get("input")
        self.runs.append((tuple(command), supplied))
        options = [item for item in command[1:] if item.startswith("-")]
        arguments = [item for item in command[1:] if not item.startswith("-")]
        lines = _lines(supplied or "")
        if supplied is not None and "-stdinwalletpassphrase" in options:
            # bitcoin-cli takes the first line as the passphrase argument.
            arguments, lines = [arguments[0], lines[0], *arguments[1:]], lines[1:]
        if supplied is not None and "-stdin" in options:
            arguments += lines
        name = next((item[11:] for item in options if item.startswith("-rpcwallet=")), None)
        return subprocess.CompletedProcess(command, 0, self._reply(arguments[0], arguments[1:], name), "")

    def _reply(self, method: str, arguments: list[str], name: str | None) -> str:
        if method == "listwallets":
            return json.dumps(sorted(self.wallets))
        if method == "listdescriptors":
            return json.dumps({"descriptors": []})
        if method == "getwalletinfo":
            assert name is not None
            wallet = self.wallets[name]
            info: dict[str, object] = {
                "descriptors": True,
                "private_keys_enabled": True,
                "external_signer": False,
                "txcount": 0,
                "keypoolsize": 0,
                "keypoolsize_hd_internal": 0,
                "scanning": False,
            }
            if wallet.encrypted:
                info["unlocked_until"] = 0 if wallet.locked else 1
            return json.dumps(info)
        if method == "createwallet":
            fields = dict(item.split("=", 1) for item in arguments)
            self.wallets[fields["wallet_name"]] = _Wallet("passphrase" in fields, "passphrase" in fields)
            return json.dumps({"name": fields["wallet_name"]})
        if method == "walletpassphrase":
            assert name is not None
            self.wallets[name].locked = False
            return ""
        if method == "walletlock":
            assert name is not None
            self.wallets[name].locked = True
            return ""
        raise AssertionError(f"the graphical program should not call {method}")

    def called(self, method: str) -> bool:
        return any(method in command for command, _supplied in self.runs)


def _client(monkeypatch: pytest.MonkeyPatch, wallets: dict[str, _Wallet]) -> tuple[BitcoinCore, _Core]:
    fake = _Core(wallets)
    monkeypatch.setattr(subprocess, "run", lambda command, **keywords: fake.run(command, **keywords))
    return BitcoinCore("bitcoin-cli", "regtest", 320000), fake


def test_only_empty_wallets_are_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    core, _fake = _client(monkeypatch, {"empty": _Wallet(), "locked": _Wallet(True, True)})
    assert wallet_setup.eligible(core) == (
        wallet_setup.Wallet("empty", False, False),
        wallet_setup.Wallet("locked", True, True),
    )


def test_the_wallet_is_chosen_by_its_exact_name(monkeypatch: pytest.MonkeyPatch) -> None:
    core, _fake = _client(monkeypatch, {"one": _Wallet(), "two": _Wallet()})
    for wanted in ("one", "two"):
        answer = wallet_setup._Answer(wanted, quoted=True)
        assert core._select(answer.ask, answer.tell) == wanted


def test_a_single_eligible_wallet_still_needs_its_name(monkeypatch: pytest.MonkeyPatch) -> None:
    core, _fake = _client(monkeypatch, {"only": _Wallet()})
    answer = wallet_setup._Answer("only", quoted=True)
    assert core._select(answer.ask, answer.tell) == "only"


@pytest.mark.parametrize("chosen", [None, "a wallet that is not there"])
def test_an_unmatched_name_offers_the_list_instead_of_guessing(
    monkeypatch: pytest.MonkeyPatch, chosen: str | None
) -> None:
    core, _fake = _client(monkeypatch, {"one": _Wallet(), "two": _Wallet()})
    answer = wallet_setup._Answer(chosen, quoted=True)
    with pytest.raises(wallet_setup.Offer) as raised:
        core._select(answer.ask, answer.tell)
    assert raised.value.options == ("one", "two")


def test_no_eligible_wallet_offers_an_empty_list_rather_than_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, _fake = _client(monkeypatch, {})
    answer = wallet_setup._Answer("anything", quoted=True)
    with pytest.raises(BitcoinCoreError, match="waiting"):
        core._select(answer.ask, answer.tell)


def test_a_wallet_name_with_quotes_is_matched_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    tricky = 'a "quoted". name'
    core, _fake = _client(monkeypatch, {tricky: _Wallet(), "plain": _Wallet()})
    answer = wallet_setup._Answer(tricky, quoted=True)
    assert core._select(answer.ask, answer.tell) == tricky


def test_the_passphrase_never_reaches_a_command_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    core, fake = _client(monkeypatch, {})
    wallet_setup.create(core, "fresh", PASSPHRASE)
    wallet_setup.unlock(core, "fresh", PASSPHRASE)
    assert fake.runs
    for command, supplied in fake.runs:
        assert not any(PASSPHRASE in item for item in command), command
        if PASSPHRASE in (supplied or ""):
            assert "-stdin" in command or "-stdinwalletpassphrase" in command


def test_the_passphrase_travels_on_the_dedicated_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    core, fake = _client(monkeypatch, {"fresh": _Wallet(True, True)})
    wallet_setup.unlock(core, "fresh", PASSPHRASE)
    command, supplied = next(run for run in fake.runs if "walletpassphrase" in run[0])
    assert "-stdinwalletpassphrase" in command
    assert supplied == PASSPHRASE + "\n"
    assert str(wallet_setup.UNLOCK_SECONDS) in command


def test_wallet_creation_uses_one_fixed_set_of_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    core, fake = _client(monkeypatch, {})
    wallet_setup.create(core, "fresh", PASSPHRASE)
    command, supplied = fake.runs[0]
    assert "-named" in command and "createwallet" in command
    assert supplied is not None
    assert _lines(supplied)[:3] == ["wallet_name=fresh", "disable_private_keys=false", "blank=true"]
    assert _lines(supplied)[3] == f"passphrase={PASSPHRASE}"
    assert len(_lines(supplied)) == 4


def test_a_wallet_created_without_a_passphrase_carries_no_passphrase_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, fake = _client(monkeypatch, {})
    wallet_setup.create(core, "fresh", "")
    assert fake.runs[0][1] is not None
    assert len(_lines(fake.runs[0][1])) == 3


@pytest.mark.parametrize("name", ["", " leading", "trailing ", "two\nlines", "bell\x07"])
def test_unusable_wallet_names_are_refused_before_bitcoin_core_sees_them(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    core, fake = _client(monkeypatch, {})
    with pytest.raises(BitcoinCoreError, match="printable text"):
        wallet_setup.create(core, name, "")
    assert fake.runs == []


@pytest.mark.parametrize("name", ["..", ".", "over/there", "back\\slash", "../../elsewhere"])
def test_a_wallet_name_cannot_describe_a_path(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    core, fake = _client(monkeypatch, {})
    with pytest.raises(BitcoinCoreError, match="slash"):
        wallet_setup.create(core, name, "")
    assert fake.runs == []


@pytest.mark.parametrize("passphrase", ["", "two\nlines", "carriage\rreturn"])
def test_a_passphrase_that_cannot_survive_the_channel_is_refused(
    monkeypatch: pytest.MonkeyPatch, passphrase: str
) -> None:
    core, fake = _client(monkeypatch, {"fresh": _Wallet(True, True)})
    with pytest.raises(BitcoinCoreError, match="line break"):
        wallet_setup.unlock(core, "fresh", passphrase)
    assert fake.runs == []


def test_an_unlock_that_leaves_the_wallet_locked_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    core, fake = _client(monkeypatch, {"fresh": _Wallet(True, True)})
    original = _Core._reply

    def stubborn(self: _Core, method: str, arguments: list[str], name: str | None) -> str:
        """Accept the passphrase call, but leave the wallet locked anyway."""
        return "" if method == "walletpassphrase" else original(self, method, arguments, name)

    monkeypatch.setattr(_Core, "_reply", stubborn)
    with pytest.raises(BitcoinCoreError, match="no longer an empty one"):
        wallet_setup.unlock(core, "fresh", PASSPHRASE)
    assert fake.called("walletlock")


def test_a_wallet_that_stops_being_eligible_is_locked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bitcoin Core has taken the passphrase by then, so the wallet is open until it is shut."""
    core, fake = _client(monkeypatch, {"fresh": _Wallet(True, True)})
    original = _Core._reply

    def filled(self: _Core, method: str, arguments: list[str], name: str | None) -> str:
        if method == "listdescriptors" and self.wallets["fresh"].locked is False:
            return json.dumps({"descriptors": [{"desc": "wpkh(xpub)", "active": True}]})
        return original(self, method, arguments, name)

    monkeypatch.setattr(_Core, "_reply", filled)
    with pytest.raises(BitcoinCoreError, match="locked it again|no longer an empty one"):
        wallet_setup.unlock(core, "fresh", PASSPHRASE)
    assert fake.called("walletlock")
    assert fake.wallets["fresh"].locked


def test_an_import_that_fails_before_the_library_arms_its_own_relock_still_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, fake = _client(monkeypatch, {"fresh": _Wallet(True, True)})

    def refuse(*_arguments: object, **_keywords: object) -> str:
        raise BitcoinCoreError("Bitcoin Core is waiting for something to be done in its own window.")

    monkeypatch.setattr(wallet_setup, "initialize", refuse)
    with pytest.raises(BitcoinCoreError, match="waiting"):
        wallet_setup.fill(core, _SEED, "fresh", PASSPHRASE)
    assert fake.called("walletlock")
    assert fake.wallets["fresh"].locked


def test_an_unlock_is_not_attempted_when_no_passphrase_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, fake = _client(monkeypatch, {"fresh": _Wallet()})
    monkeypatch.setattr(wallet_setup, "initialize", lambda *_a, **_k: "fresh")
    assert wallet_setup.fill(core, _SEED, "fresh", "") == "fresh"
    assert not fake.called("walletpassphrase")
    assert not fake.called("walletlock")


def test_the_chain_the_operator_chose_is_the_one_that_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One chain answering after another stopped must not quietly stand in for it."""
    monkeypatch.setattr(
        wallet_setup.BitcoinCore,
        "connect",
        classmethod(lambda _cls, _ask, _tell: BitcoinCore("bitcoin-cli", "main", 320000)),
    )
    assert wallet_setup.connect("mainnet").chain == "main"
    with pytest.raises(wallet_setup.Offer) as raised:
        wallet_setup.connect("signet")
    assert raised.value.options == ("mainnet",)


def test_the_version_is_reported_the_way_bitcoin_core_reports_it() -> None:
    assert wallet_setup.version_text(BitcoinCore("bitcoin-cli", "main", 320100)) == "32.1.0"


def test_recovery_identity_formats_a_full_sha256_commitment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        BitcoinCore,
        "recovery_identity",
        lambda _self, _secret: (bytes.fromhex("3f3521a6"), bytes(range(32))),
    )
    fingerprint, commitment = wallet_setup.identity(BitcoinCore("bitcoin-cli", "main", 320000), _SEED)
    assert fingerprint == "3f3521a6"
    assert commitment == ("0001 0203 0405 0607 0809 0A0B 0C0D 0E0F 1011 1213 1415 1617 1819 1A1B 1C1D 1E1F")


def test_recovery_commitment_match_ignores_only_case_and_whitespace() -> None:
    expected = "0123 4567 89AB CDEF" * 4
    assert wallet_setup.commitment_matches(expected, "0123456789abcdef" * 4)
    assert wallet_setup.commitment_matches(expected, "  0123 4567 89ab cdef  " * 4)
    assert not wallet_setup.commitment_matches(expected, "0123456789abcdef" * 3)
    assert not wallet_setup.commitment_matches(expected, "f123456789abcdef" + "0123456789abcdef" * 3)
