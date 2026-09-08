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
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO

from codex32 import (
    ConfirmationResult,
    CoreLightningSecret,
    CorrectionContext,
    MasterSeed,
    Profile,
    Secret,
    Share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import _chars_to_u5, bech32_encode
from codex32.checksums import _CODEX32, _CODEX32_LONG
from codex32.cli import main
from codex32.generation import _fingerprint_identifier
from codex32.profiles.ms32 import SEED_BYTE_LENGTHS


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
    version: int = 300000
    imported: MasterSeed | None = None
    private: bool | None = None
    account: int | None = None
    timestamp: int | str | None = None

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


def _invoke(args: list[str], *lines: str) -> _Result:
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.object(sys, "stdin", stdin),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(args)
    return _Result(status, stdout.getvalue(), stderr.getvalue())


def _invoke_terminal(args: list[str], *lines: str) -> _Result:
    stdout, stderr = _TTYOutput(), io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO("\n".join(lines) + "\n")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(args)
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
        status = main(args)
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
        status = main(args)
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
        SHARING_VECTORS["cl"]["S"],
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
        "Valid shared Core Lightning HSM secret.\n"
        "Backup identifier: TEST\n"
        "Shares needed for recovery: 2\n\n"
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


def test_check_does_not_derive_wallet_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_module = importlib.import_module("codex32.cli")

    def forbidden(_seed: bytes) -> bytes:
        raise AssertionError("check derived a BIP32 fingerprint")

    monkeypatch.setattr(cli_module, "_fingerprint_from_seed", forbidden)
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
    assert captured.err.endswith("\n\n")


def test_tty_check_reports_checksum_before_truncated_ms_length(
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
    assert captured.err.count("Rejected: The checksum does not match.") == 3
    assert "Bitcoin master-seed backup must have" not in captured.err


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
    assert captured.err.count("Rejected: The checksum does not match.") == 2


def test_tty_wallet_requires_confirmation_before_using_correction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    original = VECTOR_1["secret_s"]
    damaged = original[:20] + ("q" if original[20] != "q" else "p") + original[21:]
    answers = iter((damaged[3:], "yes"))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["xprv"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_1["xprv"]
    assert "Possible correction:" in captured.err and original in captured.err
    assert f"Possible correction:\n> {original}" in captured.err
    assert prompts[0] == "Enter a codex32 string:\n> "
    assert prompts[-1] == "Use this correction? [y/N]: "


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


def test_artifact_output_is_pretty_only_at_a_terminal() -> None:
    formatted = _invoke_terminal(["secret"], VECTOR_1["secret_s"])
    output = formatted.stdout

    assert formatted.exit_code == 0 and formatted.stderr == ""
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


def test_tty_subsequent_correction_uses_confirmed_immutable_context(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prefix = "MS12NAME"
    suffix = VECTOR_2["share_C"][len(prefix) :]
    damaged = suffix[:12] + ("Q" if suffix[12] != "Q" else "P") + suffix[13:]
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

    assert main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert "Possible correction:" in captured.err and VECTOR_2["share_C"] in captured.err
    assert contexts == [(CorrectionContext(Profile.MS, len(VECTOR_2["share_A"]), prefix, ("a",)),)]


def test_tty_recovery_accepts_complete_uppercase_and_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    first = VECTOR_2["share_A"].upper()
    mismatch = SHARING_VECTORS["cl"]["C"].upper()
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


@pytest.mark.parametrize(
    "command",
    (
        ("secret", "--plain"),
        ("xprv",),
        ("wallet", "multisig-xpub"),
        ("wallet", "bitcoin-core", "watch-only"),
        ("wallet", "bitcoin-core", "restore"),
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

    assert main(command) == 0
    captured = capsys.readouterr()
    if command[:2] != ("wallet", "bitcoin-core"):
        assert captured.out
    assert "Rejected:" not in captured.err
    assert "Share 1 of 3 accepted." in captured.err
    assert "Share 2 of 3 accepted." in captured.err
    assert prompts == [
        "Enter a codex32 string:\n> ",
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
    assert editor.inserted == [rejected]
    assert editor.hook is None


def test_share_supports_ms_and_cl_but_not_bip39() -> None:
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

    assert ms.exit_code == cl.exit_code == 0
    assert ms.stdout.strip() == VECTOR_2["derived_D"]
    assert cl.stdout.strip() == SHARING_VECTORS["cl"]["D"]
    assert bip39.exit_code != 0
    assert "Bitcoin master seed or Core Lightning HSM secret" in bip39.stderr


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
    assert secret.header.identifier == _fingerprint_identifier(secret.seed_bytes)


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
        main(["create"])
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
        main(["create", "--existing"])
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
        assert main(["create"]) == 0

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
        assert main(["create"]) == 0
    artifact = parse_codex32(emitted[0])
    assert isinstance(artifact, MasterSeed)
    assert artifact.header.identifier == _fingerprint_identifier(artifact.seed_bytes)


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
        assert main(["create", "2", "--indices", "ac"]) == 0
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
        status = main(["create", "2", "--indices", "ac"])

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
        status = main(["create"])

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

    assert main(["create", "2", "--indices", "ac", "--existing"]) == 0
    assert prompts == [
        "Enter an existing codex32 secret or hexadecimal seed:\n> ",
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
    assert fingerprinted_secret.header.identifier == _fingerprint_identifier(fingerprinted_secret.seed_bytes)
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


def test_create_supports_core_lightning_generation_and_splitting() -> None:
    unshared = _invoke(["create", "cl10cln2"])
    shared = _invoke_confirmed_create(["create", "cl13cln2", "--indices", "7cad"])
    default_shared = _invoke_confirmed_create(["create", "cl12cln2"])
    source = _output_artifacts(unshared, "cl")[0]
    split = _invoke_confirmed_create(["create", "cl12name", "--indices", "ac", "--existing"], source.text)
    raw = _invoke(["create", "cl10raw0", "--existing"], bytes(range(32)).hex())
    random_identifier = _invoke(["create", "cl10"])

    assert isinstance(source, CoreLightningSecret)
    assert source.header.identifier == "cln2"
    assert source.payload_symbols[-1] & 15 == 0
    assert len(_output_artifacts(default_shared, "cl")) == 3
    raw_secret = _output_artifacts(raw, "cl")[0]
    assert isinstance(raw_secret, CoreLightningSecret)
    assert raw_secret.secret_bytes == bytes(range(32))
    assert isinstance(_output_artifacts(random_identifier, "cl")[0], CoreLightningSecret)
    for result, threshold in ((shared, 3), (split, 2)):
        shares = _output_artifacts(result, "cl")
        assert len(shares) >= threshold
        assert isinstance(recover_secret(shares[:threshold]), CoreLightningSecret)


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


def test_checksum_defaults_to_ms_and_accepts_explicit_cl() -> None:
    ms = parse_codex32(VECTOR_1["secret_s"])
    ms_body = ms.text[3:-13]
    default = _invoke(["checksum"], ms_body)
    prefixed = _invoke(["checksum"], ms.text[:-13])
    explicit = _invoke(["checksum", ms.text[:9]], ms.text[9:-13])

    cl = SHARING_VECTORS["cl"]["S"]
    cl_result = _invoke(["checksum", cl[:9]], cl[9:-13])

    assert default.exit_code == prefixed.exit_code == explicit.exit_code == cl_result.exit_code == 0
    assert default.stdout.strip() == prefixed.stdout.strip() == explicit.stdout.strip() == ms.text
    assert cl_result.stdout.strip() == cl
    assert "DANGER: Incorrect input can make the wallet predictable" in default.stderr
    assert "dice-debiasing worksheet exactly" in default.stderr
    assert default.stdout == ms.text + "\n"


def test_checksum_enforces_published_sizes_and_capabilities() -> None:
    invalid = (
        _invoke(["checksum"], "ms10tests" + "x" * 25),
        _invoke(["checksum"], "0tests" + "x" * 25),
        _invoke(["checksum"], "0tests" + "x" * 27),
        _invoke(["checksum"], "Ms10tests" + "x" * 26),
        _invoke(["checksum"], "bip39_12w10tests" + "q" * 27),
        _invoke(["checksum", "not-a-header"], "x" * 26),
    )
    expected = (
        "The input does not match the expected format of the filled-out "
        "non-pink bold squares.\nConsult the Codex32 Book and check the worksheet."
    )

    for result in invalid:
        assert result.exit_code == 2
        assert expected in result.stderr
        assert not any(detail in result.stderr for detail in ("128", "256", "payload", "unknown prefix"))


def test_checksum_warning_precedes_the_book_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        assert "DANGER: Incorrect input" in capsys.readouterr().err
        prompts.append(prompt)
        return VECTOR_1["secret_s"][9:-13]

    monkeypatch.setattr(input_module.sys, "stdin", _TTYInput())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["checksum", VECTOR_1["secret_s"][:9]]) == 0
    assert prompts == ["Remaining non-pink bold squares:\n> "]


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


def test_cli_reports_ambiguous_structural_plus_consecutive_erasure_input() -> None:
    damaged = "MS12NAMEA2320ZYX?????????????JHGFED3CAXRPP870HKKQRMF"

    result = _invoke(["correct"], damaged)

    assert result.exit_code == 1
    assert "More than one correction is possible" in result.stderr


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
        (["--bytes", "20"], (54,), False),
        (["--bytes", "64"], (127,), False),
        (["--bytes", "?"], (48, 54, 61, 67, 74, 127), False),
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
    assert search.call_args.kwargs["reduced"] == (frozenset((54, 61, 67)) if bounded else frozenset())


def test_automatic_target_selection_covers_midpoints_and_supported_lengths() -> None:
    from codex32._cli_input import _correction_plan

    for observed in range(40, 136):
        targets = _correction_plan(Profile.MS, None, observed, None)[0]
        expected = 48 if observed <= 61 else 74 if observed <= 100 else 127

        assert targets[0] == expected
        assert sorted(targets) == [48, 54, 61, 67, 74, 127]


def test_fixed_correction_supports_cl_and_residue_reverse_positions() -> None:
    original = SHARING_VECTORS["cl"]["S"]
    position = 16
    replacement = "q" if original[position] != "q" else "p"
    damaged = original[:position] + replacement + original[position + 1 :]
    fixed = _invoke(["correct"], damaged)
    residue = _invoke(["correct", "--residue"], "2ppjkw73qdjvc")

    assert fixed.exit_code == 1 and original in fixed.stderr
    assert residue.exit_code == 0
    assert "Add x at position 38, counting backward from the end." in residue.stdout


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
    assert "undamaged ms1 or cl1 prefix" in damaged_prefix.stderr
    assert "not available for BIP39 worksheet backups" in bip39.stderr


def test_correction_hides_internal_candidate_reparse_failures() -> None:
    result = _invoke(["correct"], "ms12auxxxxxxxxxxxxxxxxxxxxxxxxxxxxxda3kr3s0s2swg")

    assert result.exit_code != 0
    assert result.stderr.strip() == ("codex32 correct: No valid correction found. Check the original backup.")
    assert "threshold" not in result.stderr


def test_wallet_commands_initialize_selected_master_seed_destinations() -> None:
    xprv = _invoke(["xprv"], VECTOR_1["secret_s"])
    xpub = _invoke(["wallet", "multisig-xpub", "--account", "0"], VECTOR_1["secret_s"])
    public, public_core = _invoke_initialized_wallet(
        ["wallet", "bitcoin-core", "watch-only"], VECTOR_1["secret_s"]
    )
    private, private_core = _invoke_initialized_wallet(
        ["wallet", "bitcoin-core", "restore"], VECTOR_1["secret_s"]
    )

    assert xprv.exit_code == xpub.exit_code == public.exit_code == private.exit_code == 0
    assert xprv.stdout.strip() == VECTOR_1["xprv"]
    assert xpub.stdout.startswith("[3f3521a6/48h/0h/0h/2h]xpub")
    assert public.stdout == private.stdout == ""
    assert public_core.imported == private_core.imported == parse_codex32(VECTOR_1["secret_s"])
    assert public_core.private is False and private_core.private is True
    assert "Warning: This imports private descriptors that can spend funds." in private.stderr
    assert "Use only the intended encrypted wallet" not in private.stderr
    assert "\x1b[" not in private.stderr + private.stdout
    assert "Do not enter codex32 shares on a network-connected computer" in public.stderr
    assert "watch-only wallet initialized" in public.stderr
    assert "spending wallet initialized" in private.stderr


def test_bitcoin_core_cli_accepts_now_timestamp() -> None:
    result, core = _invoke_initialized_wallet(
        ["wallet", "bitcoin-core", "watch-only", "--timestamp", "now"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 0
    assert core.timestamp == "now"


def test_bitcoin_core_cli_derives_test_network_from_connected_core() -> None:
    result, core = _invoke_initialized_wallet(
        ["wallet", "bitcoin-core", "watch-only"],
        VECTOR_1["secret_s"],
        core=_FakeBitcoinCore(chain="regtest"),
    )

    assert result.exit_code == 0 and core.imported is not None


def test_direct_watch_only_warning_precedes_recovery_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_module = importlib.import_module("codex32.cli")

    def stop_before_input() -> MasterSeed:
        assert "Do not enter codex32 shares on a network-connected computer" in capsys.readouterr().err
        raise cli_module._UsageError("stopped")

    monkeypatch.setattr(cli_module, "_master_seed", stop_before_input)
    monkeypatch.setattr(cli_module.BitcoinCore, "connect", lambda *_args: _FakeBitcoinCore())
    monkeypatch.setattr(cli_module.sys, "stdin", _TTYInput())

    assert main(["wallet", "bitcoin-core", "watch-only"]) == 2


def test_wallet_cli_rejects_non_ms_profiles() -> None:
    for command in (
        ("xprv",),
        ("wallet", "multisig-xpub"),
        ("wallet", "bitcoin-core", "watch-only"),
        ("wallet", "bitcoin-core", "restore"),
    ):
        result = (
            _invoke_initialized_wallet(list(command), SHARING_VECTORS["cl"]["S"])[0]
            if command[:2] == ("wallet", "bitcoin-core")
            else _invoke(list(command), SHARING_VECTORS["cl"]["S"])
        )
        assert result.exit_code != 0
        assert "only Bitcoin master seed input" in result.stderr


def test_long_options_must_not_be_abbreviated() -> None:
    result = _invoke(
        ["wallet", "bitcoin-core", "restore", "--acc", "0"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 2
    assert "Remove or correct these arguments: --acc 0" in result.stderr


def test_wallet_modes_are_mandatory_and_old_commands_are_absent() -> None:
    for command in (
        ["wallet"],
        ["wallet", "bitcoin-core"],
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

    assert sum(counts.values()) < 3000


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
        assert main(["create", "2", "--indices", "ac"]) == 0
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
        assert main(["create", "--existing"]) == 0
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


def test_create_existing_core_lightning_secret_is_preserved() -> None:
    source = SHARING_VECTORS["cl"]["S"]
    result = _invoke_confirmed_create(["create", "cl10", "--existing"], source)
    assert result.exit_code == 0
    assert _output_artifacts(result, "cl")[0].text.lower() == source.lower()
    assert "Bitcoin Core spending wallet initialized" not in result.stderr


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
        assert main(["create", "--existing"]) == 130
    assert core.imported is None
