"""Frozen malformed-input evidence for every untrusted public text boundary."""

import json
from pathlib import Path

import pytest

from codex32 import CorrectionContext, Profile, complete_checksum, correct, parse_codex32, recover_secret
from codex32._cli_parser import parser
from codex32.errors import CodexError

_DOCUMENT = json.loads((Path(__file__).parent / "data" / "malformed_inputs.json").read_text())
assert _DOCUMENT["schema"] == 1


@pytest.mark.parametrize("case", _DOCUMENT["parse"], ids=lambda case: case["id"])
def test_malformed_parse_corpus(case: dict[str, str]) -> None:
    with pytest.raises(CodexError):
        parse_codex32(case["text"])


@pytest.mark.parametrize("case", _DOCUMENT["checksum_completion"], ids=lambda case: case["id"])
def test_malformed_completion_corpus(case: dict[str, str]) -> None:
    with pytest.raises(CodexError):
        complete_checksum(case["text"])


@pytest.mark.parametrize("case", _DOCUMENT["interpolation"], ids=lambda case: case["id"])
def test_malformed_interpolation_corpus(case: dict[str, object]) -> None:
    artifacts = [parse_codex32(text) for text in case["artifacts"]]  # type: ignore[union-attr]
    with pytest.raises(CodexError):
        recover_secret(artifacts)


@pytest.mark.parametrize("case", _DOCUMENT["correction"], ids=lambda case: case["id"])
def test_malformed_correction_corpus(case: dict[str, str]) -> None:
    assert correct(CorrectionContext(Profile(case["profile"])), case["text"]) == ()


@pytest.mark.parametrize("case", _DOCUMENT["cli_tokens"], ids=lambda case: case["id"])
def test_malformed_cli_token_corpus(case: dict[str, object]) -> None:
    with pytest.raises(SystemExit) as error:
        parser().parse_args(case["args"])  # type: ignore[arg-type]
    assert error.value.code == 2
