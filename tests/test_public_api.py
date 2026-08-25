"""Abuse-path tests for the safe public package boundary."""

from dataclasses import FrozenInstanceError
from importlib.metadata import requires
from pathlib import Path

import pytest
from data.bip93_vectors import VECTOR_2

import codex32
from codex32 import Header, MasterSeed, Share, bip93, checksums, parse_codex32
from codex32.errors import InvalidIdentifier, InvalidShareIndex, InvalidThreshold


def test_unsafe_legacy_surface_is_absent() -> None:
    for name in ("Codex32String", "encode", "decode"):
        assert not hasattr(codex32, name)
        assert not hasattr(bip93, name)
    for name in ("crc_pad", "CRC1", "CRC2", "CRC3", "CRC4"):
        assert not hasattr(checksums, name)


def test_root_api_is_deliberately_small() -> None:
    assert len(codex32.__all__) <= 25
    assert set(codex32.__all__) == {
        "Bip39Secret",
        "CodexError",
        "CoreLightningSecret",
        "CorrectionCandidate",
        "CorrectionContext",
        "CorrectionEdit",
        "Header",
        "InvalidCorrectionInput",
        "MasterSeed",
        "Profile",
        "Secret",
        "Share",
        "WorksheetCorrection",
        "complete_checksum",
        "core_descriptors",
        "correct",
        "correct_worksheet_residue",
        "derive_share",
        "generate_master_seed",
        "generate_core_lightning_secret",
        "master_xprv",
        "multisig_account_xpub",
        "parse_codex32",
        "recover_secret",
        "split_secret",
    }


def test_untyped_bip32_import_is_isolated() -> None:
    package = Path(codex32.__file__).parent
    importers = [path.name for path in package.glob("*.py") if "from bip32 import" in path.read_text()]

    assert importers == ["_bip32.py"]


def test_bip32_is_the_only_runtime_dependency() -> None:
    runtime = [requirement for requirement in requires("codex32") or () if "extra ==" not in requirement]

    assert len(runtime) == 1
    assert runtime[0].lower().startswith("bip32")


def test_share_has_symbols_but_no_byte_or_padding_api() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    assert isinstance(share, Share)
    assert isinstance(share.payload_symbols, tuple)
    for name in (
        "data",
        "seed_bytes",
        "secret_bytes",
        "padding",
        "pad_val",
        "from_seed",
    ):
        assert not hasattr(share, name)


def test_artifacts_cannot_be_directly_constructed_or_mutated() -> None:
    with pytest.raises(TypeError):
        Share("ms", Header(2, "test", "a"), (), ())  # type: ignore[arg-type]
    share = parse_codex32(VECTOR_2["share_A"])
    with pytest.raises((FrozenInstanceError, AttributeError)):
        share.text = "changed"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        share.header.identifier = "leak"  # type: ignore[misc]


def test_master_seed_factory_can_only_construct_index_s() -> None:
    secret = MasterSeed.from_seed(bytes(16), identifier="test", threshold=2)
    assert secret.header.index == "s"
    assert secret.seed_bytes == bytes(16)


@pytest.mark.parametrize(
    ("arguments", "error"),
    (
        ((1, "test", "s"), InvalidThreshold),
        ((2, "bad", "a"), InvalidIdentifier),
        ((0, "test", "a"), InvalidShareIndex),
    ),
)
def test_header_invariants(arguments: tuple[object, ...], error: type[Exception]) -> None:
    with pytest.raises(error):
        Header(*arguments)  # type: ignore[arg-type]
