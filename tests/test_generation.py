"""Audited electronic generation, identifiers, and output selection."""

import inspect
from collections import Counter

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

import codex32
from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Share,
    complete_checksum,
    generate_core_lightning_secret,
    generate_master_seed,
    parse_codex32,
    recover_secret,
    split_secret,
)
from codex32.bech32 import CHARSET, _u5_to_chars
from codex32.bip93 import IDX_SORT, _has_generation_padding, _payload_padding
from codex32.errors import (
    HeaderCollision,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareSelection,
    InvalidThreshold,
)
from codex32.generation import (
    ORDINARY_INDICES,
    _canonical_payload_serialization,
    _finalize_shared,
    _fingerprint_symbols,
    _full_fingerprint_identifier,
    _legacy_shared_identifier,
    _reheader_basis,
    _resolve_default_identifier,
)


def _indices(shares: tuple[Share, ...]) -> str:
    return "".join(share.header.index for share in shares)


def _seed(byte_length: int) -> bytes:
    return bytes(
        (position * 109 + byte_length) % 256 for position in range(byte_length)
    )


def test_byte_to_u5_mapping_is_exactly_balanced() -> None:
    assert Counter(value & 0x1F for value in range(256)) == Counter(
        {symbol: 8 for symbol in range(32)}
    )


def test_fixed_ordinary_index_population_is_complete_and_unique() -> None:
    assert ORDINARY_INDICES == tuple(IDX_SORT[1:])
    assert len(ORDINARY_INDICES) == len(set(ORDINARY_INDICES)) == 31
    assert set(ORDINARY_INDICES) == set(CHARSET) - {"s"}


def test_public_generation_signatures_have_no_entropy_or_padding_controls() -> None:
    expected_parameters = {
        generate_master_seed: {
            "seed_bytes",
            "byte_length",
            "threshold",
            "share_count",
            "indices",
            "identifier",
            "excluded_headers",
        },
        generate_core_lightning_secret: {
            "secret_bytes",
            "identifier",
            "threshold",
            "share_count",
            "indices",
            "excluded_headers",
        },
        split_secret: {
            "secret",
            "threshold",
            "share_count",
            "indices",
            "identifier",
            "excluded_headers",
        },
    }
    forbidden = {"rng", "random", "entropy", "pad", "pad_val", "padding"}
    for function, expected in expected_parameters.items():
        parameters = set(inspect.signature(function).parameters)
        assert parameters == expected
        assert parameters.isdisjoint(forbidden)


def test_fresh_unshared_ms_supports_every_byte_length_and_full_identifier() -> None:
    for byte_length in range(16, 65):
        secret, shares = generate_master_seed(byte_length=byte_length)
        assert shares == ()
        assert len(secret.seed_bytes) == byte_length
        assert secret.header.threshold == 0
        assert secret.header.index == "s"
        assert _has_generation_padding(secret)
        assert secret.header.identifier == _full_fingerprint_identifier(
            _fingerprint_symbols(secret.seed_bytes)
        )


def test_fresh_shared_ms_supports_every_byte_length_and_crc_padding() -> None:
    for byte_length in range(16, 65):
        secret, shares = generate_master_seed(
            byte_length=byte_length,
            threshold=2,
            indices="ac",
        )
        assert _indices(shares) == "ac"
        assert _has_generation_padding(secret)
        assert recover_secret(shares).text == secret.text
        assert secret.text.islower()
        assert all(share.text.islower() for share in shares)


@pytest.mark.parametrize("threshold", range(2, 10))
def test_fresh_ms_generation_recovers_at_every_threshold(threshold: int) -> None:
    secret, shares = generate_master_seed(
        threshold=threshold,
        share_count=threshold,
    )
    assert len(shares) == threshold
    assert len({_share.header.index for _share in shares}) == threshold
    assert recover_secret(shares).text == secret.text


@given(
    byte_length=st.integers(min_value=16, max_value=64),
    threshold=st.integers(min_value=2, max_value=9),
)
@settings(max_examples=20, deadline=None)
def test_supplied_seed_sharing_round_trip(byte_length: int, threshold: int) -> None:
    raw_seed = _seed(byte_length)
    secret, shares = generate_master_seed(
        raw_seed,
        threshold=threshold,
        indices=ORDINARY_INDICES[:threshold],
        identifier="test",
    )
    assert secret.seed_bytes == raw_seed
    assert recover_secret(shares).text == secret.text


