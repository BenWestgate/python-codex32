"""Tests for the deliberately root-only stdlib BIP32 boundary."""

from types import SimpleNamespace

import pytest

import codex32._bip32 as bip32

_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
_XPRV = (
    "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvN"
    "KmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi"
)


def test_master_xprv_matches_bip32_root_vector() -> None:
    assert bip32._master_xprv_from_seed(_SEED) == _XPRV


@pytest.mark.parametrize(
    "private_key",
    (
        b"\x00" * 32,
        bip32._SECP256K1_ORDER.to_bytes(32, "big"),
    ),
)
def test_root_validation_rejects_invalid_master_scalars(
    monkeypatch: pytest.MonkeyPatch, private_key: bytes
) -> None:
    digest = private_key + b"\x11" * 32
    monkeypatch.setattr(
        bip32.hmac,
        "new",
        lambda *_args, **_kwargs: SimpleNamespace(digest=lambda: digest),
    )

    assert bip32._valid_root(b"seed") is False
