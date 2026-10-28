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
    Codex32String,
    MasterSeed,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.bech32 import _chars_to_u5, convertbits
from codex32.errors import CodexError, InvalidChecksum


def test_vector_1_parts_and_seed() -> None:
    secret = parse_codex32(VECTOR_1["secret_s"])
    assert isinstance(secret, MasterSeed)
    assert secret.k == "0"
    assert secret.ident == VECTOR_1["identifier"]
    assert secret.share_idx == "s"
    assert secret.data.hex() == VECTOR_1["secret_hex"]
    assert secret.s == VECTOR_1["secret_s"]


def test_vector_2_public_api_derives_and_recovers() -> None:
    a = parse_codex32(VECTOR_2["share_A"])
    c = parse_codex32(VECTOR_2["share_C"])
    assert a.share_idx != "s" and c.share_idx != "s"
    assert derive_share([a, c], "D").s == VECTOR_2["derived_D"]
    secret = recover_secret([a, c])
    assert isinstance(secret, MasterSeed)
    assert secret.s == VECTOR_2["secret_S"]
    assert secret.data.hex() == VECTOR_2["secret_hex"]


def test_vector_3_factory_and_public_derivation() -> None:
    seed = bytes.fromhex(VECTOR_3["secret_hex"])
    secret = MasterSeed.from_seed(seed, identifier="cash", threshold=3)
    assert secret.s == VECTOR_3["secret_s"]
    basis = [
        secret,
        parse_codex32(VECTOR_3["share_a"]),
        parse_codex32(VECTOR_3["share_c"]),
    ]
    for index in "def":
        assert derive_share(basis, index).s == VECTOR_3[f"derived_{index}"]
    for pad_value in range(4):
        alternate = parse_codex32(VECTOR_3[f"secret_s_alternate_{pad_value}"])
        assert isinstance(alternate, MasterSeed)
        assert alternate.data == seed


def test_vector_4_all_arbitrary_parsed_padding() -> None:
    seed = bytes.fromhex(VECTOR_4["secret_hex"])
    generated = MasterSeed.from_seed(seed, identifier="leet")
    assert generated.s == VECTOR_4["secret_s_alternate_8"]
    for pad_value in range(16):
        alternate = parse_codex32(VECTOR_4[f"secret_s_alternate_{pad_value}"])
        assert isinstance(alternate, MasterSeed)
        assert alternate.data == seed


def test_vector_5_long_uppercase_and_completion() -> None:
    secret = parse_codex32(VECTOR_5["secret_s"])
    assert isinstance(secret, MasterSeed)
    assert secret.s == VECTOR_5["secret_s"]
    assert secret.data.hex() == VECTOR_5["secret_hex"]
    assert parse_codex32(secret.s).s.isupper()


def test_vector_6_core_lightning_examples_are_generic_immutable_secrets() -> None:
    luea = parse_codex32(VECTOR_6["codex32_luea"])
    cln2 = parse_codex32(VECTOR_6["codex32_cln2"])
    peev = parse_codex32(VECTOR_6["codex32_peev"])
    for value in (luea, cln2, peev):
        assert type(value) is Codex32String and value.hrp == "cl"

    def payload(secret: Codex32String) -> str:
        return bytes(
            convertbits(_chars_to_u5(secret.payload), 5, 8, pad=False, accept_any_padding=True)
        ).hex()

    assert payload(luea) == "6c696768746e696e672d31330000000000000000000000000000000000000000"
    assert payload(peev) == "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc1"
    with pytest.raises(FrozenInstanceError):
        luea.s = cln2.s  # type: ignore[misc]
    assert luea.ident == "luea"


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
        *INVALID_PREFIX_OR_SEPARATOR[:-2],
    ],
)
def test_all_official_invalid_ms_examples_are_rejected(value: str) -> None:
    with pytest.raises(CodexError):
        parse_codex32(value)


def test_official_wrong_application_example_is_a_generic_secret() -> None:
    # BIP93 lists this as invalid when an ms decoder was explicitly expected;
    # without an ms prefix it is an ordinary codex32 secret.
    artifact = parse_codex32(INVALID_MASTER_SEED[0])
    assert type(artifact) is Codex32String and artifact.hrp != "ms"


@pytest.mark.parametrize("value", INVALID_PREFIX_OR_SEPARATOR[-2:])
def test_generic_parser_accepts_checksum_valid_non_ms_hrps(value: str) -> None:
    artifact = parse_codex32(value)
    assert artifact.hrp in {"m", "s"}
    assert not isinstance(artifact, MasterSeed)
