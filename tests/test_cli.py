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

from codex32 import MasterSeed, Secret, Share, parse_codex32, recover_secret
from codex32.cli import main


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


def _output_artifacts(result: _Result, profile: str = "ms") -> list[Share | Secret]:
    return [
        parse_codex32(line)
        for line in result.stdout.splitlines()
        if line.lower().startswith(profile + "1")
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
        "Valid codex32 secret.\n"
        "Application: Bitcoin master seed\n"
        "Threshold: 0 (unshared)\n"
        "Identifier: TEST\n\n"
        "Valid codex32 secret.\n"
        "Application: Bitcoin master seed\n"
        "Threshold: 3\n"
        "Identifier: CASH\n\n"
        "Valid codex32 share.\n"
        "Application: Bitcoin master seed\n"
        "Threshold: 2\n"
        "Identifier: NAME\n"
        "Share index: A\n\n"
        "Valid codex32 secret.\n"
        "Application: Core Lightning\n"
        "Threshold: 2\n"
        "Identifier: TEST\n\n"
        "Valid codex32 secret.\n"
        "Application: 12-word BIP39 worksheet\n"
        "Threshold: 0 (unshared)\n"
        "Identifier: TEST\n\n"
        "Valid codex32 secret.\n"
        "Application: 24-word BIP39 worksheet\n"
        "Threshold: 2\n"
        "Identifier: TEST\n"
    )
    assert result.stderr == ""
    assert all(text not in result.stdout for text in strings)
    for forbidden in (
        "Header(",
        "Master fingerprint:",
        "Application: ms",
        "Application: cl",
        "Application: bip39",
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
    assert "does not authenticate the intended wallet" in help_text


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

    def answer() -> str:
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
    assert rejected not in captured.out
    assert "mixed upper/lower case codex32 string" in captured.err
    assert captured.err.count("Enter a codex32 string: ") == 2


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
    bad_one = suffix[:-1] + ("q" if suffix[-1] != "q" else "p")
    bad_two = suffix[:-2] + ("q" if suffix[-2] != "q" else "p") + suffix[-1]
    answers = iter((VECTOR_2["share_A"], bad_one, bad_two, suffix))
    editor = _FakeLineEditor()

    def answer() -> str:
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
    monkeypatch.setattr(builtins, "input", lambda: next(answers))

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert captured.err.count("Enter a codex32 string: ") == 2


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
    monkeypatch.setattr(input_module.os, "isatty", lambda _descriptor: True)
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
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", lambda: next(answers))

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"]
    assert "Accepted share 1 (1 of 2 required)." in captured.err
    assert captured.err.startswith("Enter a codex32 string: ")
    assert "codex32 share 2 of 2: MS12NAME" in captured.err


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

    def answer() -> str:
        editor.run_hook()
        return next(answers)

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(input_module, "_line_editor", editor)
    monkeypatch.setattr(builtins, "input", answer)

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"].upper()
    assert captured.err.startswith("Enter a codex32 string: ")
    assert "codex32 share 2 of 2: MS12NAME" in captured.err
    assert "ms and cl cannot be combined" in captured.err
    assert "Rejected: share indices must be distinct" in captured.err
    assert captured.err.count("codex32 share 2 of 2: MS12NAME") == 3
    assert first not in captured.err and mismatch not in captured.err
    assert editor.inserted == [first[len("MS12NAME") :]]
    assert editor.hook is None


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
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", lambda: next(answers))

    assert main(["share", "d"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == VECTOR_3["derived_d"]
    assert captured.err.startswith("Enter a codex32 string: ")
    assert "Accepted basis item 3 (3 of 3 required)." in captured.err


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

    def answer() -> str:
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
    assert "accepts only ms or cl" in bip39.stderr


def test_create_defaults_to_an_unshared_128_bit_master_seed() -> None:
    result = _invoke(["create"])
    artifacts = _output_artifacts(result)

    assert result.exit_code == 0
    assert len(artifacts) == 1
    assert isinstance(artifacts[0], MasterSeed)
    assert len(artifacts[0].seed_bytes) == 16
    assert artifacts[0].header.threshold == 0


def test_create_accepts_positional_headers_and_preserves_index_order() -> None:
    unshared = _invoke(["create", "0test"])
    shared = _invoke(["create", "ms13cash", "--indices", "7cad"])

    unshared_secret = _output_artifacts(unshared)[0]
    shares = _output_artifacts(shared)
    assert unshared_secret.header.identifier == "test"
    assert "".join(share.header.index for share in shares) == "7cad"
    assert all(isinstance(share, Share) for share in shares)
    basis = [share for share in shares[:3] if isinstance(share, Share)]
    assert recover_secret(basis).header.identifier == "cash"


def test_create_raw_seed_and_resharing_require_explicit_headers() -> None:
    raw = bytes(range(16))
    rejected_raw = _invoke(["create"], raw.hex())
    accepted_raw = _invoke(["create", "0test"], raw.hex())
    source = parse_codex32(VECTOR_4["secret_s"])
    rejected_split = _invoke(["create"], source.text)
    accepted_split = _invoke(["create", "2name", "--indices", "ac"], source.text)

    assert rejected_raw.exit_code != 0
    assert rejected_split.exit_code != 0
    secret = _output_artifacts(accepted_raw)[0]
    assert isinstance(secret, MasterSeed) and secret.seed_bytes == raw
    shares = _output_artifacts(accepted_split)
    assert isinstance(source, MasterSeed)
    basis = [share for share in shares if isinstance(share, Share)]
    recovered = recover_secret(basis)
    assert isinstance(recovered, MasterSeed)
    assert recovered.seed_bytes == source.seed_bytes


def test_create_rejects_cl_bip39_partial_basis_and_selector_conflicts() -> None:
    cl = _invoke(["create", "cl10cln2"])
    bip39 = _invoke(["create", "bip39_12w10test"])
    partial = _invoke(["create", "2test", "--indices", "ac"], VECTOR_2["share_A"])
    conflict = _invoke(["create", "2test", "--shares", "2", "--indices", "ac"])

    for result in (cl, bip39, partial, conflict):
        assert result.exit_code != 0


def test_checksum_defaults_to_ms_and_accepts_explicit_cl() -> None:
    ms = parse_codex32(VECTOR_1["secret_s"])
    ms_body = ms.text[3:-13]
    default = _invoke(["checksum"], ms_body)
    explicit = _invoke(["checksum", ms.text[:9]], ms.text[9:-13])

    cl = SHARING_VECTORS["cl"]["S"]
    cl_result = _invoke(["checksum", cl[:9]], cl[9:-13])

    assert default.exit_code == explicit.exit_code == cl_result.exit_code == 0
    assert default.stdout.strip() == explicit.stdout.strip() == ms.text
    assert cl_result.stdout.strip() == cl
    assert "does not create entropy" in default.stderr


def test_checksum_enforces_published_sizes_and_capabilities() -> None:
    unusual = _invoke(["checksum"], "0tests" + "q" * 27)
    bip39 = _invoke(["checksum"], "bip39_12w10tests" + "q" * 27)

    assert unusual.exit_code != 0
    assert "128 or 256 bits" in unusual.stderr
    assert bip39.exit_code != 0
    assert "limited to ms and cl" in bip39.stderr


def test_pretty_secret_has_fingerprint_but_pretty_share_does_not() -> None:
    secret = _invoke(["secret", "--pretty"], VECTOR_1["secret_s"])
    share = _invoke(
        ["share", "d", "--pretty"], VECTOR_2["share_A"], VECTOR_2["share_C"]
    )

    assert secret.exit_code == share.exit_code == 0
    assert "Master fingerprint:" in secret.stdout
    assert "Master fingerprint:" not in share.stdout
    assert "Identifier:" in secret.stdout and "Identifier:" in share.stdout


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
    fixed = _invoke(["correct", "--prefix", "cl"], damaged)
    residue = _invoke(["correct", "--residue"], "2ppjkw73qdjvc")

    assert fixed.exit_code == 1 and original in fixed.stderr
    assert residue.exit_code == 0
    assert "Add x to reverse position 38." in residue.stdout


def test_wallet_commands_are_thin_master_seed_adapters() -> None:
    xprv = _invoke(["xprv"], VECTOR_1["secret_s"])
    xpub = _invoke(
        ["wallet", "multisig-xpub", "--account", "0"], VECTOR_1["secret_s"]
    )
    public = _invoke(
        ["wallet", "bitcoin-core", "watch-only"], VECTOR_1["secret_s"]
    )
    private = _invoke(
        ["wallet", "bitcoin-core", "restore"], VECTOR_1["secret_s"]
    )

    assert (
        xprv.exit_code == xpub.exit_code == public.exit_code == private.exit_code == 0
    )
    assert xprv.stdout.strip() == VECTOR_1["xprv"]
    assert xpub.stdout.startswith("[3f3521a6/48h/0h/0h/2h]xpub")
    assert len(json.loads(public.stdout)) == 4
    assert all("xprv" not in record["desc"] for record in json.loads(public.stdout))
    assert all("xprv" in record["desc"] for record in json.loads(private.stdout))
    assert "root authority" in private.stderr
    assert public.stderr == ""
    assert public.stdout.count("\n") == private.stdout.count("\n") == 1


def test_wallet_cli_rejects_non_ms_profiles() -> None:
    for command in (
        ("xprv",),
        ("wallet", "multisig-xpub"),
        ("wallet", "bitcoin-core", "watch-only"),
        ("wallet", "bitcoin-core", "restore"),
    ):
        result = _invoke(list(command), SHARING_VECTORS["cl"]["S"])
        assert result.exit_code != 0
        assert "only ms codex32 input" in result.stderr


def test_help_exposes_only_v1_commands() -> None:
    result = _invoke(["-h"])
    bare = _invoke([])

    assert bare == result
    assert result.exit_code == 0
    assert result.stdout.startswith("usage: codex32 [-h] [--version] COMMAND ...")
    assert "Create, check, recover, and use codex32 Bitcoin seed backups." in result.stdout
    descriptions = (
        "check     Check whether a backup or share is valid.",
        "secret    Recover the secret from enough shares.",
        "share     Derive an additional share.",
        "correct   Suggest repairs for damaged backup text.",
        "checksum  Finish a Codex32 Book checksum worksheet.",
        "create    Create a backup or split one into shares.",
        "wallet    Export data for Bitcoin wallet software.",
        "xprv      Export the root private key (advanced).",
    )
    positions = [result.stdout.index(description) for description in descriptions]
    assert positions == sorted(positions)
    assert "Never type or paste a seed or share into the command itself." in result.stdout
    assert "Enter it when prompted or provide it through stdin." in result.stdout
    assert "BIP93" not in result.stdout and "interoperability" not in result.stdout
    assert "--pretty" not in result.stdout


def test_long_options_must_not_be_abbreviated() -> None:
    result = _invoke(
        ["wallet", "bitcoin-core", "restore", "--acc", "0"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 2
    assert "unrecognized arguments: --acc 0" in result.stderr


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
    counts = {
        path.name: len(path.read_text().splitlines()) for path in package.glob("*.py")
    }

    assert sum(counts.values()) < 3000
    assert max(counts.values()) <= 650
    assert counts["generation.py"] <= 350
    assert counts["cli.py"] <= 500
    assert counts["wallet.py"] <= 250
