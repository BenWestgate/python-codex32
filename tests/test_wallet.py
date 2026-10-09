"""Wallet interoperability is stateless and accepts only validated ms secrets."""

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_5, VECTOR_6
from data.sharing_vectors import SHARING_VECTORS

from codex32 import MasterSeed, master_xprv, parse_codex32


@pytest.mark.parametrize("vector", (VECTOR_1, VECTOR_2, VECTOR_3, VECTOR_4, VECTOR_5))
def test_master_xprv_matches_bip93_vectors(vector: dict[str, str]) -> None:
    secret = parse_codex32(vector["secret_s"] if "secret_s" in vector else vector["secret_S"])

    assert isinstance(secret, MasterSeed)
    assert master_xprv(secret) == vector["xprv"]


def test_master_xprv_separates_test_network_serialization() -> None:
    secret = parse_codex32(VECTOR_1["secret_s"])
    assert isinstance(secret, MasterSeed)

    assert master_xprv(secret, testnet=True).startswith("tprv")


@pytest.mark.parametrize(
    "invalid",
    (
        parse_codex32(VECTOR_6["codex32_peev"]),
        parse_codex32(SHARING_VECTORS["bip39_12w"]["S"]),
        parse_codex32(VECTOR_2["share_A"]),
        b"not an artifact",
    ),
)
def test_wallet_boundary_rejects_every_non_master_seed(invalid: object) -> None:
    with pytest.raises(TypeError, match="only MasterSeed"):
        master_xprv(invalid)  # type: ignore[arg-type]
