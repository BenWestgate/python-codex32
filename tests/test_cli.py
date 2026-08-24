"""End-to-end tests for the small codex32 CLI."""

import builtins
import contextlib
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO

from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Secret,
    Share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import _chars_to_u5, _encode
from codex32.cli import main
from codex32.generation import _fingerprint_identifier


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


def _output_artifacts(result: _Result, profile: str = "ms") -> list[Share | Secret]:
    return [
        parse_codex32(line) for line in result.stdout.splitlines() if line.lower().startswith(profile + "1")
    ]


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

    monkeypatch.setattr(cli_module, "fingerprint_from_seed", forbidden)
    result = _invoke(["check"], VECTOR_1["secret_s"])

    assert result.exit_code == 0
    assert result.stderr == ""


def test_check_help_explains_validation_scope() -> None:
    result = _invoke(["check", "-h"])
    help_text = " ".join(result.stdout.split())

    assert result.exit_code == 0
    assert "Checks format, checksum, and application rules" in help_text


def test_secret_help_explains_threshold_protection() -> None:
    help_text = " ".join(_invoke(["secret", "-h"]).stdout.split())

    assert "Recover and display the complete secret" in help_text
    assert "removes the protection provided by splitting it into shares" in help_text


@pytest.mark.parametrize(
    ("hrp", "payload_length", "message"),
    (
        (
            "ms",
            25,
            ("This input has 47 characters. A Bitcoin master-seed backup needs at least 48."),
        ),
        (
            "ms",
            104,
            ("This input has 128 characters. A Bitcoin master-seed backup can have at most 127."),
        ),
        (
            "ms",
            27,
            ("This input does not encode a whole number of Bitcoin master-seed bytes."),
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
    result = _invoke(["check"], _encode(hrp, body))

    assert result.exit_code == 2
    assert message in result.stderr


def test_tty_check_prefills_rejected_entry_without_history(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

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

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert editor.inserted == [rejected]
    assert editor.auto_history == [False, False]
    assert editor.hook is None
    assert display_streams == [True, True]
    assert sys.stdout is not sys.stderr
    assert prompts == ["Enter a codex32 string: "] * 2
    assert rejected not in captured.out
    assert "Rejected: Use either all uppercase or all lowercase letters." in captured.err
    assert captured.err.endswith("\n\n")


def test_tty_check_reports_truncated_ms_length_before_checksum(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    truncated = (
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nl",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6n",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6",
    )
    answers = iter((*truncated, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    for length in (45, 46, 47):
        message = (
            f"Rejected: This input has {length} characters. A Bitcoin master-seed backup needs at least 48."
        )
        assert captured.err.count(message) == 1
    assert "checksum" not in captured.err


def test_tty_check_names_an_invalid_character_and_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    invalid = "MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW'"
    answers = iter((invalid, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    invalid = (
        "ms10fauxxxxxxxxxxxxxxxxxxxxxxxxxxxx0z26tfn0ulw3p",
        "ms1fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxda3kr3s0s2swg",
        "0fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "m10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
        "s10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    )
    answers = iter((*invalid, VECTOR_1["secret_s"]))
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", None)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert main(["check"]) == 0
    rejected = [line for line in capsys.readouterr().err.splitlines() if line.startswith("Rejected:")]
    assert rejected == [
        "Rejected: An unshared secret (threshold 0) must use S as its index.",
        "Rejected: The threshold must be 0 or a number from 2 through 9; found 'f'.",
        "Rejected: No separator (1) was found.",
        "Rejected: The application prefix before 1 is missing.",
        "Rejected: The application prefix 'm' is not supported.",
        "Rejected: The application prefix 's' is not supported.",
    ]


def test_tty_retry_replaces_only_the_editable_suffix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    prefix = "ms12name"
    suffix = VECTOR_2["share_C"][len(prefix) :]
    first, second = ("Q", "P") if suffix.isupper() else ("q", "p")
    bad_one = suffix[:-1] + (first if suffix[-1] != first else second)
    replacement = first if suffix[-2] != first else second
    bad_two = suffix[:-2] + replacement + suffix[-1]
    answers = iter((VECTOR_2["share_A"], bad_one, bad_two, suffix))
    editor = _FakeLineEditor()

    def answer(_prompt: str) -> str:
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert editor.inserted == [bad_one, bad_two]
    assert editor.hook is None
    assert editor.auto_history == [False, False, False, False]
    assert captured.err.count("Rejected: The checksum does not match.") == 2


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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    valid = VECTOR_1["secret_s"]
    rejected = valid[:-1] + valid[-1].upper()
    answers = iter((rejected, valid))
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", None)
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(builtins, "input", answer)

    assert main(["check"]) == 0
    assert "Valid unshared Bitcoin master seed." in capsys.readouterr().out
    assert prompts == ["Enter a codex32 string: "] * 2


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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", lambda _prompt: VECTOR_1["secret_s"])

    assert main(["secret"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_1["secret_s"]
    assert captured.err == "\n"


def test_tty_recovery_accepts_suffix_after_fixed_prefix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    prefix = "ms12name"
    answers = iter((VECTOR_2["share_A"], VECTOR_2["share_C"][len(prefix) :]))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", answer)

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert "Share 1 of 2 accepted." in captured.err
    assert "Share 2 of 2 accepted." not in captured.err
    assert prompts == ["Enter a codex32 string: ", "Enter share 2 of 2: MS12NAME"]


def test_tty_recovery_accepts_complete_uppercase_and_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    first = VECTOR_2["share_A"].upper()
    mismatch = SHARING_VECTORS["cl"]["C"].upper()
    answers = iter((first, mismatch, first, VECTOR_2["share_C"].upper()))
    editor = _FakeLineEditor()

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"].upper()
    assert prompts == [
        "Enter a codex32 string: ",
        "Enter share 2 of 2: MS12NAME",
        "Enter share 2 of 2: MS12NAME",
        "Enter share 2 of 2: MS12NAME",
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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    answers = iter((VECTOR_3["derived_f"], VECTOR_3["share_c"], VECTOR_3["secret_s"]))
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(command) == 0
    captured = capsys.readouterr()
    assert captured.out
    assert "Rejected:" not in captured.err
    assert "Share 1 of 3 accepted." in captured.err
    assert "Share 2 of 3 accepted." in captured.err
    assert prompts == [
        "Enter a codex32 string: ",
        "Enter share 2 of 3: ms13cash",
        "Enter share 3 of 3: ms13cash",
    ]


def test_tty_share_collects_secret_and_exact_basis(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

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

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["share", "d"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_3["derived_d"]
    assert prompts == [
        "Enter a codex32 string: ",
        "Enter string 2 of 3: ms13cash",
        "Enter string 3 of 3: ms13cash",
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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

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

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    def forbidden(_prompt: str) -> str:
        raise AssertionError("invalid target prompted for protected input")

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    answers = iter((VECTOR_2["derived_D"], VECTOR_2["share_A"], VECTOR_2["share_C"]))
    editor = _FakeLineEditor()

    def answer(_prompt: str) -> str:
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["share", "d"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_2["derived_D"]
    assert "Rejected: That index was requested for the additional share." in captured.err
    assert editor.inserted == []


def test_create_defaults_to_an_unshared_128_bit_master_seed() -> None:
    result = _invoke(["create"])
    artifacts = _output_artifacts(result)

    assert result.exit_code == 0
    assert len(artifacts) == 1
    assert isinstance(artifacts[0], MasterSeed)
    assert len(artifacts[0].seed_bytes) == 16
    assert artifacts[0].header.threshold == 0


@pytest.mark.parametrize("byte_length", (16, 32))
def test_fresh_cli_generation_supports_established_sizes(byte_length: int) -> None:
    result = _invoke(["create", "--bytes", str(byte_length)])
    artifact = _output_artifacts(result)[0]

    assert result.exit_code == 0
    assert isinstance(artifact, MasterSeed)
    assert len(artifact.seed_bytes) == byte_length


@pytest.mark.parametrize("byte_length", (17, 31, 33, 64))
def test_fresh_cli_generation_rejects_other_bip93_sizes(byte_length: int) -> None:
    result = _invoke(["create", "--bytes", str(byte_length)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "--bytes" in result.stderr
    assert "invalid choice" in result.stderr


@pytest.mark.parametrize("byte_length", (17, 64))
def test_cli_import_preserves_all_master_seed_sizes(byte_length: int) -> None:
    raw = bytes(range(byte_length))
    result = _invoke(["create", "--existing"], raw.hex())
    artifact = _output_artifacts(result)[0]

    assert result.exit_code == 0
    assert isinstance(artifact, MasterSeed)
    assert artifact.seed_bytes == raw


def test_bare_create_does_not_prompt_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    def forbidden(_prompt: str) -> str:
        raise AssertionError("bare create prompted without a decision to make")

    monkeypatch.setattr(sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", forbidden)

    assert main(["create", "--plain"]) == 0
    artifact = parse_codex32(capsys.readouterr().out.strip())
    assert isinstance(artifact, MasterSeed)
    assert artifact.header.identifier == _fingerprint_identifier(artifact.seed_bytes)


def test_fresh_shared_create_does_not_prompt_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    def forbidden(_prompt: str) -> str:
        raise AssertionError("fresh create prompted without --existing")

    monkeypatch.setattr(sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", forbidden)

    assert main(["create", "2", "--indices", "ac", "--plain"]) == 0
    assert len(_output_artifacts(_Result(0, capsys.readouterr().out, ""))) == 2


def test_existing_create_uses_one_unambiguous_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_module = importlib.import_module("codex32._cli_input")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return VECTOR_4["secret_s"]

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["create", "2", "--indices", "ac", "--existing", "--plain"]) == 0
    assert prompts == ["Enter an existing codex32 secret or hexadecimal seed: "]
    assert capsys.readouterr().err.startswith("\n")


def test_create_accepts_positional_headers_and_preserves_index_order() -> None:
    fingerprinted = _invoke(["create", "0"])
    unshared = _invoke(["create", "0test"])
    random_header = _invoke(["create", "3"])
    shared = _invoke(["create", "ms13cash", "--indices", "7cad"])

    fingerprinted_secret = _output_artifacts(fingerprinted)[0]
    unshared_secret = _output_artifacts(unshared)[0]
    random_shares = _output_artifacts(random_header)
    shares = _output_artifacts(shared)
    assert isinstance(fingerprinted_secret, MasterSeed)
    assert fingerprinted_secret.header.identifier == _fingerprint_identifier(fingerprinted_secret.seed_bytes)
    assert unshared_secret.header.identifier == "test"
    assert len(random_shares) == 5
    assert len(random_shares[0].header.identifier) == 4
    assert "".join(share.header.index for share in shares) == "7cad"
    assert all(isinstance(share, Share) for share in shares)
    basis = [share for share in shares[:3] if isinstance(share, Share)]
    assert recover_secret(basis).header.identifier == "cash"


@pytest.mark.parametrize("threshold", range(2, 10))
def test_create_defaults_to_threshold_plus_two_shares(threshold: int) -> None:
    result = _invoke(["create", f"{threshold}test"])
    shares = _output_artifacts(result)

    assert result.exit_code == 0
    assert len(shares) == threshold + 2
    assert all(isinstance(share, Share) for share in shares)
    assert len({share.header.index for share in shares}) == threshold + 2
    assert "test recovery using what you wrote down" in result.stderr


def test_pretty_create_separates_share_blocks() -> None:
    result = _invoke_terminal(["create", "2test"])

    assert result.stdout.startswith("Bitcoin master-seed share ")
    assert result.stdout.count("\n\nBitcoin master-seed share ") == 3
    assert result.stderr.endswith("Before relying on this backup, test recovery using what you wrote down.\n")


def test_create_raw_seed_and_resharing_accept_random_identifiers() -> None:
    raw = bytes(range(16))
    rejected_raw = _invoke(["create"], raw.hex())
    random_raw = _invoke(["create", "--existing"], raw.hex())
    accepted_raw = _invoke(["create", "0test", "--existing"], raw.hex())
    source = parse_codex32(VECTOR_4["secret_s"])
    rejected_split = _invoke(["create"], source.text)
    missing_threshold = _invoke(["create", "--existing"], source.text)
    random_split = _invoke(["create", "2", "--indices", "ac", "--existing"], source.text)
    accepted_split = _invoke(["create", "2name", "--indices", "ac", "--existing"], source.text)

    random_secret = _output_artifacts(random_raw)[0]
    assert isinstance(random_secret, MasterSeed) and random_secret.seed_bytes == raw
    assert rejected_raw.exit_code != 0
    assert rejected_split.exit_code != 0
    assert "Use --existing" in rejected_raw.stderr
    assert "Use --existing" in rejected_split.stderr
    assert "choose a sharing threshold" in missing_threshold.stderr
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
    shared = _invoke(["create", "cl13cln2", "--indices", "7cad"])
    default_shared = _invoke(["create", "cl12cln2"])
    source = _output_artifacts(unshared, "cl")[0]
    split = _invoke(["create", "cl12name", "--indices", "ac", "--existing"], source.text)
    raw = _invoke(["create", "cl10raw0", "--existing"], bytes(range(32)).hex())
    random_identifier = _invoke(["create", "cl10"])

    assert isinstance(source, CoreLightningSecret)
    assert source.header.identifier == "cln2"
    assert source.payload_symbols[-1] & 15 == 0
    assert len(_output_artifacts(default_shared, "cl")) == 4
    raw_secret = _output_artifacts(raw, "cl")[0]
    assert isinstance(raw_secret, CoreLightningSecret)
    assert raw_secret.secret_bytes == bytes(range(32))
    assert isinstance(_output_artifacts(random_identifier, "cl")[0], CoreLightningSecret)
    for result, threshold in ((shared, 3), (split, 2)):
        shares = _output_artifacts(result, "cl")
        assert len(shares) >= threshold
        assert isinstance(recover_secret(shares[:threshold]), CoreLightningSecret)


def test_create_help_explains_headers_and_profile_specific_bytes() -> None:
    result = _invoke(["create", "--help"])

    assert result.exit_code == 0
    assert "[HEADER]" in result.stdout
    assert "such as 3cash or 3" in result.stdout
    assert "omit to create a new unshared Bitcoin master seed" in " ".join(result.stdout.split())
    assert "length of a new Bitcoin master seed" in result.stdout
    assert "16 or 32 bytes" in " ".join(result.stdout.split())
    assert "two more than needed for recovery" in " ".join(result.stdout.split())
    assert "--existing" in result.stdout
    assert "use an existing codex32 secret or hexadecimal seed" in result.stdout
    assert "print without transcription formatting" in result.stdout

    fixed_size = _invoke(["create", "cl10cln2", "--bytes", "32"])
    assert fixed_size.exit_code == 2
    assert "Core Lightning secrets are always 32 bytes" in fixed_size.stderr


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

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    prompts: list[str] = []

    def answer(prompt: str) -> str:
        assert "DANGER: Incorrect input" in capsys.readouterr().err
        prompts.append(prompt)
        return VECTOR_1["secret_s"][9:-13]

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", answer)

    assert main(["checksum", VECTOR_1["secret_s"][:9]]) == 0
    assert prompts == ["Remaining non-pink bold squares: "]


def test_checksum_danger_is_red_only_at_a_terminal() -> None:
    stdout, stderr = io.StringIO(), _TTYOutput()
    worksheet = VECTOR_1["secret_s"][3:-13]
    with (
        patch.object(sys, "stdin", io.StringIO(worksheet)),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(["checksum"])

    assert status == 0
    assert "\x1b[1;31mDANGER:\x1b[0m" in stderr.getvalue()
    assert "\x1b[" not in stdout.getvalue()


def test_checksum_help_uses_book_worksheet_language() -> None:
    result = _invoke(["checksum", "--help"])

    assert result.exit_code == 0
    assert "using its non-pink bold squares" in result.stdout
    assert "worksheet header; omit to enter it at the prompt" in result.stdout
    assert "128" not in result.stdout and "256" not in result.stdout


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

    help_result = _invoke(["correct", "-h"])
    help_text = " ".join(help_result.stdout.split())
    assert "--prefix" not in help_text
    assert "use ? for an erasure" in help_text
    assert "-e, --erasure POSITION" in help_text
    assert "one-based position counted backward from the end" in help_text


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


@pytest.mark.parametrize(
    "damaged",
    (
        "ms12test5xxyxxuxxxxxxxxxpxxxxxxxxxx4nzvca9cmczlw",
        "ms12test5xxyxxuxxxxxxxxxpxxxxxxxxxx4nzvca9cmczl?",
    ),
)
def test_correction_failure_directs_user_to_original_backup(damaged: str) -> None:
    result = _invoke(["correct"], damaged)

    assert result.exit_code != 0
    assert result.stderr.strip() == ("codex32 correct: No valid correction found. Check the original backup.")


def test_wallet_commands_are_thin_master_seed_adapters() -> None:
    xprv = _invoke(["xprv"], VECTOR_1["secret_s"])
    xpub = _invoke(["wallet", "multisig-xpub", "--account", "0"], VECTOR_1["secret_s"])
    public = _invoke(["wallet", "bitcoin-core", "watch-only"], VECTOR_1["secret_s"])
    private = _invoke(["wallet", "bitcoin-core", "restore"], VECTOR_1["secret_s"])

    assert xprv.exit_code == xpub.exit_code == public.exit_code == private.exit_code == 0
    assert xprv.stdout.strip() == VECTOR_1["xprv"]
    assert xpub.stdout.startswith("[3f3521a6/48h/0h/0h/2h]xpub")
    assert len(json.loads(public.stdout)) == 4
    assert all("xprv" not in record["desc"] for record in json.loads(public.stdout))
    assert all("xprv" in record["desc"] for record in json.loads(private.stdout))
    assert "contains the root private key and can spend funds" in private.stderr
    assert "\x1b[" not in private.stderr + private.stdout
    assert public.stderr == ""
    assert public.stdout.count("\n") == private.stdout.count("\n") == 1


@pytest.mark.parametrize(
    "command",
    (("xprv",), ("wallet", "bitcoin-core", "restore")),
)
def test_root_authority_warning_is_red_only_at_a_terminal(
    command: tuple[str, ...],
) -> None:
    stdout, stderr = io.StringIO(), _TTYOutput()
    with (
        patch.object(sys, "stdin", io.StringIO(VECTOR_1["secret_s"])),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(command)

    assert status == 0
    assert "\x1b[1;31mWarning:\x1b[0m" in stderr.getvalue()
    assert "\x1b[" not in stdout.getvalue()


def test_wallet_cli_rejects_non_ms_profiles() -> None:
    for command in (
        ("xprv",),
        ("wallet", "multisig-xpub"),
        ("wallet", "bitcoin-core", "watch-only"),
        ("wallet", "bitcoin-core", "restore"),
    ):
        result = _invoke(list(command), SHARING_VECTORS["cl"]["S"])
        assert result.exit_code != 0
        assert "only Bitcoin master seed input" in result.stderr


def test_help_exposes_only_v1_commands() -> None:
    result = _invoke(["-h"])
    bare = _invoke([])

    assert bare == result
    assert result.exit_code == 0
    assert result.stdout.startswith("usage: codex32 [-h] [--version] COMMAND ...")
    assert "\noptions:\n" in result.stdout
    assert "\ncommands:\n  COMMAND\n" in result.stdout
    assert "-h, --help  show this help message and exit" in result.stdout
    assert "--version   show the installed version and exit" in result.stdout
    assert "Create, check, recover, and use codex32 Bitcoin seed backups." in result.stdout
    descriptions = (
        "check     check whether a secret or share is intact",
        "secret    recover a secret from shares",
        "share     derive a share from codex32 strings",
        "correct   suggest repairs for damaged backup text",
        "checksum  finish a codex32 checksum worksheet",
        "create    create a new backup or split an existing secret",
        "wallet    export data for Bitcoin wallet software",
        "xprv      export the root extended private key",
    )
    positions = [result.stdout.index(f"{description}\n") for description in descriptions]
    assert positions == sorted(positions)
    assert "Do not type a seed or share into the command itself." in result.stdout
    assert "Enter it when prompted, or pipe it into the command." in result.stdout
    assert "Codex32" not in result.stdout.replace("Codex32 Book", "")
    assert "BIP93" not in result.stdout and "interoperability" not in result.stdout
    assert "--pretty" not in result.stdout


def test_nested_commands_and_positionals_follow_help_table_style() -> None:
    wallet = _invoke(["wallet", "--help"])
    core = _invoke(["wallet", "bitcoin-core", "--help"])
    share = _invoke(["share", "--help"])
    checksum = _invoke(["checksum", "--help"])
    create = _invoke(["create", "--help"])

    assert "multisig-xpub       export an account xpub" in wallet.stdout
    assert "bitcoin-core        export wallet-import data" in wallet.stdout
    assert "restore             restore signing ability" in core.stdout
    assert "watch-only          find transactions" in core.stdout
    assert "INDEX       index for the derived share" in share.stdout
    assert "HEADER      worksheet header; omit to enter it at the prompt" in checksum.stdout
    assert "HEADER             backup header or sharing threshold" in create.stdout
    assert "\nDerive an additional share from existing codex32 strings.\n" in share.stdout
    assert "\nCreate a new backup or split an existing secret.\n" in create.stdout


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
    executable = Path(sys.executable).with_name("codex32")
    installed = subprocess.run(
        [str(executable), "--version"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert direct.exit_code == installed.returncode == 0
    assert direct.stdout == installed.stdout
    assert direct.stderr == installed.stderr == ""
    assert direct.stdout.startswith("codex32 ")


@pytest.mark.parametrize(
    "command",
    (
        ("check",),
        ("secret",),
        ("share",),
        ("create",),
        ("checksum",),
        ("correct",),
        ("xprv",),
        ("wallet",),
        ("wallet", "multisig-xpub"),
        ("wallet", "bitcoin-core"),
        ("wallet", "bitcoin-core", "restore"),
        ("wallet", "bitcoin-core", "watch-only"),
    ),
)
def test_every_installed_command_has_help(command: tuple[str, ...]) -> None:
    executable = Path(sys.executable).with_name("codex32")
    result = subprocess.run(
        [str(executable), *command, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith(f"usage: codex32 {' '.join(command)}")
    assert result.stderr == ""


def test_tty_adapter_has_no_persistent_history_or_raw_terminal_code() -> None:
    module = importlib.import_module("codex32._cli_input")
    assert module.__file__ is not None
    source = Path(module.__file__).read_text()

    for forbidden in (
        "add_history(",
        "read_history_file(",
        "write_history_file(",
        "termios",
        "prompt_toolkit",
    ):
        assert forbidden not in source
    assert "set_auto_history(False)" in source
    assert "os.dup2(saved_stdout, stdout_fd)" in source


def test_production_size_budgets_are_enforced() -> None:
    module = importlib.import_module("codex32")
    assert module.__file__ is not None
    package = Path(module.__file__).parent
    counts = {path.name: len(path.read_text().splitlines()) for path in package.glob("*.py")}

    assert sum(counts.values()) < 3000
