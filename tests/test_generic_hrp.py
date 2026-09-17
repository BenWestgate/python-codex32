"""Opaque-HRP protocol and façade regressions."""

import contextlib
import io
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

    generic_help = _invoke(main, ["--help"])[1]
    ms_help = _invoke(ms_main, ["--help"])[1]
    assert ms_help == (
        "usage: ms32 [-h] [--version] COMMAND ...\n\n"
        "Create, check, and recover codex32 backups and restore wallets from them.\n\n"
        "options:\n"
        "  -h, --help  show this help message and exit\n"
        "  --version   show the installed version and exit\n\n"
        "commands:\n"
        "  COMMAND\n"
        "    check     check a secret or share for errors\n"
        "    secret    recover a secret from shares\n"
        "    share     derive a share from codex32 strings\n"
        "    correct   suggest repairs for a damaged codex32 string\n"
        "    create    create or confirm a backup, or split an existing secret\n"
        "    wallet    restore a Bitcoin Core wallet\n"
        "    xprv      export the root extended private key\n\n"
        "Never include a secret or share in command arguments.\n"
        "Enter it when prompted. Some commands also accept piped input.\n"
    )
    for command in ("check", "correct", "secret", "share"):
        assert command in generic_help and command in ms_help
    for command in ("create", "xprv", "wallet"):
        assert command not in generic_help and command in ms_help
    assert "checksum" not in generic_help and "checksum" not in ms_help
    correct_help = _invoke(main, ["correct", "--help"])[1]
    assert (
        "Suggest repairs for wrong, unreadable, missing, extra, or swapped characters\n"
        "or four-character groups. Use ? for each unreadable character. Check suggested\n"
        "repairs against the original backup."
    ) in correct_help
    assert "--bytes" not in correct_help
    assert "--bytes" in _invoke(ms_main, ["correct", "--help"])[1]
    secret_help = _invoke(ms_main, ["secret", "--help"])[1]
    assert (
        "Recover the secret using exactly the threshold number of shares from the same\n"
        "set. Use different share indices. You can also enter an existing secret to\n"
        "display it."
    ) in secret_help
    share_help = _invoke(ms_main, ["share", "--help"])[1]
    assert (
        "Derive a share at INDEX using exactly the threshold number of codex32 strings\n"
        "from the same set. Use different input indices; one input may be the secret.\n"
        "INDEX must differ from S and the input indices."
    ) in share_help
    wallet_help = _invoke(ms_main, ["wallet", "--help"])[1]
    assert wallet_help == (
        "usage: ms32 wallet [-h] [--account ACCOUNT] [--timestamp TIMESTAMP]\n\n"
        "Restore a Bitcoin Core wallet.\n\n"
        "options:\n"
        "  -h, --help            show this help message and exit\n"
        "  --account ACCOUNT     account number (default: 0)\n"
        "  --timestamp TIMESTAMP\n"
        "                        search for transactions since this Unix timestamp; use\n"
        "                        0 for all history or now for a new wallet\n"
    )
    assert _invoke(main, ["--version"])[1].startswith("codex32 ")
    assert _invoke(ms_main, ["--version"])[1].startswith("ms32 ")


def test_cli_share_is_generic_and_ms32_share_is_scoped(monkeypatch) -> None:
    class _FakeCore:
        @staticmethod
        def fingerprint(_secret: object) -> bytes:
            return b"\0\0\0\0"

    monkeypatch.setattr("codex32.cli.BitcoinCore.connect", lambda *args, **kwargs: _FakeCore())
    basis = UNKNOWN["short"]["S"] + "\n" + UNKNOWN["short"]["A"] + "\n"
    status, output, error = _invoke(main, ["share", "d", "--plain"], basis)
    assert (status, output.strip(), error) == (0, UNKNOWN["short"]["D"], "")
    assert _invoke(ms_main, ["share", "d", "--plain"], basis)[0] == 2