def test_raw_ms_bytes_require_identifier_and_forbid_a_length_selector() -> None:
    raw_seed = bytes(range(16))
    with pytest.raises(InvalidIdentifier):
        generate_master_seed(raw_seed)
    with pytest.raises(InvalidLength):
        generate_master_seed(raw_seed, byte_length=len(raw_seed), identifier="test")
    secret, shares = generate_master_seed(raw_seed, identifier="TEST")
    assert shares == ()
    assert secret.seed_bytes == raw_seed
    assert secret.header.identifier == "test"


@pytest.mark.parametrize("byte_length", (15, 65, True, "16"))
def test_invalid_fresh_ms_lengths_are_rejected(byte_length: object) -> None:
    with pytest.raises(InvalidLength):
        generate_master_seed(byte_length=byte_length)  # type: ignore[arg-type]


def test_explicit_indices_preserve_normalized_requested_order() -> None:
    secret, shares = generate_master_seed(
        bytes(range(16)),
        threshold=3,
        indices="7CaD",
        identifier="test",
    )
    assert _indices(shares) == "7cad"
    assert all(share.header.identifier == secret.header.identifier for share in shares)
    assert recover_secret(shares[:3]).seed_bytes == secret.seed_bytes


def test_list_and_tuple_indices_preserve_order() -> None:
    for requested in (["7", "C", "a", "D"], ("7", "C", "a", "D")):
        _secret, shares = generate_master_seed(
            bytes(range(16)),
            threshold=3,
            indices=requested,
            identifier="test",
        )
        assert _indices(shares) == "7cad"


def test_random_share_counts_are_distinct_and_complete_through_31() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    for share_count in range(2, 32):
        secret, shares = split_secret(
            source,
            2,
            share_count=share_count,
            identifier="name",
        )
        output_indices = tuple(share.header.index for share in shares)
        assert len(output_indices) == len(set(output_indices)) == share_count
        assert set(output_indices) <= set(ORDINARY_INDICES)
        assert recover_secret(shares[:2]).seed_bytes == secret.seed_bytes
        if share_count == 31:
            assert set(output_indices) == set(ORDINARY_INDICES)


@pytest.mark.parametrize(
    "arguments",
    (
        {"threshold": 0, "share_count": 1},
        {"threshold": 2},
        {"threshold": 2, "share_count": 2, "indices": "ac"},
        {"threshold": 2, "share_count": 1},
        {"threshold": 2, "share_count": 32},
        {"threshold": 2, "share_count": True},
        {"threshold": 2, "indices": "a"},
        {"threshold": 2, "indices": "aa"},
        {"threshold": 2, "indices": "sa"},
        {"threshold": 2, "indices": "ia"},
    ),
)
def test_invalid_share_selections_are_rejected(arguments: dict[str, object]) -> None:
    with pytest.raises(InvalidShareSelection):
        generate_master_seed(
            bytes(range(16)),
            identifier="test",
            **arguments,  # type: ignore[arg-type]
        )


def test_unordered_or_nonsequence_indices_are_rejected() -> None:
    for indices in ({"a", "c"}, frozenset({"a", "c"}), iter("ac")):
        with pytest.raises(TypeError):
            generate_master_seed(
                bytes(range(16)),
                threshold=2,
                indices=indices,  # type: ignore[arg-type]
                identifier="test",
            )


@pytest.mark.parametrize("threshold", (1, 10, True, "2"))
def test_invalid_generation_thresholds_are_rejected(threshold: object) -> None:
    with pytest.raises(InvalidThreshold):
        generate_master_seed(
            bytes(range(16)),
            threshold=threshold,  # type: ignore[arg-type]
            share_count=2,
            identifier="test",
        )


def test_split_preserves_arbitrary_valid_parsed_ms_padding() -> None:
    source = parse_codex32(VECTOR_4["secret_s_alternate_0"])
    assert isinstance(source, MasterSeed)
    secret, shares = split_secret(source, 2, indices="ac", identifier="name")
    assert secret.payload_symbols == source.payload_symbols
    assert recover_secret(shares).payload_symbols == source.payload_symbols
    assert not _has_generation_padding(source)


def test_split_supports_only_typed_ms_and_cl_secrets() -> None:
    bip39 = parse_codex32(SHARING_VECTORS["bip39_12w"]["S"])
    share = parse_codex32(VECTOR_2["share_A"])
    for artifact in (bip39, share, VECTOR_2["secret_S"]):
        with pytest.raises(TypeError):
            split_secret(  # type: ignore[arg-type]
                artifact,
                2,
                indices="ac",
                identifier="test",
            )


