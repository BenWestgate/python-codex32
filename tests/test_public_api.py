"""Abuse-path tests for the safe public package boundary."""

import ast
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from data.bip93_vectors import VECTOR_2

import codex32
from codex32 import Header, MasterSeed, Share, parse_codex32
from codex32.errors import InvalidIdentifier, InvalidShareIndex, InvalidThreshold


def test_backup_workflows_need_only_the_standard_library() -> None:
    source = """
from codex32 import CreationCeremony, CorrectionContext, Profile, correct, derive_share, parse_codex32, recover_secret

ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
shares = []
for _ in range(2):
    share = ceremony.next_share()
    assert ceremony.confirm(share.text).accepted
    shares.append(share)
secret = ceremony.finish()
assert parse_codex32(secret.text) == secret
assert recover_secret(shares) == secret
assert derive_share(shares, "d").header.index == "d"
damaged = shares[0].text[:-1] + "?"
assert correct(CorrectionContext(Profile.MS), damaged)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-S", "-c", source],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_python_bip32_boundary_stops_at_the_root() -> None:
    module = Path(__file__).parents[1] / "src" / "codex32" / "_bip32.py"
    tree = ast.parse(module.read_text())
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    imports = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
    assert functions == {"_root_material", "_valid_root", "_base58check", "_master_xprv_from_seed"}
    assert imports == {"hashlib", "hmac"}


def test_checksum_completion_is_not_public_api() -> None:
    assert "complete_checksum" not in codex32.__all__
    assert not hasattr(codex32, "complete_checksum")


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
