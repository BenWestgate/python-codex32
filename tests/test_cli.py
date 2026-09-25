"""CLI workflows, confirmation boundaries, and secret output channels."""

import builtins
import contextlib
import importlib
import io
import re
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO

from codex32 import (
    ConfirmationResult,
    CoreLightningSecret,
    CorrectionCandidate,
    CorrectionContext,
    MasterSeed,
    Profile,
    Secret,
    Share,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import _chars_to_u5, bech32_encode
from codex32.checksums import _CODEX32, _CODEX32_LONG
from codex32.cli import main, ms_main
from codex32.generation import _fingerprint_identifier
from codex32.profiles.ms32 import SEED_BYTE_LENGTHS
from tools._wallet_test_vectors import stub_fingerprint


@dataclass(frozen=True)
class _Result:
    exit_code: int
    stdout: str
    stderr: str


class _FakeLineEditor:
    def __init__(self) -> None:
        self.auto_history: list[bool] = []
        self.inserted: list[str] = []
        self.hook: Callable[[], object] | None = None

    def insert_text(self, text: str) -> None:
        self.inserted.append(text)

    def set_auto_history(self, enabled: bool) -> None:
        self.auto_history.append(enabled)

    def set_startup_hook(self, function: Callable[[], object] | None) -> None:
        self.hook = function

    def run_hook(self) -> None:
        if self.hook is not None:
            self.hook()


class _TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _CreationOutput(io.StringIO):
    def __init__(self, *, pretty: bool = False) -> None:
        super().__init__()
        self.pretty = pretty
        self.checks = 0

    def isatty(self) -> bool:
        self.checks += 1
        return self.pretty or self.checks == 1


@dataclass
class _FakeBitcoinCore:
    chain: str = "main"
    version: int = 320000
    imported: MasterSeed | None = None
    private: bool | None = None
    account: int | None = None
    timestamp: int | str | None = None

    def fingerprint_seed(self, seed: bytes) -> bytes:
        return stub_fingerprint(seed)

    def fingerprint(self, secret: MasterSeed) -> bytes:
        return self.fingerprint_seed(secret.seed_bytes)

    def initialize(
        self,
        secret: MasterSeed,
        _ask: Callable[[str], str],
        _tell: Callable[[str], None],
        *,
        private: bool = True,
        account: int = 0,
        timestamp: int | str = "now",
    ) -> str:
        self.imported = secret
        self.private, self.account, self.timestamp = private, account, timestamp
        return "test-wallet"


@pytest.fixture(autouse=True)
def _offline_core(monkeypatch):
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *args, **kwargs: _FakeBitcoinCore())


def _invoke(args: list[str], *lines: str) -> _Result:
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.object(sys, "stdin", stdin),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        entrypoint = ms_main if args[0] in {"create", "xprv", "wallet"} or "--bytes" in args else main
        status = entrypoint(args)
    return _Result(status, stdout.getvalue(), stderr.getvalue())


def _invoke_terminal(args: list[str], *lines: str) -> _Result:
    stdout, stderr = _TTYOutput(), io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO("\n".join(lines) + "\n")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = ms_main(args)
    return _Result(status, stdout.getvalue(), stderr.getvalue())


