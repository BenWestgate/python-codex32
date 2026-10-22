"""BIP93 recovery and fresh-share derivation through the public API."""

from itertools import combinations, permutations

import pytest
from _codex32_oracle import oracle_encode
from data.bip93_vectors import VECTOR_2, VECTOR_3
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

from codex32 import (
    Codex32String,
    MasterSeed,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import CHARSET
from codex32.bip93 import IDX_SORT, SEED_BYTE_LENGTHS
from codex32.checksums import _Checksum
from codex32.errors import (
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidTargetIndex,
    MismatchedHrp,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedThreshold,
    SecretInRecoverySet,
    WrongShareCount,
)


def _payload_text(artifact: Codex32String) -> str:
    return artifact.payload


def _ms_basis(byte_length: int = 16, threshold: int = 2):
    seed = bytes((position * 37 + byte_length) % 256 for position in range(byte_length))
    secret = MasterSeed.from_seed(seed, identifier="test", threshold=threshold)
    masks = [
        parse_codex32(
            oracle_encode("ms", f"{threshold}test{index}" + CHARSET[offset + 1] * len(secret.payload))
        )
        for offset, index in enumerate(IDX_SORT[1:threshold])
    ]
    assert all(mask.share_idx != "s" for mask in masks)
    return secret, masks


def _ordinary_set(byte_length: int = 16, threshold: int = 2) -> tuple[Codex32String, ...]:
    secret, masks = _ms_basis(byte_length, threshold)
    basis = [secret, *masks]
    fresh = derive_share(basis, IDX_SORT[threshold])
    return (*masks, fresh)


def test_official_vector_2_recovers_derives_and_preserves_uppercase() -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])
    assert a.share_idx != "s" and c.share_idx != "s"
    assert recover_secret([a, c]).s == VECTOR_2["secret_S"]
    assert derive_share([a, c], "D").s == VECTOR_2["derived_D"]
    assert derive_share([c, a], "D").s == VECTOR_2["derived_D"]


def test_official_vector_3_recovers_and_derives() -> None:
    secret = parse_codex32(VECTOR_3["secret_s"])
    a = parse_codex32(VECTOR_3["share_a"])
    c = parse_codex32(VECTOR_3["share_c"])
    d = parse_codex32(VECTOR_3["derived_d"])
    assert all(item.share_idx != "s" for item in (a, c, d))
    assert recover_secret([a, c, d]).s == VECTOR_3["secret_s"]
    for index in "def":
        assert derive_share([secret, a, c], index).s == VECTOR_3[f"derived_{index}"]


def test_interpolation_does_not_create_a_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])

    def fail_create(*_args: object, **_kwargs: object) -> tuple[int, ...]:
        raise AssertionError("sharing must interpolate the existing checksum")

    monkeypatch.setattr(_Checksum, "create", fail_create)
    recovered = recover_secret([a, c])  # type: ignore[list-item]
    derived = derive_share([a, c], "d")  # type: ignore[list-item]
    assert parse_codex32(recovered.s) == recovered
    assert parse_codex32(derived.s) == derived


@pytest.mark.parametrize("threshold", range(2, 10))
def test_every_threshold_recovers_exactly_k_shares(threshold: int) -> None:
    shares = _ordinary_set(threshold=threshold)
    secret = recover_secret(shares)
    assert isinstance(secret, MasterSeed)
    assert secret.data == _ms_basis(threshold=threshold)[0].data
    with pytest.raises(WrongShareCount):
        recover_secret(shares[:-1])
    if threshold < 9:
        extra = derive_share([secret, *shares[:-1]], IDX_SORT[threshold + 1])
        with pytest.raises(WrongShareCount):
            recover_secret([*shares, extra])
    with pytest.raises(WrongShareCount):
        recover_secret(iter(lambda: shares[0], None))  # unbounded input is rejected, not read forever