def test_split_secret_rejects_threshold_zero() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    with pytest.raises(InvalidThreshold):
        split_secret(source, 0)


def test_core_lightning_generation_and_splitting_use_zero_padding() -> None:
    fresh, fresh_shares = generate_core_lightning_secret(
        identifier="peev",
        threshold=2,
        indices="7a",
    )
    assert _indices(fresh_shares) == "7a"
    assert _payload_padding(fresh) == 0
    assert recover_secret(fresh_shares).text == fresh.text
    assert fresh.text.islower()
    assert all(share.text.islower() for share in fresh_shares)

    raw_secret = bytes(range(32))
    encoded, encoded_shares = generate_core_lightning_secret(
        raw_secret,
        identifier="name",
        threshold=3,
        indices="7cad",
    )
    assert encoded.secret_bytes == raw_secret
    assert _indices(encoded_shares) == "7cad"
    assert recover_secret(encoded_shares[:3]).text == encoded.text

    split, split_shares = split_secret(
        encoded,
        2,
        indices="ac",
        identifier="test",
    )
    assert split.payload_symbols == encoded.payload_symbols
    assert recover_secret(split_shares).secret_bytes == raw_secret


def test_parsed_nonzero_cl_padding_is_preserved_when_split() -> None:
    source = parse_codex32(VECTOR_6["codex32_peev"])
    assert isinstance(source, CoreLightningSecret)
    payload = list(source.payload_symbols)
    payload[-1] |= 0xF
    nonzero = complete_checksum("cl10peevs" + _u5_to_chars(tuple(payload)))
    assert isinstance(nonzero, CoreLightningSecret)
    assert _payload_padding(nonzero) == 0xF
    split, shares = split_secret(
        nonzero,
        2,
        indices="ac",
        identifier="name",
    )
    assert split.payload_symbols == nonzero.payload_symbols
    assert recover_secret(shares).payload_symbols == nonzero.payload_symbols


def test_core_lightning_always_requires_an_explicit_identifier() -> None:
    assert (
        inspect.signature(generate_core_lightning_secret)
        .parameters["identifier"]
        .default
        is inspect.Parameter.empty
    )
    source = CoreLightningSecret.from_secret_bytes(bytes(range(32)), identifier="peev")
    with pytest.raises(InvalidIdentifier):
        split_secret(source, 2, indices="ac")


def test_set_header_exclusions_include_threshold_and_identifier() -> None:
    raw_seed = bytes(range(16))
    with pytest.raises(HeaderCollision):
        generate_master_seed(
            raw_seed,
            threshold=2,
            share_count=2,
            identifier="test",
            excluded_headers=("2test",),
        )
    secret, shares = generate_master_seed(
        raw_seed,
        threshold=2,
        share_count=2,
        identifier="test",
        excluded_headers=("3test",),
    )
    assert secret.header.identifier == "test"
    assert len(shares) == 2


def test_split_automatically_excludes_the_source_set_header() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test", threshold=2)
    with pytest.raises(HeaderCollision):
        split_secret(source, 2, indices="ac", identifier="test")
    secret, shares = split_secret(source, 3, indices="acd", identifier="test")
    assert secret.header.threshold == 3
    assert secret.header.identifier == "test"
    assert len(shares) == 3


def test_excluded_headers_are_bounded_and_validated() -> None:
    raw_seed = bytes(range(16))
    for exclusions in ("2test", ("test",), ("1test",), ("2tesi",)):
        with pytest.raises((TypeError, InvalidShareSelection)):
            generate_master_seed(
                raw_seed,
                identifier="name",
                excluded_headers=exclusions,  # type: ignore[arg-type]
            )
    with pytest.raises(InvalidShareSelection):
        generate_master_seed(
            raw_seed,
            identifier="name",
            excluded_headers=tuple("2test" for _ in range(1025)),
        )


def test_default_identifier_collision_changes_only_metadata() -> None:
    basis = (
        parse_codex32(VECTOR_2["share_A"]),
        parse_codex32(VECTOR_2["share_C"]),
    )
    assert all(isinstance(artifact, Share) for artifact in basis)
    replacement = _resolve_default_identifier("test", 2, frozenset({"2test"}))
    assert replacement != "test"
    assert f"2{replacement}" != "2test"
    reheadered = _reheader_basis(basis, 2, replacement)  # type: ignore[arg-type]
    assert tuple(item.payload_symbols for item in reheadered) == tuple(
        item.payload_symbols for item in basis
    )
    assert all(item.header.identifier == replacement for item in reheadered)
    assert all(parse_codex32(item.text) == item for item in reheadered)


