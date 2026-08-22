"""Focused tests for the bounded internal lexical/u5 codec."""

import pytest

from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    _convert_bits,
    _parse,
    _u5_to_chars,
)
from codex32.errors import (
    InvalidCase,
    InvalidCharacter,
    InvalidLength,
    InvalidPadding,
    MissingSeparator,
)


def test_u5_character_round_trip() -> None:
    values = list(range(32))
    assert _u5_to_chars(values) == CHARSET
    assert _chars_to_u5(CHARSET.upper()) == values


@pytest.mark.parametrize("value", (-1, 32))
def test_u5_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(InvalidCharacter):
        _u5_to_chars([value])


def test_lexical_parser_preserves_no_semantics() -> None:
    assert _parse("MS10TESTS") == ("ms", _chars_to_u5("0tests"))


@pytest.mark.parametrize(
    ("value", "error"),
    (
        ("ms10testS", InvalidCase),
        ("ms0tests", MissingSeparator),
        ("1q", MissingSeparator),
        ("ms1i", InvalidCharacter),
        ("ms1q\n", InvalidCharacter),
        ("m" * 128, InvalidLength),
    ),
)
def test_lexical_rejections(value: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        _parse(value)


def test_convert_bits_requires_explicit_integer_padding() -> None:
    data = bytes.fromhex("ffeedd")
    symbols = _convert_bits(data, 8, 5, pad=True, pad_value=1)
    assert bytes(
        _convert_bits(symbols, 5, 8, pad=False, accept_any_padding=True)
    ) == data
    with pytest.raises(InvalidPadding):
        _convert_bits(data, 8, 5, pad=True, pad_value=2)