def _invoke_confirmed_create(
    args: list[str],
    *lines: str,
    terminal_output: bool = False,
    core: _FakeBitcoinCore | None = None,
) -> _Result:
    stdin = _TTYInput("\n".join(lines) + "\n")
    stdout = _CreationOutput(pretty=terminal_output)
    stderr = io.StringIO()

    def confirm_card(
        artifact: Share | Secret,
        confirm: Callable[[str], ConfirmationResult] | None = None,
    ) -> None:
        if confirm is not None:
            result = confirm(artifact.text)
            assert result.accepted

    with (
        patch.object(sys, "stdin", stdin),
        patch("codex32.cli._confirm_card", confirm_card),
        patch("codex32.cli.BitcoinCore.connect", return_value=core or _FakeBitcoinCore()),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = ms_main(args)
    return _Result(status, stdout.getvalue(), stderr.getvalue())


def _invoke_initialized_wallet(
    args: list[str],
    *lines: str,
    core: _FakeBitcoinCore | None = None,
) -> tuple[_Result, _FakeBitcoinCore]:
    selected = _FakeBitcoinCore() if core is None else core
    stdin, stdout, stderr = (
        _TTYInput("\n".join(lines) + "\n"),
        io.StringIO(),
        io.StringIO(),
    )
    with (
        patch.object(sys, "stdin", stdin),
        patch("codex32.cli.BitcoinCore.connect", return_value=selected),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = ms_main(args)
    return _Result(status, stdout.getvalue(), stderr.getvalue()), selected


def _installed_cli() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return Path(sysconfig.get_path("scripts")) / f"codex32{suffix}"


def _card_text(output: str) -> str:
    return "".join(re.sub(r"\x1b\[[0-9;]*m", "", output.strip().splitlines()[-1]).split())


def _output_artifacts(result: _Result, profile: str = "ms") -> list[Share | Secret]:
    lines = (re.sub(r"\x1b\[[0-9;]*m", "", line) for line in result.stdout.splitlines())
    return [parse_codex32("".join(line.split())) for line in lines if line.lower().startswith(profile + "1")]


def test_check_supports_every_registered_application() -> None:
    strings = (
        VECTOR_1["secret_s"],
        VECTOR_3["secret_s"],
        VECTOR_2["share_A"],
        VECTOR_6["codex32_cln2"],
        BIP39_12W_ZERO,
        SHARING_VECTORS["bip39_24w"]["S"],
    )
    result = _invoke(["check"], *strings)

    assert result.exit_code == 0
    assert result.stdout == (
        "Valid unshared Bitcoin master seed.\n"
        "Backup identifier: TEST\n\n"
        "Valid shared Bitcoin master seed.\n"
        "Backup identifier: CASH\n"
        "Shares needed for recovery: 3\n\n"
        "Valid Bitcoin master-seed share A.\n"
        "Backup identifier: NAME\n"
        "Shares needed for recovery: 2\n\n"
        "Valid unshared Core Lightning HSM secret.\n"
        "Backup identifier: CLN2\n\n"
        "Valid unshared 12-word BIP39 worksheet.\n"
        "Backup identifier: TEST\n\n"
        "Valid shared 24-word BIP39 worksheet.\n"
        "Backup identifier: TEST\n"
        "Shares needed for recovery: 2\n"
    )
    assert result.stderr == ""
    assert all(text not in result.stdout for text in strings)
    for forbidden in (
        "Header(",
        "Master fingerprint:",
        "Type: ms",
        "Type: cl",
        "Type: bip39",
        "Type:",
        "Identifier:",
    ):
        assert forbidden not in result.stdout


@pytest.mark.parametrize(
    "value",
    (SHARING_VECTORS["cl"]["A"], SHARING_VECTORS["cl"]["S"]),
)
def test_check_accepts_shared_core_lightning_artifacts(value: str) -> None:
    result = _invoke(["check"], value)

    assert result.exit_code == 0
    assert "Core Lightning HSM" in result.stdout
    assert result.stderr == ""


def test_check_does_not_derive_wallet_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_module = importlib.import_module("codex32.cli")

    def forbidden(_seed: bytes) -> bytes:
        raise AssertionError("check derived a BIP32 fingerprint")

    monkeypatch.setattr(cli_module, "_connected_core", forbidden)
    result = _invoke(["check"], VECTOR_1["secret_s"])

    assert result.exit_code == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("hrp", "payload_length", "message"),
    (
        (
            "ms",
            25,
            ("A Bitcoin master-seed backup must have exactly 48, 54, 61, 67, 74, or 127 characters."),
        ),
        (
            "ms",
            104,
            ("A Bitcoin master-seed backup must have exactly 48, 54, 61, 67, 74, or 127 characters."),
        ),
        (
            "ms",
            27,
            ("A Bitcoin master-seed backup must have exactly 48, 54, 61, 67, 74, or 127 characters."),
        ),
        (
            "cl",
            51,
            ("This input has 73 characters. A Core Lightning HSM secret backup must have exactly 74."),
        ),
        (
            "bip39_12w",
            26,
            ("This input has 55 characters. A 12-word BIP39 worksheet backup must have exactly 56."),
        ),
        (
            "bip39_24w",
            52,
            ("This input has 81 characters. A 24-word BIP39 worksheet backup must have exactly 82."),
        ),
    ),
)
def test_check_reports_profile_lengths_for_people(hrp: str, payload_length: int, message: str) -> None:
    body = _chars_to_u5("0tests" + "q" * payload_length)
    expanded_body_length = 2 * len(hrp) + 1 + len(body)
    checksum = _CODEX32 if expanded_body_length <= 80 else _CODEX32_LONG
    result = _invoke(["check"], bech32_encode(hrp, body, checksum))

    assert result.exit_code == 2
    assert message in result.stderr


def test_tty_check_prefills_rejected_entry_without_history(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    valid = VECTOR_1["secret_s"]
    rejected = valid[:-1] + valid[-1].upper()
    answers = iter((rejected, valid))
    editor = _FakeLineEditor()
    display_streams: list[bool] = []
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        display_streams.append(sys.stdout is sys.stderr)
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert editor.inserted == [rejected]
    assert editor.auto_history == [False, False]
    assert editor.hook is None
    assert display_streams == [True, True]
    assert sys.stdout is not sys.stderr
    assert prompts == ["Enter a codex32 string:\n> "] * 2
    assert rejected not in captured.out
    assert "Rejected: Use either all uppercase or all lowercase letters." in captured.err
    assert "Rejected: Use either all uppercase or all lowercase letters.\n\n" in captured.err
    assert captured.err.endswith("\n\n")


def test_tty_check_reports_truncated_ms_length_before_checksum(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    truncated = (
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nl",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6n",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6",
    )
    answers = iter((*truncated, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    for length in (47, 46, 45):
        assert f"Rejected: This input has {length} characters." in captured.err
    assert "The checksum does not match." not in captured.err
    assert captured.err.count("Bitcoin master-seed backup must have") == 3


def test_tty_check_names_an_invalid_character_and_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    invalid = "MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW'"
    answers = iter((invalid, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["check"]) == 0
    assert (
        "Rejected: Apostrophe (') is not allowed in a codex32 string (position 49)."
    ) in capsys.readouterr().err


def test_tty_check_explains_header_and_prefix_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    invalid = (
        "ms10fauxxxxxxxxxxxxxxxxxxxxxxxxxxxx0z26tfn0ulw3p",
        "ms1fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxda3kr3s0s2swg",
        "0fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "m10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "s10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    )
    answers = iter((*invalid, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["check"]) == 0
    rejected = [line for line in capsys.readouterr().err.splitlines() if line.startswith("Rejected:")]
    assert rejected == [
        "Rejected: An unshared secret (threshold 0) must use S as its index.",
        "Rejected: The threshold must be 0 or a number from 2 through 9; found 'f'.",
        "Rejected: No separator (1) was found.",
        "Rejected: The application prefix before 1 is missing.",
        "Rejected: The checksum does not match.",
        "Rejected: The checksum does not match.",
    ]


def test_tty_retry_replaces_only_the_editable_suffix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prefix = "ms12name"
    suffix = VECTOR_2["share_C"][len(prefix) :]
    first, second = ("Q", "P") if suffix.isupper() else ("q", "p")
    bad_one = suffix[:-1] + (first if suffix[-1] != first else second)
    replacement = first if suffix[-2] != first else second
    bad_two = suffix[:-2] + replacement + suffix[-1]
    answers = iter((VECTOR_2["share_A"], bad_one, "n", bad_two, "n", suffix))
    editor = _FakeLineEditor()

    def answer(_prompt: str) -> str:
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert editor.inserted == [bad_one, bad_two]
    assert editor.hook is None
    assert editor.auto_history == [False] * 6
    assert "Rejected:" not in captured.err


@pytest.mark.parametrize(
    ("command", "expected"),
    [(["xprv"], VECTOR_1["xprv"]), (["wallet"], "")],
)
def test_tty_wallet_commands_retry_silently_after_declining_correction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
    expected: str,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    original = VECTOR_1["secret_s"]
    damaged = original[:20] + ("q" if original[20] != "q" else "p") + original[21:]
    answers = iter((damaged[3:], "n", damaged[3:], "yes"))
    prompts: list[str] = []
    prefills: list[str] = []

    def answer(prompt: str, prefill: str = "") -> str:
        prompts.append(prompt)
        prefills.append(prefill)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", answer)

    assert ms_main(command) == 0
    captured = capsys.readouterr()
    assert captured.out.strip().startswith(expected)
    if command[0] == "wallet":
        assert "Possible correction:\n\nMaster fingerprint: 3F3521A6\n\n" in captured.err
    else:
        assert "Master fingerprint:" not in captured.err
    assert input_module._card_text(original, False) in captured.err
    assert "> " not in captured.err
    assert prompts[0] == "Enter a codex32 string:\n> MS1"
    assert prompts[2] == "Enter a codex32 string:\n> ms1"
    assert prompts[-1] == "Does this entire string exactly match your recovery card? [y/N]: "
    assert prefills == ["", "", damaged[3:], ""]
    assert "Rejected:" not in captured.err


def test_xprv_corrects_an_uppercase_first_share(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    corrected = VECTOR_2["share_C"].upper()
    answers = iter((corrected[:-8], "n", VECTOR_1["secret_s"]))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))

    assert ms_main(["xprv"]) == 0
    captured = capsys.readouterr()
    assert input_module._card_text(corrected, False) in captured.err
    assert "Possible correction:" in captured.err
    assert captured.out.strip() == VECTOR_1["xprv"]


def test_xprv_suggests_mixed_case_input_with_symbol_errors(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    damaged = "MS12namedll4f8jkh4e5vdvuldlfxu2jhdnlSM97xcenrxeg"
    prefix = "ms12name"
    answers = iter((damaged[3:], "y", VECTOR_2["share_A"][len(prefix) :].lower()))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))

    assert ms_main(["xprv"]) == 0
    captured = capsys.readouterr()
    assert input_module._card_text(VECTOR_2["derived_D"], False) in captured.err
    assert "Possible correction:" in captured.err
    assert "Rejected:" not in captured.err
    assert captured.out.strip() == VECTOR_2["xprv"]


def test_xprv_groups_the_next_prefix_after_spaced_correction(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    damaged = "NAME DLL4 F8JL  H4E5 VDVU LDLF XU2J  HDNL SM97 XVEN r"
    prefix = "MS12NAME"
    answers = iter((damaged, "y", VECTOR_2["share_A"][len(prefix) :]))
    prompts: list[str] = []

    def answer(prompt: str, _prefill: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", answer)

    assert ms_main(["xprv"]) == 0
    captured = capsys.readouterr()
    assert "Possible correction:" in captured.err
    assert prompts[2] == "Enter share 2 of 2:\n> MS12 NAME "
    assert captured.out.strip() == VECTOR_2["xprv"]


def test_xprv_explains_prefilled_threshold_and_uncorrectable_length(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    short = "2 NAME DLL4 F8JL H4E5 VDVU LDLF XU2J HDNL SM9"
    answers = iter(("NAME DLL4 F8JL H4E5 VDVU LDLF XU2J HDNL SM97", short, VECTOR_1["secret_s"]))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))

    assert ms_main(["xprv"]) == 0
    rejected = [line for line in capsys.readouterr().err.splitlines() if line.startswith("Rejected:")]
    assert rejected == [
        "Rejected: After the prefilled MS1, enter a threshold of 0 or 2 through 9; found 'n'.",
        (
            "Rejected: The string has 39 characters; valid Bitcoin master-seed codex32 lengths are "
            "48, 54, 61, 67, 74, or 127 characters."
        ),
    ]


def test_xprv_reports_every_uncorrectable_prefixed_ms_length(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    lengths = (39, 100, 136)
    invalid = tuple(("MS10TESTS" + "Q" * length)[3:length] for length in lengths)
    answers = iter((*invalid, VECTOR_1["secret_s"]))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))

    assert ms_main(["xprv"]) == 0
    output = capsys.readouterr().err
    for length in lengths:
        assert f"The string has {length} characters; valid Bitcoin master-seed codex32 lengths are" in output


def test_prefixed_ms_lengths_at_correction_boundary_explain_length_and_still_search(
    monkeypatch, capsys
) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    lengths = (40, 135)
    invalid = tuple(("MS10TESTS" + "Q" * length)[3:length] for length in lengths)
    answers = iter((*invalid, VECTOR_1["secret_s"]))
    searched: list[str] = []

    def suggestions(value, *_args, **_kwargs):
        searched.append(value)
        return ()

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))
    monkeypatch.setattr(input_module, "_suggestions", suggestions)

    assert ms_main(["xprv"]) == 0
    output = capsys.readouterr().err
    assert [len(value) for value in searched] == list(lengths)
    for length in lengths:
        assert f"Rejected: This input has {length} characters." in output
    assert "The checksum does not match." not in output
    assert "valid Bitcoin master-seed codex32 lengths" not in output


def test_complete_paste_keeps_ordinary_threshold_error(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    answers = iter(("MS1NAME DLL4 F8JL H4E5 VDVU LDLF XU2J HDNL SM97", VECTOR_1["secret_s"]))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))
    monkeypatch.setattr(input_module, "_suggestions", lambda *_args, **_kwargs: ())

    assert ms_main(["xprv"]) == 0
    output = capsys.readouterr().err
    assert "Rejected: The threshold must be 0 or a number from 2 through 9; found 'n'." in output
    assert "After the prefilled" not in output


@pytest.mark.parametrize(("difference", "word"), ((-9, "short of"), (9, "too long for")))
def test_subsequent_prefixed_ms_input_reports_required_set_length(
    monkeypatch, capsys, difference, word
) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    prefix = "MS12NAME"
    suffix = VECTOR_2["share_C"][len(prefix) :]
    damaged = suffix[:difference] if difference < 0 else suffix + "Q" * difference
    answers = iter((VECTOR_2["share_A"], damaged, suffix))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(input_module, "_editable_input", lambda _prompt, _prefill="": next(answers))

    assert main(["secret", "--plain"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == VECTOR_2["secret_S"]
    assert (
        f"Rejected: The string is 9 characters {word} the required {len(VECTOR_2['share_C'])}-character "
        "length."
    ) in output.err


@pytest.mark.parametrize(
    ("prefix", "suffix", "expected"),
    (
        ("MS1", "2namedll4f8jkh4e5vdvuldlfxu2jhdnlSM97xcenrxeg", "ms1"),
        ("ms12name", "DLL4F8JLH4E5VDVULDLFXU2JHDNLSM97XVENRXEG", "MS12NAME"),
    ),
)
def test_fixed_prefix_follows_prevailing_suffix_case(prefix: str, suffix: str, expected: str) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    assert input_module._prefix_for_suffix(prefix, suffix) == expected


@pytest.mark.parametrize(
    "command",
    (
        ("xprv",),
        ("wallet",),
    ),
)
def test_wallet_paths_accept_a_suffix_after_frozen_ms1(
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    prompts: list[str] = []

    def answer(prompt: str, _prefill: str = "") -> str:
        prompts.append(prompt)
        return VECTOR_1["secret_s"][3:]

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_editable_input", answer)
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *_args: _FakeBitcoinCore())

    assert ms_main(command) == 0
    assert prompts[0] == "Enter a codex32 string:\n> MS1"


@pytest.mark.parametrize(
    "command",
    (
        ("xprv",),
        ("wallet",),
    ),
)
def test_wallet_recovery_recases_later_header_from_suffix(
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    prefix = "ms12name"
    answers = iter((VECTOR_2["share_A"].lower(), VECTOR_2["share_C"][len(prefix) :].upper()))
    prompts: list[str] = []

    def answer(prompt: str, _prefill: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_editable_input", answer)
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *_args: _FakeBitcoinCore())

    assert ms_main(command) == 0
    assert prompts[:2] == [
        "Enter a codex32 string:\n> MS1",
        "Enter share 2 of 2:\n> ms12name",
    ]


def test_redirected_recovery_never_attempts_correction() -> None:
    original = VECTOR_1["secret_s"]
    damaged = original[:-1] + ("q" if original[-1] != "q" else "p")
    with patch("codex32.indel._search_many") as search:
        result = _invoke(["check"], damaged)

    assert result.exit_code == 2
    search.assert_not_called()


def test_redirected_check_uses_friendly_checksum_message() -> None:
    valid = VECTOR_1["secret_s"]
    damaged = valid[:-1] + ("q" if valid[-1] != "q" else "p")
    result = _invoke(["check"], damaged)

    assert result.exit_code == 2
    assert result.stderr == "codex32 check: The checksum does not match.\n"


def test_tty_retry_without_line_editor_uses_an_empty_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    valid = VECTOR_1["secret_s"]
    rejected = valid[:-1] + valid[-1].upper()
    answers = iter((rejected, valid))
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(builtins, "input", answer)

    assert main(["check"]) == 0
    assert "Valid unshared Bitcoin master seed." in capsys.readouterr().out
    assert prompts == ["Enter a codex32 string:\n> "] * 2


def test_tty_display_file_descriptor_is_restored_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Stream:
        def __init__(self, descriptor: int) -> None:
            self.descriptor = descriptor
            self.flushes = 0

        def fileno(self) -> int:
            return self.descriptor

        def flush(self) -> None:
            self.flushes += 1

    stdout, stderr = Stream(10), Stream(11)
    duplications: list[tuple[int, int]] = []
    closed: list[int] = []
    monkeypatch.setattr(input_module.sys, "stdout", stdout)
    monkeypatch.setattr(input_module.sys, "stderr", stderr)
    monkeypatch.setattr(input_module.os, "dup", lambda _descriptor: 12)
    monkeypatch.setattr(
        input_module.os,
        "dup2",
        lambda source, target: duplications.append((source, target)),
    )
    monkeypatch.setattr(input_module.os, "close", closed.append)

    with (
        pytest.raises(RuntimeError, match="input failed"),
        input_module._input_display(),
    ):
        raise RuntimeError("input failed")

    assert duplications == [(11, 10), (12, 10)]
    assert closed == [12]
    assert stdout.flushes == 2


def test_secret_recovers_official_ms_and_bip39_sets() -> None:
    ms = _invoke(["secret"], VECTOR_2["share_A"], VECTOR_2["share_C"])
    bip39 = _invoke(
        ["secret"],
        SHARING_VECTORS["bip39_12w"]["A"],
        SHARING_VECTORS["bip39_12w"]["C"],
    )

    assert ms.exit_code == bip39.exit_code == 0
    assert ms.stdout.strip() == VECTOR_2["secret_S"]
    assert bip39.stdout.strip() == SHARING_VECTORS["bip39_12w"]["S"]


def test_secret_accepts_core_lightning() -> None:
    result = _invoke(["secret"], VECTOR_6["codex32_cln2"])

    assert result.exit_code == 0
    assert result.stdout.strip() == VECTOR_6["codex32_cln2"]
    assert result.stderr == ""


def test_artifact_output_is_pretty_only_at_a_terminal() -> None:
    formatted = _invoke_terminal(["secret"], VECTOR_1["secret_s"])
    output = formatted.stdout

    assert formatted.exit_code == 0 and formatted.stderr.strip() == ""
    assert output.startswith("Unshared Bitcoin master seed.\n")
    assert "Master fingerprint:" in output
    assert all(code in output for code in ("\x1b[1m", "\x1b[22m", "\x1b[0m"))
    grouped = output.splitlines()[-1]
    assert "\x1b[1mMS10 \x1b[22mTEST \x1b[1mSXXX \x1b[22mXXXX  \x1b[1mXXXX" in grouped

    plain = _invoke_terminal(["secret", "--plain"], VECTOR_1["secret_s"])
    assert plain.stdout.strip() == VECTOR_1["secret_s"]
    assert "\x1b[" not in plain.stdout

    help_output = _invoke(["secret", "-h"]).stdout
    assert "--plain" in help_output and "--pretty" not in help_output
    assert _invoke(["secret", "--pretty"], VECTOR_1["secret_s"]).exit_code == 2


def test_tty_direct_secret_needs_no_acceptance_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", lambda _prompt: VECTOR_1["secret_s"])

    assert main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_1["secret_s"]
    assert captured.err == "\n"


def test_tty_recovery_accepts_suffix_after_fixed_prefix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prefix = "ms12name"
    answers = iter((VECTOR_2["share_A"], VECTOR_2["share_C"][len(prefix) :]))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert "Share 1 of 2 accepted." in captured.err
    assert "Share 2 of 2 accepted." not in captured.err
    assert prompts == ["Enter a codex32 string:\n> ", "Enter share 2 of 2:\n> MS12NAME"]


def test_tty_subsequent_correction_recases_confirmed_immutable_context(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prefix = "ms12name"
    expected = VECTOR_2["share_C"].lower()
    damaged = expected[:20] + ("q" if expected[20] != "q" else "p") + expected[21:]
    answers = iter((VECTOR_2["share_A"], damaged, "y"))
    indel = importlib.import_module("codex32.indel")
    original_search = indel._search_many
    contexts: list[tuple[CorrectionContext, ...]] = []

    def search(active: tuple[CorrectionContext, ...], value: str, **kwargs: object):
        contexts.append(active)
        return original_search(active, value, **kwargs)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(indel, "_search_many", search)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert ms_main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["secret_S"].lower()
    assert "Possible correction:\n\nMaster fingerprint: FAB6868A\n\n" in captured.err
    assert input_module._card_text(expected, False) in captured.err
    assert contexts == [(CorrectionContext(Profile.MS, len(VECTOR_2["share_A"]), prefix, ("a",)),)]


def test_tty_recovery_accepts_complete_uppercase_and_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    first = VECTOR_2["share_A"].upper()
    mismatch = SHARING_VECTORS["bip39_12w"]["C"].upper()
    answers = iter((first, mismatch, first, VECTOR_2["share_C"].upper()))
    editor = _FakeLineEditor()

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"].upper()
    assert prompts == [
        "Enter a codex32 string:\n> ",
        "Enter share 2 of 2:\n> MS12NAME",
        "Enter share 2 of 2:\n> MS12NAME",
        "Enter share 2 of 2:\n> MS12NAME",
    ]
    assert "Rejected: These strings are for different applications." in captured.err
    assert "Rejected: That share index was already entered." in captured.err
    assert first not in captured.err and mismatch not in captured.err
    assert editor.inserted == []
    assert editor.hook is None


def test_tty_recovery_uses_lowercase_header_after_alternating_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    prefix = "ms13cash"
    answers = iter(
        (
            VECTOR_3["derived_f"].upper(),
            VECTOR_3["share_c"].lower(),
            VECTOR_3["share_a"][len(prefix) :].upper(),
        )
    )
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["secret", "--plain"]) == 0
    assert prompts == [
        "Enter a codex32 string:\n> ",
        "Enter share 2 of 3:\n> MS13CASH",
        "Enter share 3 of 3:\n> ms13cash",
    ]


def test_tty_recovery_suggests_a_uniformly_cased_suffix(monkeypatch, capsys) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    prefix = "ms12name"
    suffix = VECTOR_2["share_C"][len(prefix) :].lower()
    answers = iter((VECTOR_2["share_A"].lower(), suffix[0].upper() + suffix[1:], "y"))

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["secret", "--plain"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == VECTOR_2["secret_S"].lower()
    assert "Possible correction:" in output.err
    assert "Rejected:" not in output.err


@pytest.mark.parametrize("profile", ("bip39_12w", "bip39_24w"))
def test_bip39_recovery_accepts_later_suffix_in_another_case(monkeypatch, profile: str) -> None:
    input_module = importlib.import_module("codex32._cli_input")
    first = SHARING_VECTORS[profile]["A"].upper()
    second = SHARING_VECTORS[profile]["C"]
    prefix = f"{profile}12test"
    answers = iter((first, second[len(prefix) :]))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["secret", "--plain"]) == 0
    assert prompts[1] == f"Enter share 2 of 2:\n> {prefix.upper()}"


@pytest.mark.parametrize(
    "command",
    (
        ("secret", "--plain"),
        ("xprv",),
        ("wallet",),
    ),
)
def test_tty_recovery_accepts_secret_after_compatible_shares(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    answers = iter((VECTOR_3["derived_f"], VECTOR_3["share_c"], VECTOR_3["secret_s"]))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *_args: _FakeBitcoinCore())

    assert (main if command[0] == "secret" else ms_main)(command) == 0
    captured = capsys.readouterr()
    if command[0] != "wallet":
        assert captured.out
    assert "Rejected:" not in captured.err
    assert "Share 1 of 3 accepted." in captured.err
    assert "Share 2 of 3 accepted." in captured.err
    first_prompt = (
        "Enter a codex32 string:\n> " if command[0] == "secret" else "Enter a codex32 string:\n> MS1"
    )
    assert prompts == [
        first_prompt,
        "Enter share 2 of 3:\n> ms13cash",
        "Enter share 3 of 3:\n> ms13cash",
    ]


def test_tty_share_collects_secret_and_exact_basis(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prefix = "ms13cash"
    answers = iter(
        (
            VECTOR_3["secret_s"],
            VECTOR_3["share_a"][len(prefix) :],
            VECTOR_3["share_c"][len(prefix) :],
        )
    )
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *_args: _FakeBitcoinCore())

    assert main(["share", "d"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_3["derived_d"]
    assert prompts == [
        "Enter a codex32 string:\n> ",
        "Enter string 2 of 3:\n> ms13cash",
        "Enter string 3 of 3:\n> ms13cash",
    ]
    assert "String 1 of 3 accepted." in captured.err
    assert "String 2 of 3 accepted." in captured.err
    assert "String 3 of 3 accepted." not in captured.err


@pytest.mark.parametrize(("exception", "status"), ((EOFError(), 2), (KeyboardInterrupt(), 130)))
def test_tty_interrupts_have_stable_statuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception: BaseException,
    status: int,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    valid = VECTOR_1["secret_s"]
    rejected = valid[:-1] + valid[-1].upper()
    answers: list[str | BaseException] = [rejected, exception]
    editor = _FakeLineEditor()

    def answer(_prompt: str) -> str:
        editor.run_hook()
        value = answers.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["secret"]) == status
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "Possible correction:" in captured.err
    assert editor.inserted == []
    assert editor.hook is None


def test_share_supports_ms_cl_and_bip39() -> None:
    ms = _invoke(["share", "d"], VECTOR_2["share_A"], VECTOR_2["share_C"])
    cl = _invoke(
        ["share", "d"],
        SHARING_VECTORS["cl"]["A"],
        SHARING_VECTORS["cl"]["C"],
    )
    bip39 = _invoke(
        ["share", "d"],
        SHARING_VECTORS["bip39_12w"]["A"],
        SHARING_VECTORS["bip39_12w"]["C"],
    )

    assert ms.exit_code == 0
    assert ms.stdout.strip() == VECTOR_2["derived_D"]
    assert cl.exit_code == bip39.exit_code == 0
    assert cl.stdout.strip() == SHARING_VECTORS["cl"]["D"]
    assert bip39.stdout.strip() == SHARING_VECTORS["bip39_12w"]["D"]


@pytest.mark.parametrize("index", ("b", "i", "1", "s", "aa"))
def test_share_rejects_invalid_target_before_prompting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    index: str,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    def forbidden(_prompt: str) -> str:
        raise AssertionError("invalid target prompted for protected input")

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", forbidden)

    assert main(["share", index]) == 2
    assert capsys.readouterr().err == (
        "codex32 share: Choose one share index from ACDEFGHJKLMNPQRTUVWXYZ023456789.\n"
    )


def test_share_argument_errors_are_actionable() -> None:
    missing = _invoke(["share"])

    assert missing.exit_code == 2
    assert missing.stderr == (
        "usage: codex32 share [-h] [--plain] INDEX\n"
        "codex32 share: Choose an index for the additional share.\n"
    )


def test_tty_share_rejects_target_index_as_soon_as_entered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    answers = iter((VECTOR_2["derived_D"], VECTOR_2["share_A"], VECTOR_2["share_C"]))
    editor = _FakeLineEditor()

    def answer(_prompt: str) -> str:
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["share", "d"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["derived_D"]
    assert "Rejected: That index was requested for the additional share." in captured.err
    assert editor.inserted == []


def test_create_defaults_to_an_unshared_128_bit_master_seed() -> None:
    result = _invoke_confirmed_create(["create"])
    artifacts = _output_artifacts(result)

    assert result.exit_code == 0
    assert len(artifacts) == 1
    secret = artifacts[0]
    assert isinstance(secret, MasterSeed) and len(secret.seed_bytes) == 16
    assert secret.header.threshold == 0
    assert secret.header.identifier == _fingerprint_identifier(stub_fingerprint(secret.seed_bytes))


def test_fresh_bitcoin_terminal_and_core_preflight_precede_entropy() -> None:
    with (
        patch("codex32.cli.BitcoinCore.connect") as connect,
        patch("codex32.cli.generate_master_seed") as generate,
    ):
        redirected = _invoke(["create"])

    assert redirected.exit_code == 2
    assert "interactive terminal" in redirected.stderr
    connect.assert_not_called()
    generate.assert_not_called()

    stdout, stderr = _TTYOutput(), io.StringIO()
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli.BitcoinCore.connect", side_effect=RuntimeError("preflight")),
        patch("codex32.cli.generate_master_seed") as generate,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        pytest.raises(RuntimeError, match="preflight"),
    ):
        ms_main(["create"])
    generate.assert_not_called()

    stdout, stderr = _TTYOutput(), io.StringIO()
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli.BitcoinCore.connect", side_effect=RuntimeError("preflight")),
        patch("codex32.cli._creation_source") as source,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        pytest.raises(RuntimeError, match="preflight"),
    ):
        ms_main(["create", "--existing"])
    source.assert_not_called()


def test_confirmation_cannot_replace_the_original_seed_used_for_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = parse_codex32(VECTOR_1["secret_s"])
    assert isinstance(secret, MasterSeed)
    core = _FakeBitcoinCore()
    stdout, stderr = _TTYOutput(), io.StringIO()
    monkeypatch.setattr(builtins, "input", lambda _prompt: secret.text.upper())

    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli.generate_master_seed", return_value=secret),
        patch("codex32.cli.BitcoinCore.connect", return_value=core),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert ms_main(["create"]) == 0

    assert core.imported is secret


def test_existing_creation_preflights_then_initializes_from_the_recovered_seed() -> None:
    source = parse_codex32(VECTOR_4["secret_s"])
    assert isinstance(source, MasterSeed)
    core = _FakeBitcoinCore()

    result = _invoke_confirmed_create(
        ["create", "2", "--indices", "ac", "--existing"],
        source.text,
        core=core,
    )

    assert result.exit_code == 0
    assert core.imported is not None and core.imported.seed_bytes == source.seed_bytes
    assert core.timestamp == 0


@pytest.mark.parametrize("byte_length", SEED_BYTE_LENGTHS)
def test_fresh_cli_generation_supports_bip93_sizes(byte_length: int) -> None:
    result = _invoke_confirmed_create(["create", "--bytes", str(byte_length)])
    artifact = _output_artifacts(result)[0]

    assert result.exit_code == 0
    assert isinstance(artifact, MasterSeed)
    assert len(artifact.seed_bytes) == byte_length


def test_fresh_cli_generation_rejects_every_other_16_through_64_byte_size() -> None:
    for byte_length in set(range(16, 65)) - set(SEED_BYTE_LENGTHS):
        result = _invoke(["create", "--bytes", str(byte_length)])
        assert result.exit_code == 2
        assert result.stdout == ""
        assert "--bytes" in result.stderr and "invalid choice" in result.stderr


@pytest.mark.parametrize("byte_length", SEED_BYTE_LENGTHS)
def test_cli_import_preserves_all_bip93_master_seed_sizes(byte_length: int) -> None:
    raw = bytes(range(byte_length))
    core = _FakeBitcoinCore()
    result = _invoke_confirmed_create(["create", "--existing"], raw.hex(), core=core)
    assert core.timestamp == 0
    artifact = _output_artifacts(result)[0]

    assert result.exit_code == 0
    assert isinstance(artifact, MasterSeed)
    assert artifact.seed_bytes == raw


def test_cli_import_rejects_every_other_16_through_64_byte_size() -> None:
    for byte_length in set(range(16, 65)) - set(SEED_BYTE_LENGTHS):
        result = _invoke_confirmed_create(["create", "--existing"], bytes(byte_length).hex())
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "16, 20, 24, 28, 32, or 64" in result.stderr


def test_bare_create_requires_exact_confirmation_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    emitted: list[str] = []

    def answer(prompt: str) -> str:
        if prompt == "Write this secret on a new recovery card, then press Enter. ":
            emitted.append(_card_text(capsys.readouterr().out))
            return ""
        assert prompt == "Re-enter the secret from the recovery card:\n> "
        return emitted[-1].upper()

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", answer)

    with patch("codex32.cli.BitcoinCore.connect", return_value=_FakeBitcoinCore()):
        assert ms_main(["create"]) == 0
    artifact = parse_codex32(emitted[0])
    assert isinstance(artifact, MasterSeed)
    assert artifact.header.identifier == _fingerprint_identifier(stub_fingerprint(artifact.seed_bytes))


def test_fresh_shared_create_confirms_each_card_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    emitted: list[str] = []

    def answer(prompt: str) -> str:
        if prompt == "Write this share on a new recovery card, then press Enter. ":
            emitted.append(_card_text(capsys.readouterr().out))
            return ""
        assert prompt == "Re-enter the share from the recovery card:\n> "
        return emitted[-1]

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", answer)

    with patch("codex32.cli.BitcoinCore.connect", return_value=_FakeBitcoinCore()):
        assert ms_main(["create", "2", "--indices", "ac"]) == 0
    assert len(emitted) == 2
    assert all(isinstance(parse_codex32(text), Share) for text in emitted)


def test_shared_create_refuses_redirected_input() -> None:
    result = _invoke(["create", "2", "--indices", "ac"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "requires an interactive terminal" in result.stderr


def test_creation_confirmation_highlights_groups_without_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_module = importlib.import_module("codex32.cli")
    artifact = parse_codex32(VECTOR_2["share_A"])
    damaged = artifact.text[:4] + ("q" if artifact.text[4] != "q" else "p") + artifact.text[5:]
    answers = iter(("", damaged, artifact.text[4:8].upper()))
    prompts: list[tuple[str, dict[str, object]]] = []
    output = _TTYOutput()

    def answer(prompt: str, **options: object) -> str:
        prompts.append((prompt, options))
        return next(answers)

    monkeypatch.setattr(cli_module, "_text", answer)

    with contextlib.redirect_stderr(output):
        cli_module._confirm_card(artifact)

    message = output.getvalue()
    assert message.startswith("\n")
    assert "\x1b[1;7;31m" in message
    assert "group(s):" not in message
    assert artifact.text[4:8].upper() not in message
    assert damaged[4:8].upper() in message
    assert "\x1b[1;7;31m" in message
    assert "\x1b[1m" in message and "\x1b[22m" in message
    assert "\x1b[37m" not in message and "\x1b[97m" not in message
    assert prompts[2] == (
        "Review the marked text on your recovery card",
        {
            "prompt_end": ":\n> ",
            "preserve_groups": True,
            "optional": True,
            "prefill": damaged[4:8],
        },
    )
    assert sum(prompt.count("\x1b[3J\x1b[2J\x1b[H") for prompt, _options in prompts) == 1
    assert "\x1b[3J\x1b[2J\x1b[H" in prompts[1][0]


@pytest.mark.parametrize(
    ("observed", "shown", "red"),
    (
        ("abcdeXghijklmnop", "ABCD EXGH IJKL MNOP", 1),
        ("abcdefXghijklmnop", "ABCD EFXGH IJKL MNOP", 1),
        ("abcdefghXijklmnop", "ABCD EFGH XIJKL MNOP", 1),
        ("abcdeghijklmnop", "ABCD EGH IJKL MNOP", 1),
        ("aXcdefghijXlmnop", "AXCD EFGH IJXL MNOP", 2),
        ("abcdefghijklmnopX", "ABCD EFGH IJKL MNOPX", 1),
        ("abcdefghijklmnop", "ABCD EFGH ____ IJKL  MNOP", 1),
        ("aaaaaaa", "AAAA AAA", 1),
    ),
)
def test_confirmation_alignment_shows_only_entered_text(
    observed: str,
    shown: str,
    red: int,
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    expected = "abcdefghWXYZijklmnop" if observed == "abcdefghijklmnop" else "abcdefghijklmnop"
    if observed == "aaaaaaa":
        expected = "aaaaaaaa"
    groups, changed = input_module._entered_groups(observed, expected)
    actual = input_module._render_groups(groups, changed, len(expected))
    plain = re.sub(r"\x1b\[[0-9;]*m", "", actual)

    assert plain == shown
    assert len(re.findall(r"\x1b\[(?:1|22);31m", actual)) == red
    assert len(changed) == red
    assert "".join(plain.replace("_", "").split()).lower() == observed.lower()


def test_interrupted_creation_marks_partial_cards_void() -> None:
    stdout, stderr = _TTYOutput(), io.StringIO()
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli._confirm_card", side_effect=KeyboardInterrupt),
        patch("codex32.cli.BitcoinCore.connect", return_value=_FakeBitcoinCore()),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = ms_main(["create", "2", "--indices", "ac"])

    assert status == 130
    assert "Mark every card from this incomplete creation void" in stderr.getvalue()


def test_interruption_after_confirmation_keeps_cards_valid() -> None:
    core = _FakeBitcoinCore()
    stdout, stderr = _TTYOutput(), io.StringIO()

    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli._confirm_card"),
        patch.object(core, "initialize", side_effect=KeyboardInterrupt),
        patch("codex32.cli.BitcoinCore.connect", return_value=core),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = ms_main(["create"])

    assert status == 130
    assert "recovery cards are valid" in stderr.getvalue()
    assert "Mark every card" not in stderr.getvalue()


def test_existing_create_prompts_for_source_then_each_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return VECTOR_4["secret_s"]
        if prompt.startswith("Write this share"):
            emitted.append(_card_text(capsys.readouterr().out))
            return ""
        return emitted[-1]

    emitted: list[str] = []

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)
    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *_args: _FakeBitcoinCore())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert ms_main(["create", "2", "--indices", "ac", "--existing"]) == 0
    assert prompts == [
        "Enter an existing Bitcoin codex32 secret or hexadecimal seed:\n> ",
        "Write this share on a new recovery card, then press Enter. ",
        "Re-enter the share from the recovery card:\n> ",
        "Write this share on a new recovery card, then press Enter. ",
        "Re-enter the share from the recovery card:\n> ",
    ]
    assert capsys.readouterr().err.startswith("\n")


def test_create_accepts_positional_headers_and_preserves_index_order() -> None:
    fingerprinted = _invoke_confirmed_create(["create", "0"])
    unshared = _invoke_confirmed_create(["create", "0test"])
    automatic_shares = _invoke_confirmed_create(["create", "2"])
    custom_count = _invoke_confirmed_create(["create", "3cash", "--shares", "5"])
    shared = _invoke_confirmed_create(["create", "ms13cash", "--indices", "7cad"])

    fingerprinted_secret = _output_artifacts(fingerprinted)[0]
    unshared_secret = _output_artifacts(unshared)[0]
    automatic = _output_artifacts(automatic_shares)
    custom = _output_artifacts(custom_count)
    shares = _output_artifacts(shared)
    assert isinstance(fingerprinted_secret, MasterSeed)
    assert fingerprinted_secret.header.identifier == _fingerprint_identifier(
        stub_fingerprint(fingerprinted_secret.seed_bytes)
    )
    assert unshared_secret.header.identifier == "test"
    assert len(automatic) == 3
    assert all(share.header.threshold == 2 for share in automatic)
    assert len(automatic[0].header.identifier) == 4
    assert len(custom) == 5
    assert all(share.header.threshold == 3 and share.header.identifier == "cash" for share in custom)
    assert "".join(share.header.index for share in shares) == "7cad"
    assert all(isinstance(share, Share) for share in shares)
    basis = [share for share in shares[:3] if isinstance(share, Share)]
    assert recover_secret(basis).header.identifier == "cash"


@pytest.mark.parametrize(("threshold", "count"), ((2, 3), (3, 5)))
def test_create_has_reviewed_share_count_presets(threshold: int, count: int) -> None:
    result = _invoke_confirmed_create(["create", f"{threshold}test"])
    shares = _output_artifacts(result)

    assert result.exit_code == 0
    assert len(shares) == count
    assert all(isinstance(share, Share) for share in shares)
    assert len({share.header.index for share in shares}) == count
    assert "Master-seed backup confirmed." in result.stderr


def test_shared_backup_confirmation_has_no_extra_leading_blank_line() -> None:
    secret = parse_codex32(VECTOR_2["secret_S"])
    assert isinstance(secret, MasterSeed)
    output = io.StringIO()

    with contextlib.redirect_stderr(output):
        assert importlib.import_module("codex32.cli")._initialize_wallet(_FakeBitcoinCore(), secret) == 0

    assert output.getvalue().startswith("Master-seed backup confirmed.\n\nBitcoin Core")


@pytest.mark.parametrize("threshold", range(4, 10))
def test_higher_threshold_requires_an_explicit_share_selection(threshold: int) -> None:
    result = _invoke_confirmed_create(["create", f"{threshold}test"])

    assert result.exit_code == 2
    assert "thresholds 4 through 9" in result.stderr
    assert result.stdout == ""


def test_create_existing_preserves_secrets_and_uses_explicit_thresholds_for_resharing() -> None:
    raw = bytes(range(16))
    rejected_raw = _invoke(["create"], raw.hex())
    random_raw = _invoke_confirmed_create(["create", "--existing"], raw.hex())
    accepted_raw = _invoke_confirmed_create(["create", "0test", "--existing"], raw.hex())
    source = parse_codex32(VECTOR_4["secret_s"])
    rejected_split = _invoke(["create"], source.text)
    unchanged_backup = _invoke_confirmed_create(["create", "--existing"], source.text)
    random_split = _invoke_confirmed_create(["create", "2", "--indices", "ac", "--existing"], source.text)
    accepted_split = _invoke_confirmed_create(
        ["create", "2name", "--indices", "ac", "--existing"], source.text
    )

    assert rejected_raw.exit_code != 0
    assert rejected_split.exit_code != 0
    assert "interactive terminal" in rejected_raw.stderr
    assert "interactive terminal" in rejected_split.stderr
    random_secret = _output_artifacts(random_raw)[0]
    assert isinstance(random_secret, MasterSeed) and random_secret.seed_bytes == raw
    assert unchanged_backup.exit_code == 0
    assert _output_artifacts(unchanged_backup)[0].text == source.text
    secret = _output_artifacts(accepted_raw)[0]
    assert isinstance(secret, MasterSeed) and secret.seed_bytes == raw
    assert isinstance(source, MasterSeed)
    for result in (random_split, accepted_split):
        basis = [share for share in _output_artifacts(result) if isinstance(share, Share)]
        recovered = recover_secret(basis)
        assert isinstance(recovered, MasterSeed)
        assert recovered.seed_bytes == source.seed_bytes


@pytest.mark.parametrize(
    "arguments",
    (
        ["create", "cl10cln2"],
        ["create", "cl12cln2"],
        ["create", "cl10", "--existing"],
    ),
)
def test_create_rejects_core_lightning(arguments: list[str]) -> None:
    result = _invoke(arguments, VECTOR_6["codex32_cln2"])

    assert result.exit_code == 2
    assert "must begin with ms1" in result.stderr


def test_default_create_existing_rejects_core_lightning_secret() -> None:
    result = _invoke_confirmed_create(["create", "--existing"], VECTOR_6["codex32_cln2"])

    assert result.exit_code == 2
    assert "Enter one Bitcoin master seed" in result.stderr


def test_create_rejects_bip39_partial_basis_and_selector_conflicts() -> None:
    bip39 = _invoke(["create", "bip39_12w10test"])
    partial = _invoke(
        ["create", "2test", "--indices", "ac", "--existing"],
        VECTOR_2["share_A"],
    )
    conflict = _invoke(["create", "2test", "--shares", "2", "--indices", "ac"])
    partial_headers = [_invoke(["create", value]) for value in ("cat", "dad", "3cat")]

    for result in (bip39, partial, conflict, *partial_headers):
        assert result.exit_code != 0


def test_terminal_secret_has_fingerprint_but_share_does_not() -> None:
    secret = _invoke_terminal(["secret"], VECTOR_1["secret_s"])
    share = _invoke_terminal(["share", "d"], VECTOR_2["share_A"], VECTOR_2["share_C"])

    assert secret.exit_code == share.exit_code == 0
    assert "Master fingerprint:" in secret.stdout
    assert "Master fingerprint:" not in share.stdout
    assert "Backup identifier:" in secret.stdout and "Backup identifier:" in share.stdout


def test_fixed_correction_is_a_nonzero_stderr_suggestion() -> None:
    original = VECTOR_1["secret_s"]
    position = 15
    replacement = "q" if original[position] != "q" else "p"
    damaged = original[:position] + replacement + original[position + 1 :]
    result = _invoke(["correct"], damaged)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert original in result.stderr
    assert "suggestion" in result.stderr


def test_structural_correction_uses_default_lengths_and_preserved_groups() -> None:
    original = VECTOR_1["secret_s"]
    omitted = _invoke(["correct"], original[:19] + original[20:])
    groups = [original[start : start + 4] for start in range(0, len(original), 4)]
    grouped = _invoke(
        ["correct"],
        "  ".join(group for index, group in enumerate(groups) if index != 6),
    )

    assert omitted.exit_code == grouped.exit_code == 1
    assert omitted.stdout == grouped.stdout == ""
    assert original in omitted.stderr and original in grouped.stderr


def test_cli_preserves_consecutive_fixed_erasure_guarantee() -> None:
    original = VECTOR_2["share_A"]
    damaged = original[:25] + "?" * 10 + original[35:]

    result = _invoke(["correct"], damaged)

    assert result.exit_code == 1
    assert original in result.stderr


def test_cli_rejects_statistically_inadmissible_structural_burst() -> None:
    damaged = "MS12NAMEA2320ZYX?????????????JHGFED3CAXRPP870HKKQRMF"

    result = _invoke(["correct"], damaged)

    assert result.exit_code == 1
    assert "No valid correction found" in result.stderr


def test_cli_rejects_sixteen_consecutive_erasures_as_outside_regular_bound() -> None:
    damaged = "MS10 NKSU SRVE Y98M ???? ???? ???? ???? UKX9 7HUD URKE V0ZV"

    result = _invoke(["correct"], damaged)

    assert len("".join(damaged.split())) == 48
    assert damaged.count("?") == 16
    assert result.exit_code == 1
    assert "No valid correction found" in result.stderr


@pytest.mark.parametrize(
    ("byte_length", "options"),
    ((16, []), (64, []), (20, ["--bytes", "20"]), (24, ["--bytes", "?"])),
)
def test_correction_accepts_inferred_explicit_and_unknown_lengths(
    byte_length: int, options: list[str]
) -> None:
    original = MasterSeed.from_seed(bytes(range(byte_length)), identifier="test").text
    damaged = original[:19] + original[20:]
    valid = _invoke(["correct"], original)
    result = _invoke(["correct", *options], damaged)

    assert valid.exit_code == 0 and "already valid" in valid.stdout
    assert result.exit_code == 1 and original in result.stderr
    assert result.stdout == ""


def test_valid_correction_input_must_match_explicit_byte_length() -> None:
    result = _invoke(["correct", "--bytes", "24"], VECTOR_1["secret_s"])

    assert result.exit_code == 2
    assert "does not match" in result.stderr


def test_correction_bytes_rejects_an_unsupported_ms_size() -> None:
    result = _invoke(["correct", "--bytes", "17"], VECTOR_1["secret_s"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "bytes must be 16, 20, 24, 28, 32, 64, or ?" in result.stderr


def test_cli_never_accepts_an_incomplete_structural_search() -> None:
    original = VECTOR_1["secret_s"]
    damaged = original[:19] + original[20:]
    with patch("codex32.cli._correction_candidates", return_value=((), False, 0.0, False)):
        result = _invoke(["correct"], damaged)

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "did not complete" in result.stderr and original not in result.stderr


@pytest.mark.parametrize(
    ("options", "lengths", "bounded"),
    (
        ([], (48, 54, 61, 67, 74, 127), True),
        (["--bytes", "20"], (54,), True),
        (["--bytes", "64"], (127,), True),
        (["--bytes", "?"], (48, 54, 61, 67, 74, 127), True),
    ),
)
def test_correction_options_control_lengths_deadline_and_search_envelope(
    options: list[str], lengths: tuple[int, ...], bounded: bool
) -> None:
    original = VECTOR_1["secret_s"]
    damaged = original[:-1] + ("q" if original[-1] != "q" else "p")
    with patch("codex32.indel._search_many", return_value=((), True)) as search:
        result = _invoke(["correct", *options], damaged)

    assert result.exit_code == 1 and result.stdout == ""
    assert search.call_count == 1
    contexts, observed = search.call_args.args
    assert observed == damaged
    assert tuple(context.expected_length for context in contexts) == lengths
    assert (search.call_args.kwargs["deadline"] is not None) is bounded
    assert search.call_args.kwargs["reduced"] == frozenset()


def test_automatic_target_selection_covers_midpoints_and_supported_lengths() -> None:
    from codex32._cli_input import _correction_plan

    for observed in range(40, 136):
        targets = _correction_plan(Profile.MS, None, observed, None)[0]
        expected = 48 if observed <= 61 else 74 if observed <= 100 else 127

        assert targets[0] == expected
        assert sorted(targets) == [48, 54, 61, 67, 74, 127]


def test_fixed_correction_repairs_legacy_cl_header_and_residue_reverse_positions() -> None:
    original = VECTOR_6["codex32_peev"]
    damaged = original[:3] + "2" + original[4:]
    fixed = _invoke(["correct"], damaged)
    residue = _invoke(["correct", "--residue"], "2ppjkw73qdjvc")

    assert fixed.exit_code == 1 and original in fixed.stderr
    assert residue.exit_code == 0
    assert "Add x at position 38, counting backward from the end." in residue.stdout


def test_correct_accepts_valid_shared_core_lightning_artifacts() -> None:
    for value in (SHARING_VECTORS["cl"]["A"], SHARING_VECTORS["cl"]["S"]):
        result = _invoke(["correct"], value)

        assert result.exit_code == 0
        assert "already valid" in result.stdout


def test_correct_accepts_a_valid_legacy_core_lightning_secret() -> None:
    result = _invoke(["correct"], VECTOR_6["codex32_cln2"])

    assert result.exit_code == 0
    assert result.stdout == "The codex32 string is already valid.\n"


def test_correction_infers_prefix_and_marks_invalid_data_as_erasures() -> None:
    original = VECTOR_1["secret_s"]
    position = 15
    for marker in ("?", "%"):
        damaged = original[:position] + marker + original[position + 1 :]
        result = _invoke(["correct"], damaged)
        assert result.exit_code == 1
        assert original in result.stderr

    removed = _invoke(["correct", "--prefix", "ms"], original)
    damaged_prefix = _invoke(["correct"], "?" + original[1:])
    bip39 = _invoke(["correct"], BIP39_12W_ZERO)
    assert removed.exit_code == 2
    assert "Remove or correct these arguments: --prefix" in removed.stderr
    assert damaged_prefix.exit_code == 1
    assert bip39.exit_code == 0 and "already valid" in bip39.stdout


def test_correction_hides_internal_candidate_reparse_failures() -> None:
    result = _invoke(["correct"], "ms12auxxxxxxxxxxxxxxxxxxxxxxxxxxxxxda3kr3s0s2swg")

    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr.strip() in {
        "codex32 correct: No valid correction found. Check the original backup.",
        "codex32 correct: The correction search did not complete within ten seconds.",
    }
    assert "threshold" not in result.stderr


def test_wallet_commands_initialize_selected_master_seed_destinations() -> None:
    xprv = _invoke(["xprv"], VECTOR_1["secret_s"])
    private, private_core = _invoke_initialized_wallet(["wallet"], VECTOR_1["secret_s"])

    assert xprv.exit_code == private.exit_code == 0
    assert xprv.stdout.strip() == VECTOR_1["xprv"]
    assert xprv.stderr.endswith("Keep it secret.\n\n")
    assert private.stdout == ""
    assert private_core.imported == parse_codex32(VECTOR_1["secret_s"])
    assert private_core.private is True
    assert "Warning: This imports private descriptors that can spend funds." in private.stderr
    assert "Use only the intended encrypted wallet" not in private.stderr
    assert "\x1b[" not in private.stderr + private.stdout
    assert "spending wallet initialized" in private.stderr


def test_bitcoin_core_cli_accepts_now_timestamp() -> None:
    result, core = _invoke_initialized_wallet(
        ["wallet", "--timestamp", "now"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 0
    assert core.timestamp == "now"


def test_bitcoin_core_cli_derives_test_network_from_connected_core() -> None:
    result, core = _invoke_initialized_wallet(
        ["wallet"],
        VECTOR_1["secret_s"],
        core=_FakeBitcoinCore(chain="regtest"),
    )

    assert result.exit_code == 0 and core.imported is not None


def test_wallet_network_selection_does_not_change_recovery_material() -> None:
    expected = parse_codex32(VECTOR_1["secret_s"])
    main_result, main_core = _invoke_initialized_wallet(
        ["wallet"],
        VECTOR_1["secret_s"],
        core=_FakeBitcoinCore(chain="main"),
    )
    test_result, test_core = _invoke_initialized_wallet(
        ["wallet"],
        VECTOR_1["secret_s"],
        core=_FakeBitcoinCore(chain="regtest"),
    )

    assert main_result.exit_code == test_result.exit_code == 0
    assert main_core.imported == test_core.imported == expected


def test_wallet_network_selection_preserves_share_compatibility() -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])
    assert isinstance(a, Share) and isinstance(c, Share)
    recovered = recover_secret((a, c))
    assert isinstance(recovered, MasterSeed)

    for chain in ("main", "regtest"):
        result, core = _invoke_initialized_wallet(
            ["wallet"],
            recovered.text,
            core=_FakeBitcoinCore(chain=chain),
        )
        assert result.exit_code == 0
        assert core.imported == recovered
        assert recover_secret((a, c)) == recovered
        assert derive_share((a, c), "d").text == VECTOR_2["derived_D"]


def test_wallet_private_warning_precedes_recovery_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_module = importlib.import_module("codex32.cli")

    def stop_before_input(_fingerprint=None) -> MasterSeed:
        assert "Warning: This imports private descriptors that can spend funds." in capsys.readouterr().err
        raise cli_module._UsageError("stopped")

    monkeypatch.setattr(cli_module, "_master_seed", stop_before_input)
    monkeypatch.setattr(cli_module.BitcoinCore, "connect", lambda *_args: _FakeBitcoinCore())
    monkeypatch.setattr(cli_module.sys, "stdin", _TTYInput())

    assert ms_main(["wallet"]) == 2


def test_wallet_cli_rejects_non_ms_profiles() -> None:
    for command in (
        ("xprv",),
        ("wallet",),
    ):
        result = (
            _invoke_initialized_wallet(list(command), SHARING_VECTORS["cl"]["S"])[0]
            if command[0] == "wallet"
            else _invoke(list(command), SHARING_VECTORS["cl"]["S"])
        )
        assert result.exit_code != 0
        assert "only Bitcoin master seed input" in result.stderr


def test_long_options_must_not_be_abbreviated() -> None:
    result = _invoke(
        ["wallet", "--acc", "0"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 2
    assert "Remove or correct these arguments: --acc 0" in result.stderr


def test_old_wallet_hierarchy_and_old_commands_are_absent() -> None:
    for command in (
        ["wallet", "bitcoin-core"],
        ["wallet", "restore"],
        ["wallet", "watch-only"],
        ["wallet", "multisig-xpub"],
        ["verify"],
        ["xpub"],
        ["descriptors"],
    ):
        result = _invoke(command)
        assert result.exit_code == 2


def test_version_and_installed_entry_point() -> None:
    direct = _invoke(["--version"])
    installed = subprocess.run(
        [str(_installed_cli()), "--version"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert direct.exit_code == installed.returncode == 0
    assert direct.stdout == installed.stdout
    assert direct.stderr == installed.stderr == ""
    assert direct.stdout.startswith("codex32 ")


def test_production_size_budgets_are_enforced() -> None:
    module = importlib.import_module("codex32")
    assert module.__file__ is not None
    package = Path(module.__file__).parent
    counts = {
        path.relative_to(package): sum(
            bool(line.strip()) and not line.lstrip().startswith("#") for line in path.read_text().splitlines()
        )
        for path in package.rglob("*.py")
    }

    assert sum(counts.values()) < 5000, counts


@pytest.mark.parametrize(
    ("observed", "expected", "groups", "changed"),
    (
        ("Xabcdefgh", "abcdefgh", ["Xabcd", "efgh"], {0}),
        ("abcdİfgh", "abcdefgh", ["abcd", "İfgh"], {1}),
        ("abcXQefgh", "abcdefgh", ["abcXQ", "efgh"], {0}),
        ("abcdQefgX", "abcdefgh", ["abcd", "QefgX"], {1}),
        ("abcdQefgh", "abcdefgh", ["abcd", "Qefgh"], {1}),
        ("SF6EJ24CJ24X", "SF6EJ24C", ["SF6E", "J24CJ24X"], {1}),
        ("abcdeX", "abcdef", ["abcd", "eX"], {1}),
        ("abcd", "abcdef", ["abcd", ""], {1}),
        ("aaaaaaa", "aaaaaaaa", ["aaaa", "aaa"], {1}),
        ("aaaaaaaaa", "aaaaaaaa", ["aaaa", "aaaaa"], {1}),
        ("  aB cD   eF\tgX  ", "abcdefgh", ["  aB cD   ", "eF\tgX  "], {1}),
        ("", "abcdef", ["", ""], {0, 1}),
    ),
)
def test_confirmation_alignment_assigns_complete_canonical_groups(
    observed: str, expected: str, groups: list[str], changed: set[int]
) -> None:
    from codex32._cli_input import _entered_groups

    assert _entered_groups(observed, expected) == (groups, changed)
    assert "".join(groups) == observed


@pytest.mark.parametrize("readline", (True, False))
def test_confirmation_region_splits_and_confines_retries(
    monkeypatch: pytest.MonkeyPatch, readline: bool
) -> None:
    cli_module = importlib.import_module("codex32.cli")
    input_module = importlib.import_module("codex32._cli_input")
    artifact = parse_codex32(VECTOR_2["share_A"])
    # Three adjacent substitutions; correcting the middle splits the run.
    damaged = artifact.text[:4] + " qAME b320 qYXW " + artifact.text[16:]
    answers = iter(("", damaged, "qAME   a320  qYXW", "", "qAME", "NAMEa320", "nAmE", "zYxW"))
    editor = _FakeLineEditor()
    snapshots: list[str] = []
    prefills: list[str] = []
    output = _TTYOutput()
    real_text = cli_module._text

    def read(prompt: str, **options: object) -> str:
        if prompt == "Review the marked text on your recovery card":
            prefills.append(str(options["prefill"]))
            snapshots.append(output.getvalue().splitlines()[-1])
        return str(real_text(prompt, **options))

    def answer(prompt: str) -> str:
        if readline:
            editor.run_hook()
        return next(answers)

    monkeypatch.setattr(cli_module, "_text", read)
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor if readline else None)
    monkeypatch.setattr(builtins, "input", answer)
    confirmed: list[str] = []

    def confirm(text: str) -> ConfirmationResult:
        confirmed.append(text)
        return ConfirmationResult("".join(text.split()).lower() == artifact.text.lower())

    with contextlib.redirect_stderr(output):
        cli_module._confirm_card(artifact, confirm)

    assert prefills == ["qAME b320 qYXW", "qAME", "qAME", "qAME", "NAMEa320", "qYXW"]
    assert len(re.findall(r"\x1b\[(?:1|22);7;31m", snapshots[0])) == 3
    for shown in snapshots[1:]:
        assert "\x1b[1mA320\x1b[0m" in shown
        assert "\x1b[1;7;31mA320" not in shown
        assert artifact.text[16:20] in shown
        assert len(re.findall(r"\x1b\[(?:1|22);7;31m", shown)) == 1
    assert snapshots[1] == snapshots[2] == snapshots[3]
    assert len(confirmed) == 1
    assert "".join(confirmed[0].split()).lower() == artifact.text.lower()
    if readline:
        assert editor.inserted == prefills


def test_confirmation_suffix_extra_freezes_without_shifting_neighbor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_module = importlib.import_module("codex32.cli")

    # A display-only stand-in isolates the reported card suffix regression.
    class Card:
        text = "ABCDSF6EJ24C"

    answers = iter(("", "ABCDSF6EJ24CJ24X", "J24C"))
    prefills: list[str] = []
    output = _TTYOutput()

    def answer(prompt: str, **options: object) -> str:
        if "prefill" in options:
            prefills.append(str(options["prefill"]))
        return next(answers)

    monkeypatch.setattr(cli_module, "_text", answer)
    with contextlib.redirect_stderr(output):
        cli_module._confirm_card(Card())
    assert prefills == ["J24CJ24X"]
    assert "\x1b[1mABCD\x1b[0m \x1b[22mSF6E\x1b[0m \x1b[1;7;31mJ24CJ24X\x1b[0m" in output.getvalue()


@pytest.mark.parametrize("full_retry", (False, True))
def test_creation_region_retry_keeps_original_ceremony_wallet_source(
    monkeypatch: pytest.MonkeyPatch,
    full_retry: bool,
) -> None:
    cli_module = importlib.import_module("codex32.cli")
    core = _FakeBitcoinCore()
    stdout, stderr = _TTYOutput(), _TTYOutput()
    finished: list[MasterSeed | CoreLightningSecret] = []
    finish = cli_module.CreationCeremony.finish

    def remember(ceremony: object) -> MasterSeed | CoreLightningSecret:
        result = finish(ceremony)
        finished.append(result)
        return cast(MasterSeed | CoreLightningSecret, result)

    def answer(prompt: str, **options: object) -> str:
        if prompt.startswith("Write this share"):
            return ""
        text = _card_text(stdout.getvalue())
        if "Re-enter the share" in prompt:
            return text + "J24X"
        assert prompt == "Review the marked text on your recovery card"
        assert options["prefill"] == text[-4:] + "J24X"
        return text.lower() if full_retry else text[-4:].lower()

    monkeypatch.setattr(cli_module, "_text", answer)
    monkeypatch.setattr(cli_module.CreationCeremony, "finish", remember)
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli.BitcoinCore.connect", return_value=core),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert ms_main(["create", "2", "--indices", "ac"]) == 0
    assert len(finished) == 1
    assert core.imported is finished[0]


@pytest.mark.parametrize(
    ("entered", "length", "display"),
    ((" aB ", 4, "AB"), (" a ", 2, "A"), ("", 2, "__"), ("abcde", 4, "ABCDE")),
)
def test_confirmation_placeholders_only_replace_wholly_omitted_groups(
    entered: str, length: int, display: str
) -> None:
    from codex32._cli_input import _render_groups

    groups = [entered]
    assert _render_groups(groups, {0}, length, range(1)) == f"\x1b[1;7;31m{display}\x1b[0m"
    assert groups == [entered]


@pytest.mark.parametrize(
    ("observed", "expected", "groups", "changed"),
    (
        ("ABC XEFGH", "ABCDEFGH", ["ABC ", "XEFGH"], {0, 1}),
        ("3F88  X64TR", "3F8864TR", ["3F88  ", "X64TR"], {1}),
        ("ABCDEFGH IJXL", "ABCDEFGHIJKL", ["ABCD", "EFGH ", "IJXL"], {2}),
        ("ABCD IJKL", "ABCDEFGHIJKL", ["ABCD ", "", "IJKL"], {1}),
        ("ABCD X EFGH", "ABCDEFGH", ["ABCD ", "X EFGH"], {1}),
        ("X ABCD EFGH", "ABCDEFGH", ["X ABCD ", "EFGH"], {0}),
        ("ABCD EFGH X", "ABCDEFGH", ["ABCD ", "EFGH X"], {1}),
        ("ABCDEF GHIX", "ABCDEFGH", ["ABCDEF ", "GHIX"], {0, 1}),
        ("abcdef X", "abcdef", ["abcd", "ef X"], {1}),
        ("ab cd ef gh", "abcdefgh", ["ab cd ", "ef gh"], set()),
        ("aaaa aaaaX", "aaaaaaaa", ["aaaa ", "aaaaX"], {1}),
    ),
)
def test_confirmation_grouped_alignment_preserves_token_ownership(
    observed: str, expected: str, groups: list[str], changed: set[int]
) -> None:
    from codex32._cli_input import _entered_groups

    assert _entered_groups(observed, expected) == (groups, changed)
    assert "".join(groups) == observed


@pytest.mark.parametrize("readline", (False, True))
@pytest.mark.parametrize("full_retry", (False, True))
def test_confirmation_full_string_retry_preserves_progress(
    monkeypatch: pytest.MonkeyPatch, readline: bool, full_retry: bool
) -> None:
    cli_module = importlib.import_module("codex32.cli")
    input_module = importlib.import_module("codex32._cli_input")

    class Card:
        text = "MS10ABCDEFGH"

    final = " ms10 ABCD eFgH " if full_retry else "abcd"
    answers = iter(("", "ms10 ABC XEFGH", "ms10 abcd efgX", "", "ABC XEFGH", "abC eFgH", final))
    editor = _FakeLineEditor()
    output = _TTYOutput()
    prefills: list[str] = []
    snapshots: list[str] = []
    confirmed: list[str] = []
    original_text = cli_module._text

    def read(prompt: str, **options: object) -> str:
        if "prefill" in options:
            prefills.append(str(options["prefill"]))
            snapshots.append(output.getvalue().splitlines()[-1])
        return str(original_text(prompt, **options))

    def answer(prompt: str) -> str:
        if readline:
            editor.run_hook()
        return next(answers)

    def confirm(value: str) -> ConfirmationResult:
        confirmed.append(value)
        return ConfirmationResult("".join(value.split()).upper() == Card.text)

    monkeypatch.setattr(cli_module, "_text", read)
    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", editor if readline else None)
    monkeypatch.setattr(builtins, "input", answer)
    with contextlib.redirect_stderr(output):
        cli_module._confirm_card(Card(), confirm)

    assert prefills == ["ABC XEFGH"] * 4 + ["abC"]
    assert snapshots[:4] == [snapshots[0]] * 4
    assert "\x1b[1mEFGH\x1b[0m" in snapshots[4]
    assert "\x1b[1;7;31mABC\x1b[0m" in snapshots[4]
    assert "Please re-enter only the highlighted region that remains incorrect." in output.getvalue()
    assert len(confirmed) == 1
    if full_retry:
        assert confirmed == [final]
    if readline:
        assert editor.inserted == prefills


@pytest.mark.parametrize(
    ("observed", "prefill"),
    (("ms10ABQDEFGX", "ABQD EFGX"), ("ms10 ABQD  eFgX", "ABQD  eFgX")),
)
def test_confirmation_prefill_uses_typed_spacing_or_display_boundaries(
    monkeypatch: pytest.MonkeyPatch, observed: str, prefill: str
) -> None:
    cli_module = importlib.import_module("codex32.cli")

    class Card:
        text = "MS10ABCDEFGH"

    answers = iter(("", observed, "ABCDEFGH"))
    prefills: list[str] = []

    def answer(prompt: str, **options: object) -> str:
        if "prefill" in options:
            prefills.append(str(options["prefill"]))
        return next(answers)

    monkeypatch.setattr(cli_module, "_text", answer)
    cli_module._confirm_card(Card())
    assert prefills == [prefill]


@pytest.mark.parametrize("vector", (VECTOR_1["secret_s"], VECTOR_4["secret_s"]))
def test_create_existing_secret_confirms_original_before_initializing(
    monkeypatch: pytest.MonkeyPatch, vector: str
) -> None:
    cli_module = importlib.import_module("codex32.cli")
    secret = parse_codex32(vector)
    assert isinstance(secret, MasterSeed)
    core = _FakeBitcoinCore()
    output = _TTYOutput()
    damaged = secret.text[:-1] + ("q" if secret.text[-1].lower() != "q" else "p")
    width = len(secret.text) % 4 or 4
    answers = iter(("", damaged, secret.text[-width:].upper()))
    prefills: list[str] = []

    def answer(prompt: str, **options: object) -> str:
        assert core.imported is None
        if "prefill" in options:
            prefills.append(str(options["prefill"]))
        return next(answers)

    monkeypatch.setattr(cli_module, "_text", answer)
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli._creation_source", return_value=secret),
        patch("codex32.cli._generated_secret") as generate,
        patch("codex32.cli.CreationCeremony.from_secret") as split,
        patch("codex32.cli.BitcoinCore.connect", return_value=core),
        contextlib.redirect_stdout(output),
        contextlib.redirect_stderr(_TTYOutput()),
    ):
        assert ms_main(["create", "--existing"]) == 0
    assert prefills == [damaged[-width:]]
    assert _card_text(output.getvalue()).lower() == secret.text.lower()
    assert core.imported is secret
    assert core.timestamp == 0
    generate.assert_not_called()
    split.assert_not_called()


def test_create_existing_secret_does_not_silently_change_identifier() -> None:
    result = _invoke_confirmed_create(["create", "0test", "--existing"], VECTOR_4["secret_s"])
    assert result.exit_code == 2 and result.stdout == ""
    assert "To change the existing secret's identifier" in result.stderr


@pytest.mark.parametrize("source", (VECTOR_1["secret_s"], VECTOR_1["secret_s"].upper()))
def test_create_existing_accepts_complete_ms_secrets_in_either_case(source: str) -> None:
    result = _invoke_confirmed_create(["create", "--existing"], source)

    assert result.exit_code == 0
    assert _output_artifacts(result)[0].text == source


def test_create_existing_interruption_cannot_initialize_a_wallet() -> None:
    core = _FakeBitcoinCore()
    secret = parse_codex32(VECTOR_1["secret_s"])
    with (
        patch.object(sys, "stdin", _TTYInput()),
        patch("codex32.cli._creation_source", return_value=secret),
        patch("codex32.cli._confirm_card", side_effect=KeyboardInterrupt),
        patch("codex32.cli.BitcoinCore.connect", return_value=core),
        contextlib.redirect_stdout(_TTYOutput()),
        contextlib.redirect_stderr(_TTYOutput()),
    ):
        assert ms_main(["create", "--existing"]) == 130
    assert core.imported is None


@pytest.mark.parametrize(
    "response,accepted", [("", False), ("n", False), ("other", False), ("y", True), ("YES", True)]
)
def test_operational_candidate_whole_card_confirmation(monkeypatch, capsys, response, accepted):
    module = importlib.import_module("codex32._cli_input")
    artifact = parse_codex32(VECTOR_1["secret_s"])
    prompts = []
    monkeypatch.setattr(module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", lambda prompt: prompts.append(prompt) or response)
    monkeypatch.setattr(module.sys.stderr, "isatty", lambda: True)
    candidate = CorrectionCandidate(artifact, (), 1, 0, 0, None, capture_space_bits=65)
    assert module._confirm_correction(candidate, [], False, _FakeBitcoinCore().fingerprint) is accepted
    output = capsys.readouterr().err
    assert "Master fingerprint: 3F3521A6\n\n" in output
    assert module._card_text(artifact.text) in output
    assert "> " not in output
    assert "\x1b[1;31m" not in output and "\x1b[1;31;7m" not in output
    assert "\x1b[1m" in output and "\x1b[22m" in output
    assert prompts == ["Does this entire string exactly match your recovery card? [y/N]: "]


def test_final_share_preview_is_isolated_and_basis_has_no_preview(monkeypatch, capsys):
    module = importlib.import_module("codex32._cli_input")
    first = parse_codex32(VECTOR_2["share_A"])
    candidate = CorrectionCandidate(
        parse_codex32(VECTOR_2["share_C"]), (), 1, 0, 0, None, capture_space_bits=65
    )
    accepted = [first]
    monkeypatch.setattr(module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", lambda prompt: "n")
    assert not module._confirm_correction(candidate, accepted, False, _FakeBitcoinCore().fingerprint)
    assert accepted == [first]
    assert "Master fingerprint: FAB6868A\n\n" in capsys.readouterr().err
    assert not module._confirm_correction(candidate, accepted, True, _FakeBitcoinCore().fingerprint)
    assert "Master fingerprint" not in capsys.readouterr().err
    assert not module._confirm_correction(candidate, [], False, _FakeBitcoinCore().fingerprint)
    assert "Master fingerprint" not in capsys.readouterr().err


def test_failed_fingerprint_never_offers_confirmation(monkeypatch, capsys):
    module = importlib.import_module("codex32._cli_input")
    from codex32.errors import CodexError

    def fail(seed):
        raise CodexError("unusable")

    monkeypatch.setattr(module, "_editable_input", lambda prompt: pytest.fail("confirmation offered"))
    candidate = CorrectionCandidate(
        parse_codex32(VECTOR_1["secret_s"]), (), 1, 0, 0, None, capture_space_bits=65
    )
    assert not module._confirm_correction(candidate, [], False, fail)
    assert "Could not recover a valid Bitcoin master seed using this correction." in capsys.readouterr().err


@pytest.mark.parametrize(
    "observed,window",
    [("ABXD EFGH IJ", "ABCD"), ("ABC EFGH IJ", "ABCD"), ("ABCD XEFGH IJ", "EFGH"), ("ABCD EFGH I", "IJ")],
)
def test_correct_highlights_complete_canonical_windows(observed, window):
    module = importlib.import_module("codex32._cli_input")
    rendered = module._card_text("abcdefghij", observed=observed)
    assert f"\x1b[1;31m{window}\x1b[0m" in rendered
    assert re.sub(r"\x1b\[[0-9;]*m", "", rendered) == "ABCD EFGH IJ"
    assert "31" not in module._card_text("abcdefghij")


def test_check_invalid_input_never_searches(monkeypatch):
    module = importlib.import_module("codex32._cli_input")
    monkeypatch.setattr(module.sys, "stdin", _TTYInput())
    answers = iter((VECTOR_1["secret_s"][:-1] + "q", VECTOR_1["secret_s"]))
    monkeypatch.setattr(module, "_editable_input", lambda *args: next(answers))
    monkeypatch.setattr(module, "_suggestions", lambda *args: pytest.fail("check searched"))
    assert main(["check"]) == 0


def test_interactive_derived_card_confirmation(monkeypatch):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    first, second, expected = VECTOR_2["share_A"], VECTOR_2["share_C"], VECTOR_2["derived_D"]
    stdout, stderr = _TTYOutput(), _TTYOutput()
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    answers = iter((first, second, "", expected.swapcase()))
    monkeypatch.setattr(module, "_editable_input", lambda *args: next(answers))
    original_derive, original_confirm = cli.derive_share, cli._confirm_card
    derived = []

    def derive(*args):
        artifact = original_derive(*args)
        derived.append(artifact)
        return artifact

    def confirm(artifact):
        assert artifact is derived[0]
        original_confirm(artifact)

    monkeypatch.setattr(cli, "derive_share", derive)
    monkeypatch.setattr(cli, "_confirm_card", confirm)
    assert main(["share", "d"]) == 0
    assert len(derived) == 1 and derived[0].text.lower() == expected.lower()
    assert "Recovery card confirmed." in stderr.getvalue()
    card = module._card_text(expected)
    assert stdout.getvalue().count(card) == 1
    assert card not in stderr.getvalue()


@pytest.mark.parametrize(
    "plain,input_tty,output_tty", [(True, True, True), (False, False, True), (False, True, False)]
)
def test_derived_card_confirmation_bypasses(monkeypatch, plain, input_tty, output_tty):
    cli = importlib.import_module("codex32.cli")
    monkeypatch.setattr(sys, "stdin", _TTYInput() if input_tty else io.StringIO())
    monkeypatch.setattr(sys, "stdout", _TTYOutput() if output_tty else io.StringIO())
    monkeypatch.setattr(
        cli,
        "_artifacts",
        lambda **kwargs: [parse_codex32(VECTOR_2["share_A"]), parse_codex32(VECTOR_2["share_C"])],
    )
    monkeypatch.setattr(cli, "_confirm_card", lambda artifact: pytest.fail("unexpected confirmation"))
    assert main(["share", "d", *(["--plain"] if plain else [])]) == 0


@pytest.mark.parametrize("exception,status", [(EOFError, 2), (KeyboardInterrupt, 130)])
def test_derived_card_interruption(monkeypatch, exception, status):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    stdout, stderr = _TTYOutput(), _TTYOutput()
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(
        cli,
        "_artifacts",
        lambda **kwargs: [parse_codex32(VECTOR_2["share_A"]), parse_codex32(VECTOR_2["share_C"])],
    )

    def interrupted(*args):
        raise exception

    monkeypatch.setattr(module, "_editable_input", interrupted)
    assert main(["share", "d"]) == status
    assert stderr.getvalue().endswith("Recovery card not confirmed.\n")
    assert "void" not in stderr.getvalue() and "Recovery card confirmed." not in stderr.getvalue()


def test_derived_card_retries_keep_frozen_progress(monkeypatch):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    expected = VECTOR_2["derived_D"]
    groups = [expected[i : i + 4] for i in range(0, len(expected), 4)]
    damaged = groups.copy()
    damaged[3] = damaged[3][:2]
    damaged[6] += "X"
    stdout, stderr = _TTYOutput(), _TTYOutput()
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(
        cli,
        "_artifacts",
        lambda **kwargs: [parse_codex32(VECTOR_2["share_A"]), parse_codex32(VECTOR_2["share_C"])],
    )
    answers = iter(("", " ".join(damaged), "", " ".join(damaged), groups[3], expected))
    prefills = []

    def answer(prompt, prefill=""):
        if "Review the marked" in prompt:
            prefills.append(prefill)
        return next(answers)

    monkeypatch.setattr(module, "_editable_input", answer)
    assert main(["share", "d"]) == 0
    assert prefills == [damaged[3], damaged[3], damaged[3], damaged[6]]
    assert "Please re-enter only the highlighted region" in stderr.getvalue()
    assert "Recovery card confirmed." in stderr.getvalue()


def test_share_input_correction_precedes_derivation_and_card_confirmation(monkeypatch):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    first, second, expected = VECTOR_2["share_A"], VECTOR_2["share_C"], VECTOR_2["derived_D"]
    damaged = second[:20] + ("Q" if second[20] != "Q" else "P") + second[21:]
    stdout, stderr = _TTYOutput(), _TTYOutput()
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    answers = iter((first, damaged, "n", damaged, "yes", "", expected))
    events = []
    original = cli.derive_share

    def answer(prompt, prefill=""):
        result = next(answers)
        if "entire string" in prompt:
            events.append(result)
            assert "derive" not in events
        if "Write this share" in prompt:
            events.append("write")
        return result

    def derive(artifacts, index):
        events.append("derive")
        assert artifacts[1].text.lower() == second.lower()
        return original(artifacts, index)

    monkeypatch.setattr(module, "_editable_input", answer)
    monkeypatch.setattr(cli, "derive_share", derive)
    assert main(["share", "d"]) == 0
    assert events == ["n", "yes", "derive", "write"]
    assert "Recovery card confirmed." in stderr.getvalue()
    assert "Rejected:" not in stderr.getvalue()


@pytest.mark.parametrize("response", ["yes", "n", ""])
def test_creation_source_correction_requires_approval(monkeypatch, capsys, response):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    expected = VECTOR_1["secret_s"]
    damaged = expected[:20] + "q" + expected[21:]
    fallback = "00" * 16
    answers = iter((damaged, response, fallback))
    prompts = []
    prefills = []

    def answer(prompt, prefill=""):
        prompts.append(prompt)
        prefills.append(prefill)
        return next(answers)

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", answer)
    result = cli._creation_source(Profile.MS, _FakeBitcoinCore().fingerprint)
    assert result == (parse_codex32(expected) if response == "yes" else bytes(16))
    output = capsys.readouterr().err
    assert "Master fingerprint: 3F3521A6\n\n" in output
    assert module._card_text(expected, False) in output
    assert "31m" not in output
    assert "Does this entire string exactly match your recovery card? [y/N]: " in prompts
    assert prefills == (["", ""] if response == "yes" else ["", "", damaged])
    if response != "yes":
        assert "Rejected:" not in output


@pytest.mark.parametrize("kind", ["none", "ambiguous", "share", "wrong_profile", "fingerprint"])
def test_creation_source_unusable_candidates_retry(monkeypatch, capsys, kind):
    from types import SimpleNamespace

    from codex32.errors import CodexError

    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    artifact = parse_codex32(VECTOR_1["secret_s"])
    if kind == "share":
        artifact = parse_codex32(VECTOR_2["share_A"])
    elif kind == "wrong_profile":
        artifact = parse_codex32(SHARING_VECTORS["cl"]["S"])
    candidate = SimpleNamespace(artifact=artifact, search_complete=True, low_checksum_discrimination=False)
    candidates = () if kind == "none" else (candidate, candidate) if kind == "ambiguous" else (candidate,)
    monkeypatch.setattr(cli, "_suggestions", lambda *args, **kwargs: candidates)
    answers = iter(("ms1invalid", "00" * 16))
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", lambda *args: next(answers))

    def fail(seed):
        raise CodexError("invalid seed")

    fingerprint = fail if kind == "fingerprint" else _FakeBitcoinCore().fingerprint
    assert cli._creation_source(Profile.MS, fingerprint) == bytes(16)
    output = capsys.readouterr().err
    assert "Possible correction:" not in output
    assert "Rejected:" in output


def test_creation_source_does_not_label_an_incomplete_share_candidate(monkeypatch, capsys):
    from types import SimpleNamespace

    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    damaged = "ms12namedll4f8jkh4e5vdvuldlfxu2jhdnlsm97xcenrxeg"
    share = parse_codex32(VECTOR_2["derived_D"])
    candidate = SimpleNamespace(artifact=share, search_complete=False)
    answers = iter((damaged, "00" * 16))

    def suggestions(*args, **kwargs):
        assert not kwargs["allowed"](candidate)
        return (candidate,)

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", lambda *args: next(answers))
    monkeypatch.setattr(cli, "_suggestions", suggestions)

    assert cli._creation_source(Profile.MS) == bytes(16)
    output = capsys.readouterr().err
    assert "Search incomplete:" not in output
    assert "Possible correction:" not in output
    assert "Rejected:" in output


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_creation_source_empty_then_interrupt(monkeypatch, exception):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    answers = iter(("",))

    def answer(*args):
        try:
            return next(answers)
        except StopIteration:
            raise exception

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", answer)
    monkeypatch.setattr(cli, "_suggestions", lambda *args, **kwargs: ())
    with pytest.raises(exception):
        cli._creation_source(Profile.MS)


def test_creation_source_hex_and_noninteractive_never_search(monkeypatch):
    cli = importlib.import_module("codex32.cli")
    monkeypatch.setattr(cli, "_suggestions", lambda *args, **kwargs: pytest.fail("unexpected search"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("00" * 16))
    assert cli._creation_source(Profile.MS) == bytes(16)
    monkeypatch.setattr(sys, "stdin", io.StringIO("ms1invalid"))
    with pytest.raises(cli._UsageError):
        cli._creation_source(Profile.MS)


def test_creation_source_is_neutral_and_does_not_infer_ms1(monkeypatch, capsys):
    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    answers = iter((VECTOR_1["secret_s"][3:], "00" * 16))
    prompts: list[str] = []

    def answer(prompt: str, _prefill: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(module, "_editable_input", answer)
    monkeypatch.setattr("codex32.indel._search_many", lambda *args, **kwargs: pytest.fail("searched"))

    assert cli._creation_source(Profile.MS) == bytes(16)
    assert prompts == ["Enter an existing Bitcoin codex32 secret or hexadecimal seed:\n> "] * 2
    output = capsys.readouterr().err
    assert "Rejected:" in output
    assert "Possible correction:" not in output


def test_corrected_creation_source_identity_and_acceptance_boundary(monkeypatch):
    from types import SimpleNamespace

    cli = importlib.import_module("codex32.cli")
    module = importlib.import_module("codex32._cli_input")
    secret = parse_codex32(VECTOR_1["secret_s"])
    core = _FakeBitcoinCore()
    monkeypatch.setattr(sys, "stdin", _TTYInput())
    monkeypatch.setattr(sys, "stdout", _TTYOutput())
    monkeypatch.setattr(sys, "stderr", _TTYOutput())
    monkeypatch.setattr(cli.BitcoinCore, "connect", lambda *args: core)
    monkeypatch.setattr(
        cli,
        "_suggestions",
        lambda *args, **kwargs: (
            SimpleNamespace(artifact=secret, search_complete=True, low_checksum_discrimination=False),
        ),
    )
    answers = iter(("ms1invalid", "n", "ms1invalid", "yes", "", secret.text))
    confirmations = []

    def answer(prompt, prefill=""):
        assert core.imported is None
        result = next(answers)
        if "entire string" in prompt:
            confirmations.append(result)
        if "Write this" in prompt:
            assert confirmations == ["n", "yes"]
        return result

    monkeypatch.setattr(module, "_editable_input", answer)
    assert ms_main(["create", "--existing"]) == 0
    assert core.imported is secret
    assert confirmations == ["n", "yes"]


def test_incomplete_candidate_has_no_search_warning_and_is_never_accepted_automatically():
    from dataclasses import replace

    from codex32.correction import _correct_fixed

    source = VECTOR_1["secret_s"]
    candidate = _correct_fixed(source, suspected_profile=Profile.MS)
    assert candidate is not None
    candidate = replace(candidate, search_complete=False)
    with patch("codex32.cli._correction_candidates", return_value=((candidate,), False, 0.0, False)):
        result = _invoke(["correct"], source[:-1] + "?")
    assert result.exit_code == 1 and result.stdout == ""
    assert "Search incomplete" not in result.stderr
    assert "may not be unique" not in result.stderr
    assert "only a correction suggestion" in result.stderr
