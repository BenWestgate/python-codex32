"""End-to-end tests for the small codex32 CLI."""

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
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_4
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO

from codex32 import MasterSeed, Share, parse_codex32, recover_secret
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


def _output_artifacts(result: _Result, profile: str = "ms"):
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


def test_tty_recovery_prefills_the_authenticated_prefix(monkeypatch) -> None:
    cli_module = importlib.import_module("codex32.cli")

    class Terminal:
        @staticmethod
        def isatty() -> bool:
            return True

    answers = iter((VECTOR_2["share_A"], VECTOR_2["share_C"][-40:]))
    prompts: list[str] = []

    def prompt(label: str) -> str:
        prompts.append(label)
        return next(answers)

    monkeypatch.setattr(cli_module.sys, "stdin", Terminal())
    monkeypatch.setattr(cli_module, "_prompt", prompt)

    artifacts = cli_module._artifacts(sequential=True)

    assert [artifact.text for artifact in artifacts] == [
        VECTOR_2["share_A"],
        VECTOR_2["share_C"],
    ]
    assert "MS12NAME" in prompts[1].upper()


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
    assert "API-only" in bip39.stderr


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
    assert recover_secret(shares[:3]).header.identifier == "cash"  # type: ignore[arg-type]


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
    assert recover_secret(shares).seed_bytes == source.seed_bytes  # type: ignore[arg-type,union-attr]


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
    xpub = _invoke(["xpub", "--account", "0"], VECTOR_1["secret_s"])
    public = _invoke(["descriptors"], VECTOR_1["secret_s"])
    private = _invoke(["descriptors", "--private"], VECTOR_1["secret_s"])

    assert (
        xprv.exit_code == xpub.exit_code == public.exit_code == private.exit_code == 0
    )
    assert xprv.stdout.strip() == VECTOR_1["xprv"]
    assert xpub.stdout.startswith("[3f3521a6/48h/0h/0h/2h]xpub")
    assert len(json.loads(public.stdout)) == 4
    assert all("xprv" not in record["desc"] for record in json.loads(public.stdout))
    assert all("xprv" in record["desc"] for record in json.loads(private.stdout))
    assert "root authority" in private.stderr


def test_wallet_cli_rejects_non_ms_profiles() -> None:
    for command in ("xprv", "xpub", "descriptors"):
        result = _invoke([command], SHARING_VECTORS["cl"]["S"])
        assert result.exit_code != 0
        assert "only ms secrets" in result.stderr


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
        "descriptors",
        "xprv",
        "xpub",
    ):
        assert command in result.stdout
    assert "--pretty" not in result.stdout


def test_long_options_must_not_be_abbreviated() -> None:
    result = _invoke(["descriptors", "--priv"], VECTOR_1["secret_s"])

    assert result.exit_code == 2
    assert "unrecognized arguments: --priv" in result.stderr


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
        "verify",
        "secret",
        "share",
        "create",
        "checksum",
        "correct",
        "xprv",
        "xpub",
        "descriptors",
    ),
)
def test_every_installed_command_has_help(command: str) -> None:
    executable = Path(sys.executable).with_name("codex32")
    result = subprocess.run(
        [str(executable), command, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith(f"usage: codex32 {command}")
    assert result.stderr == ""
