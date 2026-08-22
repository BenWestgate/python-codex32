"""Security invariants for the deliberately small master-seed generator."""

import inspect
from collections import Counter

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

import codex32
from codex32 import (
    MasterSeed,
    Share,
    generate_master_seed,
    parse_codex32,
    recover_secret,
    split_secret,
)
from codex32.bech32 import CHARSET
from codex32.bip93 import IDX_SORT, _has_generation_padding
from codex32.errors import (
    HeaderCollision,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareSelection,
    InvalidThreshold,
)
from codex32.generation import (
    ORDINARY_INDICES,
    _fingerprint_identifier,
)


def _indices(shares: tuple[Share, ...]) -> str:
    return "".join(share.header.index for share in shares)


def _seed(byte_length: int) -> bytes:
    return bytes((position * 109 + byte_length) % 256 for position in range(byte_length))


def test_entropy_mapping_and_index_population_are_exact() -> None:
    assert Counter(value & 31 for value in range(256)) == Counter(
        {symbol: 8 for symbol in range(32)}
    )
    assert ORDINARY_INDICES == tuple(IDX_SORT[1:])
    assert len(set(ORDINARY_INDICES)) == 31
    assert set(ORDINARY_INDICES) == set(CHARSET) - {"s"}


def test_public_signatures_have_no_entropy_padding_or_exclusion_controls() -> None:
    assert set(inspect.signature(generate_master_seed).parameters) == {
        "seed_bytes",
        "byte_length",
        "threshold",
        "share_count",
        "indices",
        "identifier",
    }
    assert set(inspect.signature(split_secret).parameters) == {
        "secret",
        "threshold",
        "identifier",
        "share_count",
        "indices",
    }
    for function in (generate_master_seed, split_secret):
        parameters = set(inspect.signature(function).parameters)
        assert parameters.isdisjoint({"rng", "entropy", "padding", "excluded_headers"})


def test_fresh_unshared_ms_supports_every_byte_length() -> None:
    for byte_length in range(16, 65):
        secret, shares = generate_master_seed(byte_length=byte_length)
        assert shares == ()
        assert len(secret.seed_bytes) == byte_length
        assert secret.header.threshold == 0
        assert secret.header.identifier == _fingerprint_identifier(secret.seed_bytes)
        assert _has_generation_padding(secret)


def test_fresh_shared_ms_supports_every_byte_length() -> None:
    for byte_length in range(16, 65):
        secret, shares = generate_master_seed(
            byte_length=byte_length,
            threshold=2,
            indices="ac",
        )
        assert _indices(shares) == "ac"
        assert _has_generation_padding(secret)
        assert recover_secret(shares) == secret


@pytest.mark.parametrize("threshold", range(2, 10))
def test_fresh_generation_recovers_at_every_threshold(threshold: int) -> None:
    secret, shares = generate_master_seed(threshold=threshold, share_count=threshold)
    assert len({share.header.index for share in shares}) == threshold
    assert recover_secret(shares) == secret


@given(
    byte_length=st.integers(min_value=16, max_value=64),
    threshold=st.integers(min_value=2, max_value=9),
)
@settings(max_examples=20, deadline=None)
def test_supplied_seed_round_trip(byte_length: int, threshold: int) -> None:
    secret, shares = generate_master_seed(
        _seed(byte_length),
        threshold=threshold,
        indices=ORDINARY_INDICES[:threshold],
        identifier="test",
    )
    assert secret.seed_bytes == _seed(byte_length)
    assert recover_secret(shares) == secret


def test_raw_bytes_require_an_identifier() -> None:
    raw = bytes(range(16))
    with pytest.raises(InvalidIdentifier):
        generate_master_seed(raw)
    with pytest.raises(InvalidLength):
        generate_master_seed(raw, byte_length=16, identifier="test")
    secret, shares = generate_master_seed(raw, identifier="TEST")
    assert shares == ()
    assert secret.header.identifier == "test"


def test_explicit_and_random_output_order_contracts() -> None:
    _secret, shares = generate_master_seed(
        bytes(range(16)),
        threshold=3,
        indices="7CaD",
        identifier="test",
    )
    assert _indices(shares) == "7cad"

    source = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    _secret, all_shares = split_secret(
        source,
        2,
        share_count=31,
        identifier="name",
    )
    assert len(set(_indices(all_shares))) == 31
    assert set(_indices(all_shares)) == set(ORDINARY_INDICES)


@pytest.mark.parametrize(
    "arguments",
    (
        {"threshold": 0, "share_count": 1},
        {"threshold": 2},
        {"threshold": 2, "share_count": 2, "indices": "ac"},
        {"threshold": 2, "share_count": 1},
        {"threshold": 2, "share_count": 32},
        {"threshold": 2, "indices": "a"},
        {"threshold": 2, "indices": "aa"},
        {"threshold": 2, "indices": "sa"},
        {"threshold": 2, "indices": "ia"},
    ),
)
def test_invalid_share_selections(arguments: dict[str, object]) -> None:
    with pytest.raises(InvalidShareSelection):
        generate_master_seed(
            bytes(range(16)),
            identifier="test",
            **arguments,  # type: ignore[arg-type]
        )


def test_unordered_indices_and_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(TypeError):
        generate_master_seed(
            bytes(range(16)), threshold=2, indices={"a", "c"}, identifier="test"  # type: ignore[arg-type]
        )
    for threshold in (1, 10, True, "2"):
        with pytest.raises(InvalidThreshold):
            generate_master_seed(
                bytes(range(16)),
                threshold=threshold,  # type: ignore[arg-type]
                share_count=2,
                identifier="test",
            )


def test_split_preserves_parsed_padding_and_requires_a_new_header() -> None:
    source = parse_codex32(VECTOR_4["secret_s_alternate_0"])
    assert isinstance(source, MasterSeed)
    secret, shares = split_secret(source, 2, indices="ac", identifier="name")
    assert secret.payload_symbols == source.payload_symbols
    assert recover_secret(shares).payload_symbols == source.payload_symbols
    with pytest.raises(HeaderCollision):
        split_secret(secret, 2, indices="ac", identifier="name")
    with pytest.raises(TypeError):
        split_secret(source, 2, indices="ac")  # type: ignore[call-arg]


def test_split_rejects_non_ms_artifacts() -> None:
    artifacts = (
        parse_codex32(VECTOR_6["codex32_peev"]),
        parse_codex32(SHARING_VECTORS["bip39_12w"]["S"]),
        parse_codex32(VECTOR_2["share_A"]),
        VECTOR_2["secret_S"],
    )
    for artifact in artifacts:
        with pytest.raises(TypeError):
            split_secret(artifact, 2, indices="ac", identifier="test")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("vector", "expected"),
    ((VECTOR_1, "8u6j"), (VECTOR_2, "l2mg"), (VECTOR_3, "regv")),
)
def test_unshared_fingerprint_identifier_vectors(
    vector: dict[str, str], expected: str
) -> None:
    assert _fingerprint_identifier(bytes.fromhex(vector["secret_hex"])) == expected


def test_reduced_public_surface_has_no_partial_or_cl_generation() -> None:
    assert codex32.generate_master_seed is generate_master_seed
    assert codex32.split_secret is split_secret
    assert not hasattr(codex32, "generate_core_lightning_secret")
    assert not hasattr(codex32, "complete_partial_basis")
    assert "basis" not in inspect.signature(generate_master_seed).parameters
