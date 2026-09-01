"""Security invariants for incremental ``ms`` and CL creation ceremonies."""

import copy
import inspect
import pickle
from collections import Counter
from itertools import combinations

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

import codex32
import codex32.generation as generation_module
from codex32 import (
    CoreLightningSecret,
    CreationCeremony,
    MasterSeed,
    Share,
    complete_checksum,
    generate_core_lightning_secret,
    generate_master_seed,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import CHARSET, _u5_to_chars
from codex32.bip93 import IDX_SORT
from codex32.errors import (
    CeremonyStateError,
    CodexError,
    HeaderCollision,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareSelection,
    InvalidThreshold,
)
from codex32.generation import ORDINARY_INDICES, _fingerprint_identifier
from codex32.profiles.ms32 import SEED_BYTE_LENGTHS, _has_generation_padding


def _complete(ceremony: CreationCeremony) -> tuple[MasterSeed | CoreLightningSecret, tuple[Share, ...]]:
    shares = []
    while True:
        try:
            share = ceremony.next_share()
        except CeremonyStateError as error:
            assert "all cards are confirmed" in str(error)
            break
        shares.append(share)
        assert ceremony.confirm(share.text.upper()).accepted
    return ceremony.finish(), tuple(shares)


def _indices(shares: tuple[Share, ...]) -> str:
    return "".join(share.header.index for share in shares)


def _seed(byte_length: int) -> bytes:
    return bytes((position * 109 + byte_length) % 256 for position in range(byte_length))


def test_entropy_mapping_and_index_population_are_exact() -> None:
    assert Counter(value & 31 for value in range(256)) == Counter({symbol: 8 for symbol in range(32)})
    assert ORDINARY_INDICES == tuple(IDX_SORT[1:])
    assert len(set(ORDINARY_INDICES)) == 31
    assert set(ORDINARY_INDICES) == set(CHARSET) - {"s"}


def test_public_signatures_expose_only_unshared_one_shot_generation() -> None:
    assert set(inspect.signature(generate_master_seed).parameters) == {
        "seed_bytes",
        "byte_length",
        "identifier",
    }
    assert set(inspect.signature(generate_core_lightning_secret).parameters) == {
        "secret_bytes",
        "identifier",
    }
    assert not hasattr(codex32, "split_secret")
    for function in (generate_core_lightning_secret, generate_master_seed):
        assert set(inspect.signature(function).parameters).isdisjoint(
            {"rng", "entropy", "padding", "threshold", "share_count", "indices"}
        )


def test_fresh_unshared_ms_supports_every_bip93_size() -> None:
    for byte_length in SEED_BYTE_LENGTHS:
        secret = generate_master_seed(byte_length=byte_length)
        assert len(secret.seed_bytes) == byte_length
        assert secret.header.threshold == 0
        assert secret.header.identifier == _fingerprint_identifier(secret.seed_bytes)
        assert _has_generation_padding(secret)


def test_fresh_shared_ms_supports_every_bip93_size() -> None:
    for byte_length in SEED_BYTE_LENGTHS:
        secret, shares = _complete(
            CreationCeremony.master_seed(
                byte_length=byte_length, threshold=2, indices="ac", identifier="test"
            )
        )
        assert _indices(shares) == "ac"
        assert isinstance(secret, MasterSeed) and _has_generation_padding(secret)
        assert recover_secret(shares) == secret


@pytest.mark.parametrize("threshold", range(2, 10))
def test_fresh_generation_recovers_at_every_threshold(threshold: int) -> None:
    secret, shares = _complete(CreationCeremony.master_seed(threshold=threshold, share_count=threshold))
    assert len({share.header.index for share in shares}) == threshold
    assert recover_secret(shares) == secret


@pytest.mark.parametrize("threshold", range(2, 10))
@pytest.mark.parametrize("kind", (16, 32, "cl"))
def test_every_generated_threshold_subset_recovers(threshold: int, kind: int | str) -> None:
    ceremony = (
        CreationCeremony.core_lightning(threshold=threshold, share_count=threshold + 2)
        if kind == "cl"
        else CreationCeremony.master_seed(
            byte_length=kind,
            threshold=threshold,
            share_count=threshold + 2,  # type: ignore[arg-type]
        )
    )
    secret, shares = _complete(ceremony)

    assert {recover_secret(subset).text for subset in combinations(shares, threshold)} == {secret.text}


@given(
    byte_length=st.sampled_from(SEED_BYTE_LENGTHS),
    threshold=st.integers(min_value=2, max_value=9),
)
@settings(max_examples=20, deadline=None)
def test_supplied_seed_round_trip(byte_length: int, threshold: int) -> None:
    source = generate_master_seed(_seed(byte_length), identifier="test")
    secret, shares = _complete(
        CreationCeremony.from_secret(
            source, threshold=threshold, indices=ORDINARY_INDICES[:threshold], identifier="name"
        )
    )
    assert isinstance(secret, MasterSeed) and secret.seed_bytes == _seed(byte_length)
    assert recover_secret(shares) == secret


def test_every_other_16_through_64_byte_generation_size_is_rejected() -> None:
    for byte_length in set(range(16, 65)) - set(SEED_BYTE_LENGTHS):
        with pytest.raises(InvalidLength):
            generate_master_seed(_seed(byte_length))
        with pytest.raises(InvalidLength):
            generate_master_seed(byte_length=byte_length)
        with pytest.raises(InvalidLength):
            CreationCeremony.master_seed(threshold=2, indices="ac", byte_length=byte_length)


def test_raw_bytes_accept_random_or_explicit_identifiers() -> None:
    raw = bytes(range(16))
    with pytest.raises(InvalidLength):
        generate_master_seed(raw, byte_length=16, identifier="test")
    random_secret = generate_master_seed(raw)
    secret = generate_master_seed(raw, identifier="TEST")
    assert len(random_secret.header.identifier) == 4
    assert secret.header.identifier == "test"


def test_explicit_and_random_output_order_contracts() -> None:
    source = generate_master_seed(bytes(range(16)), identifier="test")
    _secret, shares = _complete(
        CreationCeremony.from_secret(source, threshold=3, indices="7CaD", identifier="name")
    )
    assert _indices(shares) == "7cad"

    _secret, all_shares = _complete(
        CreationCeremony.from_secret(source, threshold=2, share_count=31, identifier="cash")
    )
    assert len(set(_indices(all_shares))) == 31
    assert set(_indices(all_shares)) == set(ORDINARY_INDICES)


@pytest.mark.parametrize(
    "arguments",
    (
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
        CreationCeremony.master_seed(identifier="test", **arguments)  # type: ignore[arg-type]


def test_oversized_index_strings_are_bounded_before_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_normalization(_value: object) -> str:
        raise AssertionError("oversized selector reached per-index normalization")

    monkeypatch.setattr(generation_module, "_index", unexpected_normalization)
    source = generate_master_seed(bytes(range(16)), identifier="test")
    operations = (
        lambda: CreationCeremony.master_seed(threshold=2, indices="a" * 32, identifier="test"),
        lambda: CreationCeremony.core_lightning(threshold=2, indices="a" * 32, identifier="test"),
        lambda: CreationCeremony.from_secret(source, threshold=2, indices="a" * 32, identifier="name"),
    )
    for operation in operations:
        with pytest.raises(InvalidShareSelection, match="at most 31"):
            operation()


def test_unordered_indices_and_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(TypeError):
        CreationCeremony.master_seed(
            threshold=2,
            indices={"a", "c"},
            identifier="test",  # type: ignore[arg-type]
        )
    for threshold in (0, 1, 10, True, "2"):
        with pytest.raises(InvalidThreshold):
            CreationCeremony.master_seed(
                threshold=threshold,
                share_count=2,
                identifier="test",  # type: ignore[arg-type]
            )


def test_confirmation_gates_each_entropy_draw_and_reports_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    original = generation_module.secrets.token_bytes

    def recorded(length: int) -> bytes:
        calls.append(length)
        return original(length)

    monkeypatch.setattr(generation_module.secrets, "token_bytes", recorded)
    ceremony = CreationCeremony.master_seed(threshold=2, indices="acd", identifier="test")
    assert calls == []
    first = ceremony.next_share()
    assert calls == [26]
    with pytest.raises(CeremonyStateError, match="pending"):
        ceremony.next_share()
    damaged = first.text[:4] + ("q" if first.text[4] != "q" else "p") + first.text[5:]
    result = ceremony.confirm(damaged)
    assert not result.accepted and result.mismatched_groups == (2,)
    assert calls == [26]
    assert ceremony.confirm(" \n".join(first.text.upper())).accepted
    second = ceremony.next_share()
    assert len(calls) >= 2 and all(length == 26 for length in calls)
    assert ceremony.confirm(second.text).accepted
    calls_after_basis = len(calls)
    derived = ceremony.next_share()
    assert len(calls) == calls_after_basis
    assert ceremony.confirm(derived.text).accepted
    ceremony.finish()


def test_final_share_rejection_retains_confirmed_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
    first = ceremony.next_share()
    assert ceremony.confirm(first.text).accepted
    original = ceremony._candidate_is_accepted
    checks = 0

    def reject_once(_self: CreationCeremony, secret: object) -> bool:
        nonlocal checks
        checks += 1
        return checks > 1 and original(secret)  # type: ignore[arg-type]

    monkeypatch.setattr(
        CreationCeremony,
        "_candidate_is_accepted",
        reject_once,
    )
    calls = 0
    original_random = generation_module._random_share

    def recorded(*args: object, **kwargs: object) -> Share:
        nonlocal calls
        calls += 1
        return original_random(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(generation_module, "_random_share", recorded)
    second = ceremony.next_share()
    assert calls >= 2
    assert ceremony.confirm(second.text).accepted
    secret = ceremony.finish()
    assert recover_secret((first, second)) == secret


def test_final_ms_share_retries_a_bip32_invalid_root(monkeypatch: pytest.MonkeyPatch) -> None:
    ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
    first = ceremony.next_share()
    assert ceremony.confirm(first.text).accepted
    original = generation_module._fingerprint_from_seed
    checks = 0

    def reject_once(seed: bytes) -> bytes:
        nonlocal checks
        checks += 1
        if checks == 1:
            raise CodexError("synthetic invalid BIP32 root")
        return original(seed)

    monkeypatch.setattr(generation_module, "_fingerprint_from_seed", reject_once)
    second = ceremony.next_share()
    assert checks >= 2 and ceremony.confirm(second.text).accepted
    assert recover_secret((first, second)) == ceremony.finish()


def test_ceremony_state_is_fail_closed() -> None:
    ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
    with pytest.raises(CeremonyStateError):
        ceremony.confirm("anything")
    with pytest.raises(CeremonyStateError):
        ceremony.finish()
    shares = []
    for _ in range(2):
        shares.append(ceremony.next_share())
        assert ceremony.confirm(shares[-1].text).accepted
    secret = ceremony.finish()
    assert recover_secret(shares) == secret
    assert ceremony._basis == [] and ceremony._indices == () and ceremony._secret is None
    with pytest.raises(CeremonyStateError):
        ceremony.next_share()
    with pytest.raises(CeremonyStateError):
        ceremony.finish()


def test_ceremony_cannot_be_copied_or_serialized() -> None:
    ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
    pending = ceremony.next_share()
    assert ceremony.confirm(pending.text).accepted

    for operation in (
        lambda: copy.copy(ceremony),
        lambda: copy.deepcopy(ceremony),
        lambda: pickle.dumps(ceremony),
    ):
        with pytest.raises(TypeError, match="cannot be copied or serialized"):
            operation()


def test_resharing_preserves_padding_and_requires_a_new_header() -> None:
    source = parse_codex32(VECTOR_4["secret_s_alternate_0"])
    assert isinstance(source, MasterSeed)
    secret, shares = _complete(
        CreationCeremony.from_secret(source, threshold=2, indices="ac", identifier="name")
    )
    assert secret.payload_symbols == source.payload_symbols
    assert recover_secret(shares).payload_symbols == source.payload_symbols
    with pytest.raises(HeaderCollision):
        CreationCeremony.from_secret(secret, threshold=2, indices="ac", identifier="name")
    randomized = CreationCeremony.from_secret(secret, threshold=2, indices="ac")
    assert randomized.next_share().header.identifier != secret.header.identifier


@pytest.mark.parametrize("threshold", range(2, 10))
def test_core_lightning_generation_and_splitting_target_zero_padding(threshold: int) -> None:
    fresh, shares = _complete(
        CreationCeremony.core_lightning(
            identifier="peev", threshold=threshold, indices=ORDINARY_INDICES[:threshold]
        )
    )
    assert isinstance(fresh, CoreLightningSecret)
    assert fresh.payload_symbols[-1] & 15 == 0
    assert recover_secret(shares) == fresh

    if threshold == 2:
        raw = generate_core_lightning_secret(bytes(range(32)), identifier="name")
        split, split_shares = _complete(
            CreationCeremony.from_secret(raw, threshold=2, indices="ac", identifier="test")
        )
        assert split.payload_symbols == raw.payload_symbols
        assert recover_secret(split_shares).secret_bytes == bytes(range(32))


def test_resharing_preserves_nonzero_core_lightning_padding() -> None:
    source = parse_codex32(VECTOR_6["codex32_peev"])
    assert isinstance(source, CoreLightningSecret)
    payload = (*source.payload_symbols[:-1], source.payload_symbols[-1] | 15)
    nonzero = complete_checksum("cl10peevs" + _u5_to_chars(payload))
    assert isinstance(nonzero, CoreLightningSecret)
    secret, shares = _complete(
        CreationCeremony.from_secret(nonzero, threshold=2, indices="ac", identifier="name")
    )
    assert secret.payload_symbols == nonzero.payload_symbols
    assert recover_secret(shares).payload_symbols == nonzero.payload_symbols


def test_core_lightning_generation_validates_size_and_identifier() -> None:
    for value in (b"x" * 31, b"x" * 33):
        with pytest.raises(InvalidLength):
            generate_core_lightning_secret(value, identifier="test")
    with pytest.raises(TypeError):
        generate_core_lightning_secret("x" * 32, identifier="test")  # type: ignore[arg-type]
    assert len(generate_core_lightning_secret().header.identifier) == 4
    with pytest.raises(InvalidIdentifier):
        generate_core_lightning_secret(identifier="bad")


def test_from_secret_rejects_non_secret_artifacts() -> None:
    artifacts = (
        parse_codex32(SHARING_VECTORS["bip39_12w"]["S"]),
        parse_codex32(VECTOR_2["share_A"]),
        VECTOR_2["secret_S"],
    )
    for artifact in artifacts:
        with pytest.raises(TypeError):
            CreationCeremony.from_secret(
                artifact,
                threshold=2,
                indices="ac",
                identifier="test",  # type: ignore[arg-type]
            )


@pytest.mark.parametrize(
    ("vector", "expected"),
    ((VECTOR_1, "8u6j"), (VECTOR_2, "l2mg"), (VECTOR_3, "regv")),
)
def test_unshared_fingerprint_identifier_vectors(vector: dict[str, str], expected: str) -> None:
    assert _fingerprint_identifier(bytes.fromhex(vector["secret_hex"])) == expected


def test_generation_surface_has_no_partial_basis_or_one_shot_sharing() -> None:
    assert codex32.CreationCeremony is CreationCeremony
    assert codex32.generate_master_seed is generate_master_seed
    assert codex32.generate_core_lightning_secret is generate_core_lightning_secret
    for name in ("split_secret", "complete_partial_basis"):
        assert not hasattr(codex32, name)
