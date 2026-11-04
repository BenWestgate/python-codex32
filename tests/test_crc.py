"""Generation-only CRC padding and its sharing invariant."""

from collections import Counter

import pytest
from data.bip93_vectors import VECTOR_2, VECTOR_4

import codex32
from codex32 import CorrectionCandidate, MasterSeed, Share, parse_codex32
from codex32.checksums import _CRC, _crc_pad
from codex32.correction import _best
from codex32.gf32 import _multiply as _gf32_multiply
from codex32.profiles.ms32 import (
    SEED_BYTE_LENGTHS,
    _has_generation_padding,
    _has_legacy_generation_padding,
    _payload_padding,
)


@pytest.mark.parametrize(
    ("data", "padding_bits", "expected"),
    (
        (bytes(range(20)), 0, 0),
        (bytes(range(18)), 1, 0),
        (bytes(range(16)), 2, 1),
        (bytes(range(19)), 3, 0),
        (bytes(range(17)), 4, 4),
    ),
)
def test_frozen_crc_padding_values(data: bytes, padding_bits: int, expected: int) -> None:
    """Freeze the compact CRC convention, not an optimality claim."""
    assert (-len(data) * 8) % 5 == padding_bits
    assert _crc_pad(data) == expected


def test_compact_crc_definitions_are_unchanged() -> None:
    assert _CRC[0] is None
    assert tuple(
        (checksum.kind, checksum.generators, checksum.length, checksum.constant)
        for checksum in _CRC[1:]
        if checksum is not None
    ) == (
        ("CRC1", (1,), 1, 0),
        ("CRC2", (3,), 2, 0b11),
        ("CRC3", (3,), 3, 0b111),
        ("CRC4", (3,), 4, 0b1111),
    )


def test_master_seed_factory_uses_crc_for_every_supported_size() -> None:
    for byte_length in SEED_BYTE_LENGTHS:
        seed = bytes((position * 73 + byte_length) % 256 for position in range(byte_length))
        secret = MasterSeed.from_seed(seed, identifier="test")
        assert _has_generation_padding(secret)
        assert _payload_padding(secret) == _crc_pad(seed)


def test_parsed_master_seed_validity_is_independent_of_crc() -> None:
    generated = MasterSeed.from_seed(bytes.fromhex(VECTOR_4["secret_hex"]), identifier="leet")
    parsed = [parse_codex32(VECTOR_4[f"secret_s_alternate_{padding}"]) for padding in range(16)]
    assert all(isinstance(secret, MasterSeed) for secret in parsed)
    assert len({secret.payload_symbols for secret in parsed}) == 16
    assert sum(_has_generation_padding(secret) for secret in parsed) == 1
    assert generated.payload_symbols in {secret.payload_symbols for secret in parsed}


def test_tie_break_prefers_current_then_legacy_crc_padding() -> None:
    parsed = [parse_codex32(VECTOR_4[f"secret_s_alternate_{padding}"]) for padding in range(16)]
    assert all(isinstance(secret, MasterSeed) for secret in parsed)
    current = next(secret for secret in parsed if _has_generation_padding(secret))
    legacy = next(secret for secret in parsed if _has_legacy_generation_padding(secret))
    other = next(secret for secret in parsed if secret not in (current, legacy))

    def best(*secrets: MasterSeed) -> tuple[MasterSeed, ...]:
        candidates = [CorrectionCandidate(s, (), 1, 0, 0, _has_generation_padding(s)) for s in secrets]
        return tuple(candidate.artifact for candidate in _best(candidates))

    assert best(other, legacy, current) == (current,)
    assert best(other, legacy) == (legacy,)


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
                assert counts == Counter({suffix: expected_per_suffix for suffix in range(1 << padding_bits)})


def test_crc_never_becomes_share_or_public_api_semantics() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    assert isinstance(share, Share)
    assert not hasattr(share, "seed_bytes")
    assert not hasattr(share, "padding")
    assert not hasattr(share, "crc")
    assert not hasattr(codex32, "crc_pad")
