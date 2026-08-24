"""Migration-only BIP39 profile validation."""

import pytest
from test_profiles import _oracle_encode

from codex32 import Bip39Secret, Profile, Share, parse_codex32
from codex32.errors import (
    InvalidBip39Checksum,
    InvalidChecksum,
    InvalidLength,
    InvalidPadding,
)

BIP39_12W_ZERO = "bip39_12w10testsqqqqqqqqqqqqqqqqqqqqqqqqqqcwa5plrxrewp27"
BIP39_24W_ZERO = "bip39_24w10testsqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqxv5hjvxqkrlt8cg"


@pytest.mark.parametrize(
    ("text", "profile", "payload_length"),
    (
        (BIP39_12W_ZERO, Profile.BIP39_12W, 27),
        (BIP39_24W_ZERO, Profile.BIP39_24W, 53),
    ),
)
def test_frozen_bip39_zero_entropy_fixtures(text: str, profile: Profile, payload_length: int) -> None:
    secret = parse_codex32(text)
    assert isinstance(secret, Bip39Secret)
    assert secret.profile is profile
    assert len(secret.payload_symbols) == payload_length
    assert parse_codex32(text.upper()).text == text.upper()


@pytest.mark.parametrize(
    ("hrp", "payload"),
    (("bip39_12w", "q" * 27), ("bip39_24w", "q" * 53)),
)
def test_valid_outer_checksum_does_not_mask_bad_bip39_checksum(hrp: str, payload: str) -> None:
    with pytest.raises(InvalidBip39Checksum):
        parse_codex32(_oracle_encode(hrp, "0tests" + payload))


def test_outer_checksum_precedes_bip39_secret_semantics() -> None:
    invalid_bip39 = _oracle_encode("bip39_12w", "0tests" + "q" * 27)
    damaged = invalid_bip39[:-1] + ("q" if invalid_bip39[-1] != "q" else "p")
    with pytest.raises(InvalidChecksum):
        parse_codex32(damaged)


def test_bip39_secret_requires_zero_outer_padding() -> None:
    body = BIP39_12W_ZERO.rsplit("1", 1)[1][:-13]
    payload = body[6:]
    # The final three bits are outer u5 padding; change only one of them.
    changed = payload[:-1] + "e"
    with pytest.raises(InvalidPadding):
        parse_codex32(_oracle_encode("bip39_12w", "0tests" + changed))


def test_bip39_share_is_only_a_uniform_symbol_mask() -> None:
    share = parse_codex32(_oracle_encode("bip39_12w", "2testa" + "q" * 27))
    assert isinstance(share, Share)
    assert not hasattr(share, "seed_bytes")
    assert not hasattr(share, "entropy")
    assert not hasattr(share, "mnemonic")


@pytest.mark.parametrize(
    ("hrp", "payload"),
    (("bip39_12w", "q" * 26), ("bip39_24w", "q" * 54)),
)
def test_bip39_exact_payload_lengths(hrp: str, payload: str) -> None:
    with pytest.raises(InvalidLength):
        parse_codex32(_oracle_encode(hrp, "2testa" + payload))
