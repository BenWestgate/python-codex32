"""Official BIP93 vectors through the immutable public boundary."""

from dataclasses import FrozenInstanceError

import pytest
from data.bip93_vectors import (
    BAD_CASES,
    BAD_CHECKSUMS,
    INVALID_LENGTHS,
    INVALID_MASTER_SEED,
    INVALID_PREFIX_OR_SEPARATOR,
    INVALID_SHARE_INDEX,
    INVALID_THRESHOLD,
    VECTOR_1,
    VECTOR_2,
    VECTOR_3,
    VECTOR_4,
    VECTOR_5,
    VECTOR_6,
    WRONG_CHECKSUMS,
)

from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Profile,
    Share,
    complete_checksum,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.errors import CodexError, InvalidChecksum


def test_vector_1_parts_and_seed() -> None:
    secret = parse_codex32(VECTOR_1["secret_s"])
    assert isinstance(secret, MasterSeed)
    assert secret.profile is Profile.MS
    assert secret.header.threshold == 0
    assert secret.header.identifier == VECTOR_1["identifier"]
    assert secret.header.index == "s"
    assert secret.seed_bytes.hex() == VECTOR_1["secret_hex"]
    assert secret.text == VECTOR_1["secret_s"]


def test_vector_2_public_api_derives_and_recovers() -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])
    assert isinstance(a, Share) and isinstance(c, Share)
    assert derive_share([a, c], "D").text == VECTOR_2["derived_D"]
    secret = recover_secret([a, c])
    assert isinstance(secret, MasterSeed)
    assert secret.text == VECTOR_2["secret_S"]
    assert secret.seed_bytes.hex() == VECTOR_2["secret_hex"]


def test_vector_3_factory_and_public_derivation() -> None:
    seed = bytes.fromhex(VECTOR_3["secret_hex"])
    secret = MasterSeed.from_seed(seed, identifier="cash", threshold=3)
    assert secret.text == VECTOR_3["secret_s"]
    basis = [
        secret,
        parse_codex32(VECTOR_3["share_a"]),
        parse_codex32(VECTOR_3["share_c"]),
    ]
    for index in "def":
        assert derive_share(basis, index).text == VECTOR_3[f"derived_{index}"]
    for pad_value in range(4):
        alternate = parse_codex32(VECTOR_3[f"secret_s_alternate_{pad_value}"])
        assert isinstance(alternate, MasterSeed)
        assert alternate.seed_bytes == seed


def test_vector_4_all_arbitrary_parsed_padding() -> None:
    seed = bytes.fromhex(VECTOR_4["secret_hex"])
    generated = MasterSeed.from_seed(seed, identifier="leet")
    assert generated.text == VECTOR_4["secret_s_alternate_8"]
    for pad_value in range(16):
        alternate = parse_codex32(VECTOR_4[f"secret_s_alternate_{pad_value}"])
        assert isinstance(alternate, MasterSeed)
        assert alternate.seed_bytes == seed


def test_vector_5_long_uppercase_and_completion() -> None:
    unchecksummed = (
        f"{VECTOR_5['hrp']}1{VECTOR_5['k']}{VECTOR_5['identifier']}"
        f"{VECTOR_5['share_idx']}{VECTOR_5['payload']}"
    )
    secret = complete_checksum(unchecksummed)
    assert isinstance(secret, MasterSeed)
    assert secret.text == VECTOR_5["secret_s"]
    assert secret.seed_bytes.hex() == VECTOR_5["secret_hex"]
    assert parse_codex32(secret.text).text.isupper()


def test_vector_6_core_lightning_examples_are_immutable() -> None:
    luea = parse_codex32(VECTOR_6["codex32_luea"])
    cln2 = parse_codex32(VECTOR_6["codex32_cln2"])
    peev = parse_codex32(VECTOR_6["codex32_peev"])
    assert all(isinstance(value, CoreLightningSecret) for value in (luea, cln2, peev))
    assert luea.secret_bytes.hex() == (
        "6c696768746e696e672d31330000000000000000000000000000000000000000"
    )
    assert peev.secret_bytes.hex() == (
        "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc1"
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        luea._header = cln2.header  # type: ignore[misc]


@pytest.mark.parametrize("value", BAD_CHECKSUMS)
def test_bad_checksums_are_rejected(value: str) -> None:
    with pytest.raises(InvalidChecksum):
        parse_codex32(value)


@pytest.mark.parametrize("value", BAD_CASES)
def test_mixed_case_is_rejected(value: str) -> None:
    with pytest.raises(CodexError):
        parse_codex32(value)


@pytest.mark.parametrize(
    "value",
    [
        *INVALID_MASTER_SEED[1:],
        *WRONG_CHECKSUMS,
        *INVALID_LENGTHS,
        *INVALID_SHARE_INDEX,
        *INVALID_THRESHOLD,
        *INVALID_PREFIX_OR_SEPARATOR,
    ],
)
def test_all_official_invalid_ms_examples_are_rejected(value: str) -> None:
    with pytest.raises(CodexError):
        parse_codex32(value)


def test_registered_profile_reinterprets_official_wrong_application_example() -> None:
    # BIP93 lists this as invalid when an ms decoder was explicitly expected;
    # the fixed registry recognizes that it is instead a valid CL secret.
    assert isinstance(parse_codex32(INVALID_MASTER_SEED[0]), CoreLightningSecret)
