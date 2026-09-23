"""Independent profile-length, checksum-boundary, and CL tests."""

import pytest
from _codex32_oracle import oracle_encode as _oracle_encode
from data.bip93_vectors import (
    BIP93_ADDITIONAL_MASTER_SEEDS,
    FORMERLY_VALID_UNSUPPORTED_MS,
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
    parse_codex32,
)
from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    bech32_decode,
    bech32_hrp_expand,
)
from codex32.bip93 import _checksum_for_encoded_length
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import (
    InvalidCase,
    InvalidCharacter,
    InvalidChecksum,
    InvalidLength,
    InvalidThreshold,
    MissingSeparator,
)
from codex32.profiles.ms32 import SEED_BYTE_LENGTHS, TEXT_LENGTHS


def _payload(data: bytes, padding: int) -> str:
    accumulator = int.from_bytes(data, "big")
    padding_bits = (-len(data) * 8) % 5
    combined = (accumulator << padding_bits) | padding
    count = (len(data) * 8 + 4) // 5
    return "".join(CHARSET[(combined >> (5 * (count - 1 - index))) & 31] for index in range(count))


def test_every_supported_ms_size_and_legal_parsed_padding() -> None:
    for byte_length in SEED_BYTE_LENGTHS:
        data = bytes((index * 29 + byte_length) % 256 for index in range(byte_length))
        padding_bits = (-byte_length * 8) % 5
        for padding in range(1 << padding_bits):
            text = _oracle_encode("ms", "0tests" + _payload(data, padding))
            secret = parse_codex32(text)
            assert isinstance(secret, MasterSeed)
            assert secret.seed_bytes == data


def test_supported_factories_use_exact_bip93_lengths() -> None:
    artifacts = tuple(MasterSeed.from_seed(bytes(size), identifier="test") for size in SEED_BYTE_LENGTHS)
    assert tuple(len(artifact.text) for artifact in artifacts) == TEXT_LENGTHS
    assert all(
        _checksum_for_encoded_length("ms", len(bech32_decode(artifact.text)[1])) is _CODEX32
        for artifact in artifacts[:-1]
    )
    assert _checksum_for_encoded_length("ms", len(bech32_decode(artifacts[-1].text)[1])) is _CODEX32_LONG


@pytest.mark.parametrize(("seed_hex", "text"), BIP93_ADDITIONAL_MASTER_SEEDS)
def test_pr2258_supported_size_vectors(seed_hex: str, text: str) -> None:
    artifact = parse_codex32(text)
    assert isinstance(artifact, MasterSeed)
    assert artifact.seed_bytes == bytes.fromhex(seed_hex)


@pytest.mark.parametrize("text", FORMERLY_VALID_UNSUPPORTED_MS)
def test_pr2258_rejects_formerly_valid_unsupported_sizes(text: str) -> None:
    expected = InvalidChecksum if text in FORMERLY_VALID_UNSUPPORTED_MS[-2:] else InvalidLength
    with pytest.raises(expected):
        parse_codex32(text)


def test_every_other_16_through_64_byte_size_is_rejected() -> None:
    for byte_length in set(range(16, 65)) - set(SEED_BYTE_LENGTHS):
        data = bytes(byte_length)
        with pytest.raises(InvalidLength):
            MasterSeed.from_seed(data, identifier="test")
        with pytest.raises(InvalidLength):
            parse_codex32(_oracle_encode("ms", "0tests" + _payload(data, 0)))


def test_expanded_codeword_boundaries() -> None:
    header = "0tests"
    max_regular = _oracle_encode("ms", header + "q" * 69)
    first_long = _oracle_encode("ms", header + "q" * 70)
    assert len(bech32_hrp_expand("ms")) + len(bech32_decode(max_regular)[1]) == 93
    assert len(bech32_hrp_expand("ms")) + len(bech32_decode(first_long)[1]) == 96
    assert _checksum_for_encoded_length("ms", len(bech32_decode(max_regular)[1])) is _CODEX32
    assert _checksum_for_encoded_length("ms", len(bech32_decode(first_long)[1])) is _CODEX32_LONG

    for body_length in (74, 75):
        body = _chars_to_u5(header + "q" * (body_length - len(header)))
        checksum = _CODEX32_LONG.create(bech32_hrp_expand("ms") + body)
        invalid = "ms1" + "".join(CHARSET[value] for value in body + checksum)
        with pytest.raises(InvalidLength):
            _checksum_for_encoded_length("ms", len(bech32_decode(invalid)[1]))


