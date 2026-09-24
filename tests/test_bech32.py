"""Check Bech32 encoding, decoding, and invalid input handling."""

import pytest

from codex32.bech32 import (
    CHARSET,
    bech32_decode,
    bech32_encode,
    bech32_hrp_expand,
    chars_to_u5,
    convertbits,
    u5_to_chars,
)
from codex32.checksums import CODEX32
from codex32.errors import (
    InvalidCase,
    InvalidCharacter,
    InvalidChecksum,
    InvalidLength,
    InvalidPadding,
    MissingSeparator,
)


def test_u5_character_round_trip() -> None:
    values = list(range(32))
    assert u5_to_chars(values) == CHARSET
    assert chars_to_u5(CHARSET.upper()) == values


@pytest.mark.parametrize("value", (-1, 32))
def test_u5_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(InvalidCharacter):
        u5_to_chars([value])


def test_lexical_parser_preserves_no_semantics() -> None:
    assert bech32_decode("MS10TESTS") == ("ms", chars_to_u5("0tests"))


def test_decoder_optionally_verifies_and_removes_checksum() -> None:
    data = chars_to_u5("0tests")
    encoded = bech32_encode("ms", data, CODEX32)

    assert bech32_decode(encoded) == ("ms", data + CODEX32.create(bech32_hrp_expand("ms") + data))
    assert bech32_decode(encoded, CODEX32) == ("ms", data)

    damaged = encoded[:-1] + ("q" if encoded[-1] != "q" else "p")
    with pytest.raises(InvalidChecksum, match="invalid codex32 checksum"):
        bech32_decode(damaged, CODEX32)

    with pytest.raises(InvalidChecksum, match="invalid codex32 checksum"):
        bech32_decode("ms1q", CODEX32)


def test_invalid_data_character_uses_complete_one_based_position() -> None:
    with pytest.raises(InvalidCharacter) as raised:
        bech32_decode("MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW'")

    assert str(raised.value) == ("Apostrophe (') is not allowed in a codex32 string (position 49).")


@pytest.mark.parametrize(
    ("value", "error"),
    (
        ("ms10testS", InvalidCase),
        ("ms0tests", MissingSeparator),
        ("1q", MissingSeparator),
        ("ms1i", InvalidCharacter),
        ("ms1q\n", InvalidCharacter),
        ("m" * 1025, InvalidLength),
    ),
)
def test_lexical_rejections(value: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        bech32_decode(value)


def test_convert_bits_requires_explicit_integer_padding() -> None:
    data = bytes.fromhex("ffeedd")
    symbols = convertbits(data, 8, 5, pad=True, pad_value=1)
    assert bytes(convertbits(symbols, 5, 8, pad=False, accept_any_padding=True)) == data
    with pytest.raises(InvalidPadding):
        convertbits(data, 8, 5, pad=True, pad_value=2)
