"""Generation-only CRC padding and its sharing invariant."""

from collections import Counter

import pytest
from data.bip93_vectors import VECTOR_2, VECTOR_4

import codex32
from codex32 import MasterSeed, Share, parse_codex32
from codex32.bip93 import _has_generation_padding, _payload_padding
from codex32.checksums import _CRC, _crc_pad
from codex32.gf32 import _multiply as _gf32_multiply


@pytest.mark.parametrize(
    ("data", "padding_bits", "expected"),
    (
        (bytes(range(20)), 0, 0),
        (bytes(range(18)), 1, 0),
        (bytes(range(16)), 2, 2),
        (bytes(range(19)), 3, 7),
        (bytes(range(17)), 4, 11),
    ),
)
def test_frozen_crc_padding_values(
    data: bytes, padding_bits: int, expected: int
) -> None:
    """Freeze the compact CRC convention, not an optimality claim."""
    assert (-len(data) * 8) % 5 == padding_bits
    assert _crc_pad(data) == expected


def test_compact_crc_definitions_are_unchanged() -> None:
    assert _CRC[0] is None
    assert tuple(
        (checksum.kind, checksum.generators, checksum.length)
        for checksum in _CRC[1:]
        if checksum is not None
    ) == (
        ("CRC1", (1,), 1),
        ("CRC2", (3,), 2),
        ("CRC3", (3,), 3),
        ("CRC4", (3,), 4),
    )


def test_master_seed_factory_uses_crc_for_every_byte_length() -> None:
    for byte_length in range(16, 65):
        seed = bytes(
            (position * 73 + byte_length) % 256 for position in range(byte_length)
        )
        secret = MasterSeed.from_seed(seed, identifier="test")
        assert _has_generation_padding(secret)
        assert _payload_padding(secret) == _crc_pad(seed)


def test_parsed_master_seed_validity_is_independent_of_crc() -> None:
    generated = MasterSeed.from_seed(
        bytes.fromhex(VECTOR_4["secret_hex"]), identifier="leet"
    )
    parsed = [
        parse_codex32(VECTOR_4[f"secret_s_alternate_{padding}"])
        for padding in range(16)
    ]
    assert all(isinstance(secret, MasterSeed) for secret in parsed)
    assert len({secret.payload_symbols for secret in parsed}) == 16
    assert sum(_has_generation_padding(secret) for secret in parsed) == 1
    assert generated.payload_symbols in {secret.payload_symbols for secret in parsed}


def test_padding_acceptance_is_balanced_for_every_nonzero_lagrange_weight() -> None:
    """A free GF(32) symbol leaves each permitted padding suffix equally likely."""
    for padding_bits in range(1, 5):
        expected_per_suffix = 1 << (5 - padding_bits)
        suffix_mask = (1 << padding_bits) - 1
        for coefficient in range(1, 32):
            for fixed_value in range(32):
                counts = Counter(
                    (fixed_value ^ _gf32_multiply(coefficient, free_value)) & suffix_mask
                    for free_value in range(32)
                )
                assert counts == Counter(
                    {suffix: expected_per_suffix for suffix in range(1 << padding_bits)}
                )


def test_crc_never_becomes_share_or_public_api_semantics() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    assert isinstance(share, Share)
    assert not hasattr(share, "seed_bytes")
    assert not hasattr(share, "padding")
    assert not hasattr(share, "crc")
    assert not hasattr(codex32, "crc_pad")
