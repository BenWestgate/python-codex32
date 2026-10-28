"""Abuse-path tests for the safe public package boundary."""

import ast
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2

import codex32
from codex32 import (
    Codex32String,
    CorrectionCandidate,
    CorrectionContext,
    MasterSeed,
    correct,
    correct_worksheet_residue,
    parse_codex32,
)
from codex32.bip93 import _header
from codex32.errors import CodexError, InvalidIdentifier, InvalidShareIndex, InvalidThreshold


def test_backup_workflows_need_only_the_standard_library() -> None:
    source = """
from codex32 import CreationCeremony, CorrectionContext, correct, derive_share, parse_codex32, recover_secret

ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
shares = []
for _ in range(2):
    share = ceremony.next_share()
    assert ceremony.confirm(share.s).accepted
    shares.append(share)
secret = ceremony.finish()
assert parse_codex32(secret.s) == secret
assert recover_secret(shares) == secret
assert derive_share(shares, "d").share_idx == "d"
damaged = shares[0].s[:-1] + "?"
assert correct(CorrectionContext("ms"), damaged)
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
    assert share.share_idx != "s"
    assert isinstance(share.payload, str)
    for name in (
        "data",
        "seed_bytes",
        "secret_bytes",
        "padding",
        "pad_val",
        "from_seed",
    ):
        assert not hasattr(share, name)


def test_artifacts_are_validated_strings_and_cannot_be_mutated() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    secret = parse_codex32(VECTOR_1["secret_s"])
    assert Codex32String(share.s) == share and MasterSeed(secret.s) == secret
    with pytest.raises(TypeError):
        MasterSeed(share.s)
    with pytest.raises(CodexError):
        MasterSeed(secret.s[:-1] + ("q" if secret.s[-1] != "q" else "p"))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        share.s = "changed"  # type: ignore[misc]
    # Before Python 3.13, slotted frozen dataclasses raise TypeError for non-field names.
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        share.ident = "leak"  # type: ignore[misc]
    assert share.ident == "name"


def test_artifact_default_rendering_does_not_disclose_recovery_text() -> None:
    share = parse_codex32(VECTOR_2["share_A"])
    candidate = CorrectionCandidate(share, (), 1, 0, 0, None)

    assert share.s not in str(share)
    assert share.s not in repr(share)
    assert share.s not in repr(candidate)
    assert str(share) == "<Codex32String: redacted>"
    assert repr(share) == "Codex32String(<redacted>)"


def test_correction_edits_do_not_render_recovery_characters() -> None:
    text = VECTOR_2["share_A"]
    candidate = correct(CorrectionContext("ms"), text[:9] + "?" * 8 + text[17:])[0]
    rendered = repr(candidate)

    assert len(candidate.edits) == 8
    assert text[9:17].lower() not in rendered.lower()
    assert all(f"'{edit.replacement}'" not in rendered for edit in candidate.edits)
    first = candidate.edits[0]
    assert repr(first) == f"CorrectionEdit(kind='erasure', reverse_index={first.reverse_index})"
    assert repr(correct_worksheet_residue("2ppjkw73qdjvc")) == "(WorksheetCorrection(reverse_index=37),)"


def test_master_seed_default_rendering_does_not_disclose_seed_material() -> None:
    secret = MasterSeed.from_seed(bytes(range(16)), identifier="test")

    assert secret.s not in str(secret)
    assert secret.s not in repr(secret)
    assert "payload" not in repr(secret)
    assert str(secret) == "<MasterSeed: redacted>"
    assert repr(secret) == "MasterSeed(<redacted>)"


def test_master_seed_factory_can_only_construct_index_s() -> None:
    secret = MasterSeed.from_seed(bytes(16), identifier="test", threshold=2)
    assert secret.share_idx == "s"
    assert secret.data == bytes(16)


@pytest.mark.parametrize(
    ("arguments", "error"),
    (
        ((1, "test", "s"), InvalidThreshold),
        ((2.0, "test", "a"), InvalidThreshold),
        ((2, "bad", "a"), InvalidIdentifier),
        ((0, "test", "a"), InvalidShareIndex),
    ),
)
def test_header_invariants(arguments: tuple[object, ...], error: type[Exception]) -> None:
    with pytest.raises(error):
        _header(*arguments)
