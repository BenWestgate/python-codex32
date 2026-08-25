"""Wallet interoperability is stateless and accepts only validated ms secrets."""

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_5
from data.sharing_vectors import SHARING_VECTORS

from codex32 import (
    MasterSeed,
    core_descriptors,
    master_xprv,
    multisig_account_xpub,
    parse_codex32,
)
from codex32.wallet import _with_checksum


def _master() -> MasterSeed:
    artifact = parse_codex32(VECTOR_1["secret_s"])
    assert isinstance(artifact, MasterSeed)
    return artifact


@pytest.mark.parametrize("vector", (VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_5))
def test_master_xprv_matches_bip93_vectors(vector: dict[str, str]) -> None:
    secret = parse_codex32(vector["secret_s"] if "secret_s" in vector else vector["secret_S"])

    assert isinstance(secret, MasterSeed)
    assert master_xprv(secret) == vector["xprv"]


def test_multisig_xpub_has_bip48_origin_and_frozen_key() -> None:
    assert multisig_account_xpub(_master()) == (
        "[3f3521a6/48h/0h/0h/2h]"
        "xpub6FCn7LwiLh2GPPPV5DgVo4NS2X9rZi2Keo8D7KSciChyAToHBcRLW1kXzG4X"
        "fyYbTNb6VMRDS6r9QaDsdJKH21ADGgy6dvGdE44FZtx2126"
    )
    assert "/48h/1h/7h/2h]tpub" in multisig_account_xpub(_master(), account=7, testnet=True)


def test_public_core_descriptors_are_fixed_and_private_free() -> None:
    records = core_descriptors(_master())

    assert len(records) == 4
    assert [record["desc"].split("(", 1)[0] for record in records] == [
        "pkh",
        "sh",
        "wpkh",
        "tr",
    ]
    assert all(record["active"] is True for record in records)
    assert all(record["timestamp"] == 0 for record in records)
    assert all("xpub" in str(record["desc"]) for record in records)
    assert all("xprv" not in str(record["desc"]) for record in records)
    assert records[0]["desc"] == (
        "pkh([3f3521a6/44h/0h/0h]"
        "xpub6CeZ5XxHp6rXSwi2GCi7UT25rswWQtoPvj36MbzRBr3QEoEmBFNGgnMy329ZMk"
        "fjRKBZHtKKpYfpkrPWohTjHZZn7y1NR9EHnojaGLKdMAR/<0;1>/*)#smv8ra2a"
    )


def test_private_core_descriptors_use_root_xprv_and_explicit_inputs() -> None:
    records = core_descriptors(_master(), account=3, testnet=True, private=True, timestamp=123)

    assert all(record["timestamp"] == 123 for record in records)
    for purpose, record in zip((44, 49, 84, 86), records, strict=True):
        descriptor = str(record["desc"])
        assert "tprv" in descriptor and "tpub" not in descriptor
        assert f"/{purpose}h/1h/3h/<0;1>/*" in descriptor


def test_core_descriptors_accept_bitcoin_core_now_timestamp() -> None:
    assert all(record["timestamp"] == "now" for record in core_descriptors(_master(), timestamp="now"))


def test_descriptor_checksum_matches_published_example() -> None:
    assert _with_checksum("raw(deadbeef)") == "raw(deadbeef)#89f8spxm"


@pytest.mark.parametrize(
    "invalid",
    (
        parse_codex32(SHARING_VECTORS["cl"]["S"]),
        parse_codex32(SHARING_VECTORS["bip39_12w"]["S"]),
        parse_codex32(VECTOR_2["share_A"]),
        b"not an artifact",
    ),
)
def test_wallet_boundary_rejects_every_non_master_seed(invalid: object) -> None:
    for function in (master_xprv, multisig_account_xpub, core_descriptors):
        with pytest.raises(TypeError, match="only MasterSeed"):
            function(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("account", (-1, 2**31, True, "0"))
def test_account_is_explicitly_bounded(account: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        multisig_account_xpub(_master(), account=account)  # type: ignore[arg-type]


@pytest.mark.parametrize("timestamp", (-1, True, "yesterday"))
def test_timestamp_is_a_supported_core_value(timestamp: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        core_descriptors(_master(), timestamp=timestamp)  # type: ignore[arg-type]
