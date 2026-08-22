"""BIP93 recovery and fresh-share derivation through the public API."""

from itertools import combinations, permutations

import pytest
from data.bip93_vectors import VECTOR_2, VECTOR_3
from data.sharing_vectors import INVALID_BIP39_IMPLIED_SECRET, SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st

from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Share,
    complete_checksum,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import CHARSET, _u5_to_chars
from codex32.bip93 import IDX_SORT
from codex32.checksums import _Checksum
from codex32.errors import (
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidBip39Checksum,
    InvalidPadding,
    InvalidTargetIndex,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    SecretInRecoverySet,
    WrongShareCount,
)


def _payload_text(artifact: Share | MasterSeed | CoreLightningSecret) -> str:
    return _u5_to_chars(artifact.payload_symbols)


def _ms_basis(byte_length: int = 16, threshold: int = 2):
    seed = bytes((position * 37 + byte_length) % 256 for position in range(byte_length))
    secret = MasterSeed.from_seed(seed, identifier="test", threshold=threshold)
    masks = [
        complete_checksum(
            f"ms1{threshold}test{index}"
            + CHARSET[offset + 1] * len(secret.payload_symbols)
        )
        for offset, index in enumerate(IDX_SORT[1:threshold])
    ]
    assert all(isinstance(mask, Share) for mask in masks)
    return secret, masks


def _ordinary_set(byte_length: int = 16, threshold: int = 2) -> tuple[Share, ...]:
    secret, masks = _ms_basis(byte_length, threshold)
    basis = [secret, *masks]
    fresh = derive_share(basis, IDX_SORT[threshold])
    return (*masks, fresh)


def test_official_vector_2_recovers_derives_and_preserves_uppercase() -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])
    assert isinstance(a, Share) and isinstance(c, Share)
    assert recover_secret([a, c]).text == VECTOR_2["secret_S"]
    assert derive_share([a, c], "D").text == VECTOR_2["derived_D"]
    assert derive_share([c, a], "D").text == VECTOR_2["derived_D"]


def test_official_vector_3_recovers_and_derives() -> None:
    secret = parse_codex32(VECTOR_3["secret_s"])
    a = parse_codex32(VECTOR_3["share_a"])
    c = parse_codex32(VECTOR_3["share_c"])
    d = parse_codex32(VECTOR_3["derived_d"])
    assert all(isinstance(item, Share) for item in (a, c, d))
    assert recover_secret([a, c, d]).text == VECTOR_3["secret_s"]
    for index in "def":
        assert derive_share([secret, a, c], index).text == VECTOR_3[f"derived_{index}"]


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
    assert parse_codex32(recovered.text) == recovered
    assert parse_codex32(derived.text) == derived


@pytest.mark.parametrize("threshold", range(2, 10))
def test_every_threshold_recovers_exactly_k_shares(threshold: int) -> None:
    shares = _ordinary_set(threshold=threshold)
    secret = recover_secret(shares)
    assert isinstance(secret, MasterSeed)
    assert secret.seed_bytes == _ms_basis(threshold=threshold)[0].seed_bytes
    with pytest.raises(WrongShareCount):
        recover_secret(shares[:-1])
    if threshold < 9:
        extra = derive_share([secret, *shares[:-1]], IDX_SORT[threshold + 1])
        with pytest.raises(WrongShareCount):
            recover_secret([*shares, extra])


def test_share_set_mismatches_have_distinct_errors() -> None:
    ms_secret, ms_masks = _ms_basis()
    cl = complete_checksum("cl12testa" + "q" * 52)
    with pytest.raises(MismatchedProfile):
        derive_share([ms_secret, cl], "c")  # type: ignore[list-item]

    threshold_three = complete_checksum(
        "ms13testc" + "q" * len(ms_secret.payload_symbols)
    )
    with pytest.raises(MismatchedThreshold):
        derive_share([ms_secret, threshold_three], "d")  # type: ignore[list-item]

    other_id = complete_checksum("ms12namec" + "q" * len(ms_secret.payload_symbols))
    with pytest.raises(MismatchedIdentifier):
        derive_share([ms_secret, other_id], "d")  # type: ignore[list-item]

    longer = MasterSeed.from_seed(bytes(17), identifier="test", threshold=2)
    longer_mask = complete_checksum("ms12testc" + "q" * len(longer.payload_symbols))
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


def test_oversized_sequence_is_rejected_before_items_are_read() -> None:
    class OversizedSequence:
        def __len__(self) -> int:
            return 10

        def __getitem__(self, _position: int) -> Share:
            raise AssertionError("oversized input must not be materialized")

    with pytest.raises(WrongShareCount):
        recover_secret(OversizedSequence())  # type: ignore[arg-type]