def test_share_set_mismatches_have_distinct_errors() -> None:
    ms_secret, ms_masks = _ms_basis()
    opaque = parse_codex32(oracle_encode("xy", "2testa" + "q" * len(ms_secret.payload)))
    with pytest.raises(MismatchedHrp):
        derive_share([ms_secret, opaque], "c")  # type: ignore[list-item]

    threshold_three = parse_codex32(oracle_encode("ms", "3testc" + "q" * len(ms_secret.payload)))
    with pytest.raises(MismatchedThreshold):
        derive_share([ms_secret, threshold_three], "d")  # type: ignore[list-item]

    other_id = parse_codex32(oracle_encode("ms", "2namec" + "q" * len(ms_secret.payload)))
    with pytest.raises(MismatchedIdentifier):
        derive_share([ms_secret, other_id], "d")  # type: ignore[list-item]

    longer = MasterSeed.from_seed(bytes(20), identifier="test", threshold=2)
    longer_mask = parse_codex32(oracle_encode("ms", "2testc" + "q" * len(longer.payload)))
    with pytest.raises(MismatchedPayloadLength):
        derive_share([ms_secret, longer_mask], "d")  # type: ignore[list-item]

    with pytest.raises(DuplicateShareIndex):
        recover_secret([ms_masks[0], ms_masks[0]])  # type: ignore[list-item]
    with pytest.raises(SecretInRecoverySet):
        recover_secret([ms_secret, ms_masks[0]])  # type: ignore[list-item]
    with pytest.raises(MismatchedThreshold):
        recover_secret([MasterSeed.from_seed(bytes(16), identifier="test")])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        recover_secret([VECTOR_2["share_A"], VECTOR_2["share_C"]])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        recover_secret(VECTOR_2["share_A"])  # type: ignore[arg-type]


@pytest.mark.parametrize("target", ("s", "i", "b", "?", "aa", "", 3))
def test_invalid_targets_are_rejected(target: object) -> None:
    secret, masks = _ms_basis()
    with pytest.raises(InvalidTargetIndex):
        derive_share([secret, *masks], target)  # type: ignore[arg-type]


def test_existing_targets_are_rejected_case_insensitively() -> None:
    secret, masks = _ms_basis()
    with pytest.raises(ExistingTargetIndex):
        derive_share([secret, *masks], "A")


def test_every_ms_size_recovers_with_short_and_long_checksums() -> None:
    for byte_length in SEED_BYTE_LENGTHS:
        shares = _ordinary_set(byte_length)
        recovered = recover_secret(shares)
        expected = _ms_basis(byte_length)[0]
        assert isinstance(recovered, MasterSeed)
        assert recovered.data == expected.data
        assert len(recovered.payload) == len(expected.payload)


def test_every_ordinary_index_can_be_a_fresh_target() -> None:
    secret = MasterSeed.from_seed(bytes(16), identifier="test", threshold=2)
    ordinary = tuple(character for character in CHARSET if character != "s")
    for target in ordinary:
        mask_index = next(index for index in ordinary if index != target)
        mask = parse_codex32(oracle_encode("ms", f"2test{mask_index}" + "p" * len(secret.payload)))
        derived = derive_share([secret, mask], target)  # type: ignore[list-item]
        assert derived.share_idx == target


@pytest.mark.parametrize("profile", ("bip39_12w", "bip39_24w"))
def test_frozen_profile_sharing_vectors(profile: str) -> None:
    vector = SHARING_VECTORS[profile]
    secret = parse_codex32(vector["S"])
    a = parse_codex32(vector["A"])
    c = parse_codex32(vector["C"])
    assert a.share_idx != "s" and c.share_idx != "s"
    assert recover_secret([a, c]).s == vector["S"]
    assert derive_share([secret, a], "c").s == vector["C"]  # type: ignore[list-item]
    assert derive_share([a, c], "d").s == vector["D"]


@given(st.sampled_from(SEED_BYTE_LENGTHS), st.booleans())
@settings(max_examples=35, deadline=None)
def test_order_and_case_properties(byte_length: int, uppercase: bool) -> None:
    shares = _ordinary_set(byte_length)
    rendered = [parse_codex32(item.s.upper() if uppercase else item.s) for item in shares]
    outputs = [recover_secret(list(order)).s for order in permutations(rendered)]
    assert len(set(outputs)) == 1
    assert outputs[0].isupper() is uppercase


def test_mixed_case_sets_emit_lowercase_and_replacement_preserves_secret() -> None:
    secret, masks = _ms_basis(threshold=3)
    mixed_basis = [parse_codex32(secret.s.upper()), masks[0], masks[1]]
    derived = derive_share(mixed_basis, "d")
    assert derived.s.islower()
    recovered_before = recover_secret([masks[0], masks[1], derived])
    replacement = derive_share([secret, masks[0], derived], "e")
    recovered_after = recover_secret([masks[0], derived, replacement])
    assert recovered_before.s == recovered_after.s == secret.s


def test_any_exact_threshold_subset_recovers_the_same_secret() -> None:
    secret, masks = _ms_basis(threshold=3)
    basis = [secret, *masks]
    ordinary = [*masks, *(derive_share(basis, index) for index in "def")]
    recovered = {recover_secret(list(subset)).s for subset in combinations(ordinary, 3)}
    assert recovered == {secret.s}