def test_expanded_codeword_upper_bound() -> None:
    max_body = _chars_to_u5("0tests" + "q" * 997)
    max_text = _oracle_encode("ms", "".join(CHARSET[value] for value in max_body))
    assert len(bech32_hrp_expand("ms")) + len(bech32_decode(max_text)[1]) == 1023
    assert _checksum_for_encoded_length("ms", len(bech32_decode(max_text)[1])) is _CODEX32_LONG

    oversized_body = _chars_to_u5("0tests" + "q" * 998)
    oversized = _oracle_encode("ms", "".join(CHARSET[value] for value in oversized_body))
    with pytest.raises(InvalidLength):
        _checksum_for_encoded_length("ms", len(bech32_decode(oversized)[1]))


def test_long_checksum_residue_stays_correct_past_its_period() -> None:
    # Probes the polynomial itself with u5 values, not a codex32 string: the
    # arithmetic still closes beyond the code's 1023-symbol period, so length is
    # what verify() has to enforce, not the residue.
    body = bech32_hrp_expand("ms") + [0] * 1100
    codeword = body + _CODEX32_LONG.create(body)
    assert len(codeword) > 1023
    assert _CODEX32_LONG.polymod(codeword) == _CODEX32_LONG.constant
    assert _CODEX32_LONG.verify(codeword) is False


def test_checksum_is_verified_before_unknown_hrp_dispatch() -> None:
    valid_generic = _oracle_encode("zz", "0tests" + "q" * 26)
    artifact = parse_codex32(valid_generic)
    assert artifact.hrp == "zz"
    assert artifact.profile is None
    with pytest.raises(InvalidChecksum):
        parse_codex32("zz10tests" + "q" * 39)


def test_common_header_is_validated_before_checksum() -> None:
    malformed = VECTOR_2["secret_S"][:3] + "1" + VECTOR_2["secret_S"][4:]
    with pytest.raises(InvalidThreshold):
        parse_codex32(malformed)


@pytest.mark.parametrize(
    ("hrp", "payload_length"),
    (("ms", 26), ("cl", 52), ("bip39_12w", 27), ("bip39_24w", 53)),
)
def test_checksum_precedes_profile_length(hrp: str, payload_length: int) -> None:
    valid = _oracle_encode(hrp, "0tests" + "q" * payload_length)
    with pytest.raises(InvalidChecksum):
        parse_codex32(valid[:-1])


def test_generic_length_and_checksum_precede_ms_length() -> None:
    with pytest.raises(InvalidLength, match="at least 21"):
        parse_codex32("ms1")
    with pytest.raises(InvalidChecksum):
        parse_codex32("ms10tests" + "q" * 40)


def test_valid_profile_length_still_reports_checksum_failure() -> None:
    valid = _oracle_encode("ms", "0tests" + "q" * 26)
    damaged = valid[:-1] + ("q" if valid[-1] != "q" else "p")
    with pytest.raises(InvalidChecksum):
        parse_codex32(damaged)


def test_core_lightning_constructor_and_parsed_padding() -> None:
    original = parse_codex32(VECTOR_6["codex32_peev"])
    assert isinstance(original, CoreLightningSecret)
    assert original.payload_symbols[-1] & 0xF == 0
    payload = list(original.payload_symbols)
    payload[-1] |= 0xF
    nonzero = _oracle_encode("cl", "0peevs" + "".join(CHARSET[value] for value in payload))
    parsed = parse_codex32(nonzero)
    assert isinstance(parsed, CoreLightningSecret)
    assert parsed.secret_bytes == original.secret_bytes


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
    hrp, encoded = bech32_decode(value)
    expanded_length = len(bech32_hrp_expand(hrp)) + len(encoded)
    assert checksum.polymod(bech32_hrp_expand(hrp) + encoded) == checksum.constant
    assert checksum.verify(bech32_hrp_expand(hrp) + encoded) is (
        checksum.maximum_length is None or expanded_length <= checksum.maximum_length
    )


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
        hrp, encoded = bech32_decode(value)
    except (InvalidCase, InvalidCharacter, InvalidLength, MissingSeparator) as error:
        # Lexical failure is one of the official invalid classes.
        assert error is not None
        return
    expanded_length = len(bech32_hrp_expand(hrp)) + len(encoded)
    assert not (expanded_length <= maximum and checksum.verify(bech32_hrp_expand(hrp) + encoded))
