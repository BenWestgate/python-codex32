"""Security invariants for the deliberately small ``ms``/CL generator."""

import inspect
from collections import Counter

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

import codex32
import codex32.generation as generation_module
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
    assert Counter(value & 31 for value in range(256)) == Counter({symbol: 8 for symbol in range(32)})
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
    assert set(inspect.signature(generate_core_lightning_secret).parameters) == {
        "secret_bytes",
        "identifier",
        "threshold",
        "share_count",
        "indices",
    }
    for function in (
        generate_core_lightning_secret,
        generate_master_seed,
        split_secret,
    ):
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


def test_raw_bytes_accept_random_or_explicit_identifiers() -> None:
    raw = bytes(range(16))
    with pytest.raises(InvalidLength):
        generate_master_seed(raw, byte_length=16, identifier="test")
    random_secret, random_shares = generate_master_seed(raw)
    secret, shares = generate_master_seed(raw, identifier="TEST")
    assert random_shares == ()
    assert len(random_secret.header.identifier) == 4
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


def test_oversized_index_strings_are_bounded_before_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_normalization(_value: object) -> str:
        raise AssertionError("oversized selector reached per-index normalization")

    monkeypatch.setattr(generation_module, "_index", unexpected_normalization)
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    operations = (
        lambda: generate_master_seed(
            bytes(range(16)),
            threshold=2,
            indices="a" * 32,
            identifier="test",
        ),
        lambda: generate_core_lightning_secret(
            bytes(range(32)),
            threshold=2,
            indices="a" * 32,
            identifier="test",
        ),
        lambda: split_secret(
            source,
            2,
            indices="a" * 32,
            identifier="name",
        ),
    )

    for operation in operations:
        with pytest.raises(InvalidShareSelection, match="at most 31"):
            operation()


def test_unordered_indices_and_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(TypeError):
        generate_master_seed(
            bytes(range(16)),
            threshold=2,
            indices={"a", "c"},
            identifier="test",  # type: ignore[arg-type]
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
    randomized, _shares = split_secret(secret, 2, indices="ac")
    assert randomized.header.identifier != secret.header.identifier


@pytest.mark.parametrize("threshold", range(2, 10))
def test_core_lightning_generation_and_splitting_target_zero_padding(
    threshold: int,
) -> None:
    fresh, shares = generate_core_lightning_secret(
        identifier="peev", threshold=threshold, indices=ORDINARY_INDICES[:threshold]
    )
    assert isinstance(fresh, CoreLightningSecret)
    assert fresh.payload_symbols[-1] & 15 == 0
    assert _indices(shares) == "".join(ORDINARY_INDICES[:threshold])
    assert recover_secret(shares) == fresh

    if threshold != 2:
        return
    raw = bytes(range(32))
    encoded, encoded_shares = generate_core_lightning_secret(
        raw, identifier="name", threshold=3, indices="7cad"
    )
    assert encoded.secret_bytes == raw
    assert encoded.payload_symbols[-1] & 15 == 0
    assert recover_secret(encoded_shares[:3]) == encoded

    split, split_shares = split_secret(encoded, 2, indices="ac", identifier="test")
    assert split.payload_symbols == encoded.payload_symbols
    assert recover_secret(split_shares).secret_bytes == raw


def test_split_preserves_nonzero_core_lightning_padding() -> None:
    source = parse_codex32(VECTOR_6["codex32_peev"])
    assert isinstance(source, CoreLightningSecret)
    payload = (*source.payload_symbols[:-1], source.payload_symbols[-1] | 15)
    nonzero = complete_checksum("cl10peevs" + _u5_to_chars(payload))
    assert isinstance(nonzero, CoreLightningSecret)
    secret, shares = split_secret(nonzero, 2, indices="ac", identifier="name")
    assert secret.payload_symbols == nonzero.payload_symbols
    assert recover_secret(shares).payload_symbols == nonzero.payload_symbols


def test_core_lightning_generation_validates_size_and_identifier() -> None:
    for value in (b"x" * 31, b"x" * 33):
        with pytest.raises(InvalidLength):
            generate_core_lightning_secret(value, identifier="test")
    with pytest.raises(TypeError):
        generate_core_lightning_secret("x" * 32, identifier="test")  # type: ignore[arg-type]
    generated, shares = generate_core_lightning_secret()
    assert shares == () and len(generated.header.identifier) == 4
    with pytest.raises(InvalidIdentifier):
        generate_core_lightning_secret(identifier="bad")


def test_split_rejects_non_secret_artifacts() -> None:
    artifacts = (
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
def test_unshared_fingerprint_identifier_vectors(vector: dict[str, str], expected: str) -> None:
    assert _fingerprint_identifier(bytes.fromhex(vector["secret_hex"])) == expected


def test_generation_surface_has_no_partial_basis() -> None:
    assert codex32.generate_master_seed is generate_master_seed
    assert codex32.generate_core_lightning_secret is generate_core_lightning_secret
    assert codex32.split_secret is split_secret
    assert not hasattr(codex32, "complete_partial_basis")
    assert "basis" not in inspect.signature(generate_master_seed).parameters