def test_public_split_fallback_retains_payload_after_forced_default_collision() -> None:
    seed = bytes.fromhex(VECTOR_1["secret_hex"])
    fingerprint_prefix = _u5_to_chars(_fingerprint_symbols(seed)[:2])
    source_identifier = f"{fingerprint_prefix}qq"
    source = MasterSeed.from_seed(
        seed,
        identifier=source_identifier,
        threshold=2,
    )
    exclusions = tuple(
        f"2{fingerprint_prefix}{first}{second}"
        for first in CHARSET
        for second in CHARSET
    )
    assert len(exclusions) == 1024
    assert f"2{source_identifier}" in exclusions

    split, shares = split_secret(
        source,
        2,
        indices="ac",
        excluded_headers=exclusions,
    )
    assert f"2{split.header.identifier}" not in exclusions
    assert split.payload_symbols == source.payload_symbols
    assert recover_secret(shares).payload_symbols == source.payload_symbols


def test_output_selection_does_not_enter_the_fixed_basis_set_tag() -> None:
    secret = parse_codex32(VECTOR_3["secret_s"])
    basis = tuple(
        parse_codex32(VECTOR_3[name]) for name in ("share_a", "share_c", "derived_d")
    )
    assert isinstance(secret, MasterSeed)
    assert all(isinstance(artifact, Share) for artifact in basis)
    identifier = _legacy_shared_identifier(
        _fingerprint_symbols(secret.seed_bytes),
        basis,  # type: ignore[arg-type]
        3,
    )

    first_secret, first_outputs = _finalize_shared(
        secret,
        basis,  # type: ignore[arg-type]
        3,
        identifier,
        None,
        tuple("def"),
    )
    second_secret, second_outputs = _finalize_shared(
        secret,
        basis,  # type: ignore[arg-type]
        3,
        identifier,
        None,
        tuple("789"),
    )
    assert (
        first_secret.header.identifier == second_secret.header.identifier == identifier
    )
    assert first_secret.payload_symbols == second_secret.payload_symbols
    assert _indices(first_outputs) == "def"
    assert _indices(second_outputs) == "789"


@pytest.mark.parametrize(
    ("vector", "expected"),
    (
        (VECTOR_1, "8u6j"),
        (VECTOR_2, "l2mg"),
        (VECTOR_3, "regv"),
    ),
)
def test_frozen_full_fingerprint_identifiers(
    vector: dict[str, str], expected: str
) -> None:
    fingerprint = _fingerprint_symbols(bytes.fromhex(vector["secret_hex"]))
    assert _full_fingerprint_identifier(fingerprint) == expected


@pytest.mark.parametrize(
    ("vector", "share_names", "expected"),
    (
        (VECTOR_2, ("share_A", "share_C"), "l24s"),
        (VECTOR_3, ("share_a", "share_c", "derived_d"), "re9w"),
    ),
)
def test_frozen_legacy_ten_plus_ten_identifier_serialization(
    vector: dict[str, str], share_names: tuple[str, ...], expected: str
) -> None:
    basis = tuple(parse_codex32(vector[name]) for name in share_names)
    assert all(isinstance(artifact, Share) for artifact in basis)
    expected_serialization = "".join(
        _u5_to_chars(artifact.payload_symbols).lower() for artifact in basis
    ).encode("ascii")
    assert (
        _canonical_payload_serialization(  # type: ignore[arg-type]
            basis, len(basis)
        )
        == expected_serialization
    )
    master_fingerprint = _fingerprint_symbols(bytes.fromhex(vector["secret_hex"]))
    assert (
        _legacy_shared_identifier(  # type: ignore[arg-type]
            master_fingerprint, basis, len(basis)
        )
        == expected
    )


def test_generation_surface_is_exported_without_partial_basis_api() -> None:
    assert codex32.generate_master_seed is generate_master_seed
    assert codex32.generate_core_lightning_secret is generate_core_lightning_secret
    assert codex32.split_secret is split_secret
    assert not hasattr(codex32, "complete_partial_basis")
    assert "basis" not in inspect.signature(generate_master_seed).parameters
    assert "basis" not in inspect.signature(split_secret).parameters
