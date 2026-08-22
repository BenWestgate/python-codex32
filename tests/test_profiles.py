"""Independent profile-length, checksum-boundary, and CL tests."""

import pytest
from data.bip93_vectors import (
    INVALID_CODEX32,
    INVALID_CODEX32_LONG,
    VALID_CODEX32,
    VALID_CODEX32_LONG,
    VECTOR_2,
    VECTOR_6,
)

from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Share,
    complete_checksum,
    parse_codex32,
)
from codex32.bech32 import CHARSET, _parse, _verify
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import (
    InvalidCase,
    InvalidCharacter,
    InvalidLength,
    MissingSeparator,
    UnknownProfile,
    UnsupportedOperation,
)

_SHORT_GENERATORS = (
    0x19DC500CE73FDE210,
    0x1BFAE00DEF77FE529,
    0x1FBD920FFFE7BEE52,
    0x1739640BDEEE3FDAD,
    0x07729A039CFC75F5A,
)
_LONG_GENERATORS = (
    0x3D59D273535EA62D897,
    0x7A9BECB6361C6C51507,
    0x543F9B7E6C38D8A2A0E,
    0x0C577EAECCF1990D13C,
    0x1887F74F8DC71B10651,
)


def _polymod(values: list[int], generators: tuple[int, ...], length: int) -> int:
    residue = 1
    shift = 5 * (length - 1)
    mask = (1 << shift) - 1
    for value in values:
        top = residue >> shift
        residue = ((residue & mask) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                residue ^= generator
    return residue


def _oracle_encode(hrp: str, body: str, *, force_long: bool | None = None) -> str:
    use_long = len(body) > 80 if force_long is None else force_long
    generators = _LONG_GENERATORS if use_long else _SHORT_GENERATORS
    length = 15 if use_long else 13
    constant = 0x43381E570BF4798AB26 if use_long else 0x10CE0795C2FD1E62A
    values = (
        [ord(character) >> 5 for character in hrp]
        + [0]
        + [ord(character) & 31 for character in hrp]
        + [CHARSET.index(character) for character in body]
    )
    residue = _polymod(values + [0] * length, generators, length) ^ constant
    checksum = "".join(
        CHARSET[(residue >> (5 * (length - 1 - index))) & 31]
        for index in range(length)
    )
    return f"{hrp}1{body}{checksum}"


def _payload(data: bytes, padding: int) -> str:
    accumulator = int.from_bytes(data, "big")
    padding_bits = (-len(data) * 8) % 5
    combined = (accumulator << padding_bits) | padding
    count = (len(data) * 8 + 4) // 5
    return "".join(
        CHARSET[(combined >> (5 * (count - 1 - index))) & 31]
        for index in range(count)
    )


def test_every_ms_byte_length_and_legal_parsed_padding() -> None:
    for byte_length in range(16, 65):
        data = bytes((index * 29 + byte_length) % 256 for index in range(byte_length))
        padding_bits = (-byte_length * 8) % 5
        for padding in range(1 << padding_bits):
            text = _oracle_encode("ms", "0tests" + _payload(data, padding))
            secret = parse_codex32(text)
            assert isinstance(secret, MasterSeed)
            assert secret.seed_bytes == data


def test_ms_checksum_boundary_uses_only_data_part_length() -> None:
    short = _oracle_encode("ms", "0tests" + "q" * 74)
    long = _oracle_encode("ms", "0tests" + "q" * 76)
    assert len("0tests" + "q" * 74) == 80
    assert len("0tests" + "q" * 76) == 82
    assert isinstance(parse_codex32(short), MasterSeed)
    assert isinstance(parse_codex32(long), MasterSeed)
    with pytest.raises(InvalidLength):
        parse_codex32(_oracle_encode("ms", "0tests" + "q" * 75))


def test_46_and_47_byte_factories_choose_short_and_long() -> None:
    short = MasterSeed.from_seed(bytes(46), identifier="test")
    long = MasterSeed.from_seed(bytes(47), identifier="test")
    assert len(short.payload_symbols) == 74
    assert len(long.payload_symbols) == 76
    assert len(short.text) == 2 + 1 + 80 + 13
    assert len(long.text) == 2 + 1 + 82 + 15


def test_unknown_hrp_is_rejected_before_checksum_interpretation() -> None:
    valid_generic = _oracle_encode("zz", "0tests" + "q" * 26)
    with pytest.raises(UnknownProfile):
        parse_codex32(valid_generic)


def test_core_lightning_constructor_and_parsed_padding() -> None:
    original = parse_codex32(VECTOR_6["codex32_peev"])
    assert isinstance(original, CoreLightningSecret)
    generated = CoreLightningSecret.from_secret_bytes(
        original.secret_bytes, identifier="peev"
    )
    assert generated.payload_symbols[-1] & 0xF == 0
    payload = list(generated.payload_symbols)
    payload[-1] |= 0xF
    nonzero = _oracle_encode(
        "cl", "0peevs" + "".join(CHARSET[value] for value in payload)
    )
    parsed = parse_codex32(nonzero)
    assert isinstance(parsed, CoreLightningSecret)
    assert parsed.secret_bytes == original.secret_bytes


def test_profile_completion_capabilities() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    assert isinstance(share, Share)
    assert complete_checksum(share.text[:-13]).text == share.text
    with pytest.raises(UnsupportedOperation):
        complete_checksum("bip39_12w10tests" + "q" * 27)
    with pytest.raises(InvalidLength):
        complete_checksum("cl10testsq")


@pytest.mark.parametrize(
    ("value", "checksum", "minimum", "maximum"),
    [
        *((value, _CODEX32, 0, 80) for value in VALID_CODEX32),
        *((value, _CODEX32_LONG, 81, 1008) for value in VALID_CODEX32_LONG),
    ],
)
def test_official_generic_checksum_vectors_at_codec_level(
    value: str, checksum: _Checksum, minimum: int, maximum: int
) -> None:
    hrp, encoded = _parse(value, max_length=2048)
    covered_length = len(value) - 1 - checksum.length
    assert minimum <= covered_length <= maximum
    assert _verify(hrp, encoded, checksum)


@pytest.mark.parametrize(
    ("value", "checksum", "minimum", "maximum"),
    [
        *((value, _CODEX32, 0, 80) for value in INVALID_CODEX32),
        *((value, _CODEX32_LONG, 81, 1008) for value in INVALID_CODEX32_LONG),
    ],
)
def test_official_invalid_generic_checksum_vectors(
    value: str, checksum: _Checksum, minimum: int, maximum: int
) -> None:
    try:
        hrp, encoded = _parse(value, max_length=2048)
    except (InvalidCase, InvalidCharacter, InvalidLength, MissingSeparator) as error:
        # Lexical failure is one of the official invalid classes.
        assert error is not None
        return
    covered_length = len(value) - 1 - checksum.length
    assert not (
        minimum <= covered_length <= maximum and _verify(hrp, encoded, checksum)
    )
