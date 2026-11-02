"""Opaque-HRP protocol and façade regressions."""

import contextlib
import io
import re
import sys
from unittest.mock import patch

import pytest
from _codex32_oracle import oracle_encode

from codex32 import (
    CorrectionContext,
    Secret,
    Share,
    correct,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.cli import main, ms_main
from codex32.errors import MismatchedHrp, MismatchedProfile
from tools._wallet_test_vectors import STUB_FINGERPRINT

UNKNOWN = {
    "short": {
        "S": "zz12testsqqqqqqqqqqqqqqqqqqqqqqqqqqzkztt5804a3kj",
        "A": "zz12testappppppppppppppppppppppppppqx2qjvn23a93u",
        "C": "zz12testckkkkkkkkkkkkkkkkkkkkkkkkkk8hkvgpvnla60f",
        "D": "zz12testdyyyyyyyyyyyyyyyyyyyyyyyyyy2ytw509m9an2r",
    },
    "long": {
        "S": "zz12testsqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqxp8whfj90cp8nf6",
        "A": "zz12testappppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppd5x0lnqrkjml75w",
        "C": "zz12testckkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkpu3crek2vf3jmq3",
        "D": "zz12testdyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyr8r276gasejuwxc",
    },
}


@pytest.mark.parametrize("vector", UNKNOWN.values(), ids=UNKNOWN)
def test_opaque_hrp_parse_complete_recover_and_derive(vector: dict[str, str]) -> None:
    secret = parse_codex32(vector["S"].upper())
    a = parse_codex32(vector["A"].upper())
    c = parse_codex32(vector["C"].upper())
    assert isinstance(secret, Secret) and type(secret) is Secret
    assert isinstance(a, Share) and isinstance(c, Share)
    assert secret.hrp == a.hrp == c.hrp == "zz"
    assert secret.profile is a.profile is c.profile is None
    assert secret.text.isupper()
    assert recover_secret([a, c]).text == vector["S"].upper()
    assert derive_share([secret, a], "d").text == vector["D"].upper()


def test_sharing_compares_normalized_hrp_and_keeps_compatibility_error_name() -> None:
    assert MismatchedProfile is MismatchedHrp
    zz = parse_codex32(UNKNOWN["short"]["S"])
    yy = parse_codex32(oracle_encode("yy", "2testa" + "p" * 26))
    with pytest.raises(MismatchedHrp):
        derive_share([zz, yy], "c")


def test_unknown_hrp_correction_freezes_namespace_and_repairs_structure() -> None:
    source = UNKNOWN["short"]["C"]
    substituted = source[:18] + ("q" if source[18] != "q" else "p") + source[19:]
    omitted = source[:22] + source[23:]
    erased = source[:20] + "?" + source[21:]
    group_omitted = source[:20] + source[24:]
    extra = source[:20] + "q" + source[20:]
    group_extra = source[:20] + "qpzr" + source[20:]
    for damaged in (substituted, omitted, erased, group_omitted, extra, group_extra):
        candidates = correct(CorrectionContext("ZZ"), damaged)
        assert candidates and candidates[0].artifact.text == source
    assert correct(CorrectionContext("zz"), "yy1" + source[3:]) == ()


def test_generic_correction_does_not_guess_missing_or_replaced_prefix():
    source = UNKNOWN["short"]["C"]
    for damaged in (source[3:], source[:2] + "?" + source[3:]):
        status, output, error = _invoke(main, ["correct"], damaged)
        assert status == 2 and output == ""
        assert "application prefix" in error
    # A supplied opaque namespace remains immutable, even when near registered ms.
    assert correct(CorrectionContext("mt"), "ms" + source[2:]) == ()


def _invoke(entrypoint: object, args: list[str], text: str = "") -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO(text)),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = entrypoint(args)  # type: ignore[operator]
    return status, stdout.getvalue(), stderr.getvalue()


def _help(entrypoint: object, *args: str) -> str:
    status, output, error = _invoke(entrypoint, [*args, "--help"])
    assert status == 0 and error == ""
    assert output.startswith("usage: ")
    return output


def test_cli_split_and_unknown_neutral_summary() -> None:
    status, output, error = _invoke(main, ["check"], UNKNOWN["short"]["C"])
    assert status == 0 and error == ""
    assert output == (
        "Valid codex32 share C.\nHRP: ZZ\nBackup identifier: TEST\nShares needed for recovery: 2\n"
    )
    assert _invoke(main, ["create"])[0] == 2
    assert _invoke(ms_main, ["check"], UNKNOWN["short"]["C"])[0] == 2
    unshared = parse_codex32(oracle_encode("zz", "0tests" + "q" * 26))
    assert _invoke(main, ["check"], unshared.text)[1] == (
        "Valid unshared codex32 secret.\nHRP: ZZ\nBackup identifier: TEST\n"
    )


def test_cli_help_exposes_commands_and_safety_guidance() -> None:
    generic_help = _help(main)
    ms_help = _help(ms_main)
    assert generic_help.startswith("usage: codex32 ")
    assert ms_help.startswith("usage: ms32 ")

    for command in ("check", "correct", "secret", "share"):
        assert re.search(rf"(?m)^\s+{command}(?:\s|$)", generic_help)
        assert re.search(rf"(?m)^\s+{command}(?:\s|$)", ms_help)
    for command in ("create", "xprv", "wallet"):
        assert not re.search(rf"(?m)^\s+{command}(?:\s|$)", generic_help)
        assert re.search(rf"(?m)^\s+{command}(?:\s|$)", ms_help)

    for output in (generic_help, ms_help):
        assert re.search(r"(?i)(?:never|do not|don't).*secret.*share.*arguments?", output)
        assert "prompt" in output.lower()
        assert "checksum" not in output.lower()

    correct_help = _help(main, "correct")
    assert "?" in correct_help and "original backup" in correct_help
    assert "--bytes" not in correct_help
    assert "--bytes" in _help(ms_main, "correct")

    secret_help = _help(ms_main, "secret")
    assert "threshold" in secret_help and "different share indices" in secret_help
    share_help = _help(ms_main, "share")
    assert "threshold" in share_help and "different input indices" in share_help
    assert "INDEX must differ" in share_help

    wallet_help = _help(ms_main, "wallet")
    assert wallet_help.startswith("usage: ms32 wallet ")
    assert "--account ACCOUNT" in wallet_help
    assert "--timestamp TIMESTAMP" in wallet_help
    assert "all history" in wallet_help and "new wallet" in wallet_help
    assert _invoke(main, ["--version"])[1].startswith("codex32 ")
    assert _invoke(ms_main, ["--version"])[1].startswith("ms32 ")


def test_cli_share_is_generic_and_ms32_share_is_scoped(monkeypatch) -> None:
    class _FakeCore:
        @staticmethod
        def fingerprint(_secret: object) -> bytes:
            return STUB_FINGERPRINT

    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *args, **kwargs: _FakeCore())
    basis = UNKNOWN["short"]["S"] + "\n" + UNKNOWN["short"]["A"] + "\n"
    status, output, error = _invoke(main, ["share", "d", "--plain"], basis)
    assert (status, output.strip(), error) == (0, UNKNOWN["short"]["D"], "")
    assert _invoke(ms_main, ["share", "d", "--plain"], basis)[0] == 2