@pytest.mark.parametrize("target", ("s", "i", "b", "?", "aa", "", 3))
def test_invalid_targets_are_rejected(target: object) -> None:
    secret, masks = _ms_basis()
    with pytest.raises(InvalidTargetIndex):
        derive_share([secret, *masks], target)  # type: ignore[arg-type]


def test_existing_targets_are_rejected_case_insensitively() -> None:
    secret, masks = _ms_basis()
    with pytest.raises(ExistingTargetIndex):
        derive_share([secret, *masks], "A")


def test_every_ms_length_recovers_with_short_and_long_checksums() -> None:
    for byte_length in range(16, 65):
        shares = _ordinary_set(byte_length)
        recovered = recover_secret(shares)
        expected = _ms_basis(byte_length)[0]
        assert isinstance(recovered, MasterSeed)
        assert recovered.seed_bytes == expected.seed_bytes
        assert len(recovered.payload_symbols) == len(expected.payload_symbols)


def test_every_ordinary_index_can_be_a_fresh_target() -> None:
    secret = MasterSeed.from_seed(bytes(16), identifier="test", threshold=2)
    ordinary = tuple(character for character in CHARSET if character != "s")
    for target in ordinary:
        mask_index = next(index for index in ordinary if index != target)
        mask = complete_checksum(
            f"ms12test{mask_index}" + "p" * len(secret.payload_symbols)
        )
        derived = derive_share([secret, mask], target)  # type: ignore[list-item]
        assert derived.header.index == target


@pytest.mark.parametrize("profile", ("cl", "bip39_12w", "bip39_24w"))
def test_frozen_profile_sharing_vectors(profile: str) -> None:
    vector = SHARING_VECTORS[profile]
    secret = parse_codex32(vector["S"])
    a = parse_codex32(vector["A"])
    c = parse_codex32(vector["C"])
    assert isinstance(a, Share) and isinstance(c, Share)
    assert recover_secret([a, c]).text == vector["S"]
    assert derive_share([secret, a], "c").text == vector["C"]  # type: ignore[list-item]
    assert derive_share([a, c], "d").text == vector["D"]


def test_invalid_implied_bip39_secret_rejects_recovery_and_derivation() -> None:
    a = parse_codex32(INVALID_BIP39_IMPLIED_SECRET["A"])
    c = parse_codex32(INVALID_BIP39_IMPLIED_SECRET["C"])
    assert isinstance(a, Share) and isinstance(c, Share)
    for operation in (
        lambda: recover_secret([a, c]),
        lambda: derive_share([a, c], "d"),
    ):
        with pytest.raises((InvalidPadding, InvalidBip39Checksum)):
            operation()


@given(st.integers(min_value=16, max_value=64), st.booleans())
@settings(max_examples=35, deadline=None)
def test_order_and_case_properties(byte_length: int, uppercase: bool) -> None:
    shares = _ordinary_set(byte_length)
    rendered = [
        parse_codex32(item.text.upper() if uppercase else item.text) for item in shares
    ]
    outputs = [recover_secret(list(order)).text for order in permutations(rendered)]
    assert len(set(outputs)) == 1
    assert outputs[0].isupper() is uppercase


def test_mixed_case_sets_emit_lowercase_and_replacement_preserves_secret() -> None:
    secret, masks = _ms_basis(threshold=3)
    mixed_basis = [parse_codex32(secret.text.upper()), masks[0], masks[1]]
    derived = derive_share(mixed_basis, "d")
    assert derived.text.islower()
    recovered_before = recover_secret([masks[0], masks[1], derived])
    replacement = derive_share([secret, masks[0], derived], "e")
    recovered_after = recover_secret([masks[0], derived, replacement])
    assert recovered_before.text == recovered_after.text == secret.text


def test_any_exact_threshold_subset_recovers_the_same_secret() -> None:
    secret, masks = _ms_basis(threshold=3)
    basis = [secret, *masks]
    ordinary = [*masks, *(derive_share(basis, index) for index in "def")]
    recovered = {
        recover_secret(list(subset)).text for subset in combinations(ordinary, 3)
    }
    assert recovered == {secret.text}


def test_gate_2_public_surface_replaces_the_private_bridge() -> None:
    import codex32
    from codex32 import bip93

    assert codex32.recover_secret is recover_secret
    assert codex32.derive_share is derive_share
    assert not hasattr(bip93, "_interpolate_at")
    for old_error in (
        "MismatchedLength",
        "MismatchedHrp",
        "MismatchedId",
        "RepeatedIndex",
        "ThresholdNotPassed",
    ):
        assert not hasattr(bip93, old_error)
    share = parse_codex32(VECTOR_2["share_A"])
    assert isinstance(share, Share)
    assert not hasattr(share, "seed_bytes")
