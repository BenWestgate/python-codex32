"""End-to-end tests for the small codex32 CLI."""

import builtins
import contextlib
import importlib
import io
import json
import subprocess
import sys
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


def test_verify_supports_every_registered_application() -> None:
    strings = (
        VECTOR_1["secret_s"],
        SHARING_VECTORS["cl"]["S"],
        BIP39_12W_ZERO,
        SHARING_VECTORS["bip39_24w"]["S"],
    )
    result = _invoke(["verify"], *strings)

    assert result.exit_code == 0
    assert len(result.stdout.splitlines()) == 4
    assert "valid ms secret" in result.stdout
    assert "valid cl secret" in result.stdout


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
    assert "Codex32 share 2 of 2: MS12NAME" in captured.err


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
    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", lambda: next(answers))

    status = main(["secret"])
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.strip() == VECTOR_2["secret_S"].upper()
    assert "Codex32 share 2 of 2: MS12NAME" in captured.err
    assert "ms and cl cannot be combined" in captured.err
    assert "Rejected: share indices must be distinct" in captured.err
    assert captured.err.count("Codex32 share 2 of 2: MS12NAME") == 3
    assert first not in captured.err and mismatch not in captured.err


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

    monkeypatch.setattr(input_module.sys, "stdin", Terminal())
    monkeypatch.setattr(builtins, "input", lambda: (_ for _ in ()).throw(exception))

    assert main(["secret"]) == status
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err


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
    result = _invoke(["--help"])

    assert result.exit_code == 0
    for command in (
        "verify",
        "secret",
        "share",
        "create",
        "checksum",
        "correct",
        "xprv",
        "wallet",
    ):
        assert command in result.stdout
    assert "--pretty" not in result.stdout


def test_long_options_must_not_be_abbreviated() -> None:
    result = _invoke(
        ["wallet", "bitcoin-core", "restore", "--acc", "0"],
        VECTOR_1["secret_s"],
    )

    assert result.exit_code == 2
    assert "unrecognized arguments: --acc 0" in result.stderr


def test_wallet_modes_are_mandatory_and_old_commands_are_absent() -> None:
    for command in (["wallet"], ["wallet", "bitcoin-core"], ["xpub"], ["descriptors"]):
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
        ("verify",),
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


def test_tty_adapter_has_no_history_or_terminal_editing_code() -> None:
    module = importlib.import_module("codex32._cli_input")
    assert module.__file__ is not None
    source = Path(module.__file__).read_text()

    for forbidden in ("readline", "termios", "fileno(", "set_history"):
        assert forbidden not in source


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
