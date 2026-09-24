"""Cumulative checksum evidence and disclosure before any recovery output."""

import contextlib
import io
import sys
from dataclasses import replace
from unittest.mock import patch

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2
from data.sharing_vectors import INVALID_BIP39_IMPLIED_SECRET, SHARING_VECTORS
from test_cli import _FakeBitcoinCore, _TTYInput, _TTYOutput
from test_generic_hrp import UNKNOWN

from codex32 import CorrectionCandidate, CorrectionContext, _cli_input, cli, correct, indel, parse_codex32
from codex32.correction import (
    _capture_mass,
    _low_discrimination,
    _residue_low_discrimination,
    correct_worksheet_residue,
)


def _candidate(text=VECTOR_1["secret_s"], *, low=True):
    return CorrectionCandidate(
        parse_codex32(text),
        (),
        1,
        0,
        0,
        None,
        cumulative_capture_volume=(1 << 60) + int(low),
        capture_space_bits=65,
    )


@pytest.mark.parametrize("bits", (65, 75))
def test_strict_five_bit_boundary(bits):
    boundary = 1 << (bits - 5)
    assert not _low_discrimination(boundary - 1, bits)
    assert not _low_discrimination(boundary, bits)
    assert _low_discrimination(boundary + 1, bits)
    assert _low_discrimination(1 << bits, bits)


def test_mixed_checksum_spaces_include_every_equal_or_better_class():
    layers = [(10, 65), (100, 65), (100, 75), (101, 65)]
    assert _capture_mass(layers, 100) == ((110 << 10) + 100, 75)
    assert _capture_mass(list(reversed(layers)), 100) == _capture_mass(layers, 100)


@pytest.mark.parametrize("complete", (True, False))
def test_scheduler_annotates_from_admission_even_when_no_work_finished(monkeypatch, complete):
    source = VECTOR_1["secret_s"]
    rank = (1 << 59) + 1
    candidate = replace(_candidate(source), capture_volume=rank, search_complete=complete)
    frontier = {
        (48, indel._FIXED, 0, 0): rank,
        (48, indel._StructuralClass(0, 0, adjacent=1), 0, 0): rank,
        (48, indel._StructuralClass(0, 0, adjacent=2), 0, 0): rank + 1,
    }
    monkeypatch.setattr(indel, "_frontier", lambda *args: frontier)
    monkeypatch.setattr("codex32._competitors._search_competitors", lambda *args: ((candidate,), complete))
    result, finished = indel._search_many(
        (CorrectionContext("ms", 48),),
        source,
        primary=frozenset((48,)),
        competitors=True,
    )
    assert finished is complete
    assert result[0].capture_volume == rank
    assert result[0].cumulative_capture_volume == 2 * rank
    assert result[0].capture_space_bits == 65
    assert result[0].low_checksum_discrimination


@pytest.mark.parametrize(
    "source,degree",
    [
        (VECTOR_1["secret_s"], 13),
        *((v["S"], 13) for v in SHARING_VECTORS.values()),
        (UNKNOWN["short"]["S"], 13),
        (UNKNOWN["long"]["S"], 15),
    ],
)
def test_public_api_full_checksum_erasure_completion_carries_risk(source, degree):
    hrp = source.rsplit("1", 1)[0]
    candidates = correct(CorrectionContext(hrp, len(source)), source[:-degree] + "?" * degree)
    assert len(candidates) == 1 and candidates[0].artifact.text == source
    assert candidates[0].capture_space_bits == 5 * degree
    assert candidates[0].cumulative_capture_volume == 1 << (5 * degree)
    assert candidates[0].low_checksum_discrimination


@pytest.mark.parametrize("entrypoint", (cli.main, cli.ms_main))
@pytest.mark.parametrize("plain", (False, True))
def test_noninteractive_gate_emits_only_operational_error(entrypoint, plain):
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO(VECTOR_1["secret_s"][:-1] + "?")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        patch.object(cli, "_correction_candidates", return_value=((_candidate(),), True, None, False)),
    ):
        status = entrypoint(["correct", *(["--plain"] if plain else [])])
    prog = "codex32" if entrypoint is cli.main else "ms32"
    assert status == 3 and stdout.getvalue() == ""
    assert stderr.getvalue() == f"{prog}: interactive confirmation required\n"


@pytest.mark.parametrize("answer", ("y", "Y", "yes", "Yes", "n", "", "other", None))
@pytest.mark.parametrize("command", ("correct", "secret", "share", "create"))
def test_declining_gate_aborts_every_flow_without_metadata(monkeypatch, answer, command):
    source = VECTOR_2["share_A"] if command == "share" else VECTOR_1["secret_s"]
    candidate = _candidate(source)
    prompts = []

    def respond(prompt, prefill=""):
        prompts.append(prompt)
        if len(prompts) == 1:
            return source[:-1] + "?"
        assert prompt == "If you understand this, type YES to attempt to correct the data: "
        if answer is None:
            raise EOFError
        return answer

    monkeypatch.setattr(_cli_input, "_editable_input", respond)
    monkeypatch.setattr(_cli_input, "_suggestions", lambda *args, **kwargs: (candidate,))
    monkeypatch.setattr(cli, "_suggestions", lambda *args, **kwargs: (candidate,))
    monkeypatch.setattr(
        cli, "_correction_candidates", lambda *args, **kwargs: ((candidate,), True, None, False)
    )
    core = _FakeBitcoinCore()
    monkeypatch.setattr(cli.BitcoinCore, "connect", lambda *args: core)
    stdout, stderr = _TTYOutput(), _TTYOutput()
    args = [command, *({"share": ["d"], "create": ["--existing"]}.get(command, []))]
    with (
        patch.object(sys, "stdin", _TTYInput()),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = (cli.ms_main if command == "create" else cli.main)(args)
    expected_status = 3 if command == "correct" else 1
    assert status == expected_status and stdout.getvalue() == ""
    assert len(prompts) == 2 and core.imported is None
    warning = stderr.getvalue()
    assert "\x1b[1;31mWarning:\x1b[0m If you are generating new data" in warning
    assert 'errors, so any errors you have made up to this point will be "locked in" by' in warning
    assert "If you are recovering data with this many missing characters" in warning
    assert source not in warning and "Master fingerprint" not in warning


def test_yes_reveals_candidate_after_gate_with_plain_output(monkeypatch):
    source = VECTOR_1["secret_s"]
    candidate = _candidate(source)
    stdout, stderr = io.StringIO(), _TTYOutput()
    responses = iter((source[:-1] + "?", "YES"))

    def respond(prompt, prefill=""):
        if prompt.startswith("If you understand"):
            assert source not in stderr.getvalue()
            assert "Master fingerprint" not in stderr.getvalue()
        return next(responses)

    monkeypatch.setattr(_cli_input, "_editable_input", respond)
    monkeypatch.setattr(
        cli, "_correction_candidates", lambda *args, **kwargs: ((candidate,), True, None, False)
    )
    with (
        patch.object(sys, "stdin", _TTYInput()),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(["correct", "--plain"]) == 1
    assert source in stderr.getvalue() and stdout.getvalue() == ""
    assert "\x1b[1;31mWarning:\x1b[0m" in stderr.getvalue()


def test_redirected_stderr_blocks_low_discrimination_disclosure(monkeypatch):
    source = VECTOR_1["secret_s"]
    candidate = _candidate(source)
    responses = iter((source[:-1] + "?",))
    monkeypatch.setattr(_cli_input, "_editable_input", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(
        cli, "_correction_candidates", lambda *args, **kwargs: ((candidate,), True, None, False)
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.object(sys, "stdin", _TTYInput()),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(["correct", "--plain"]) == 3
    assert stdout.getvalue() == ""
    assert stderr.getvalue().strip() == "codex32: interactive confirmation required"


def test_yes_still_requires_independent_whole_card_acceptance(monkeypatch):
    candidate = _candidate()
    prompts = []
    answers = iter(("YES", "n"))
    monkeypatch.setattr(_cli_input, "_editable_input", lambda prompt: prompts.append(prompt) or next(answers))
    with patch.object(sys, "stdin", _TTYInput()), contextlib.redirect_stderr(_TTYOutput()):
        assert _cli_input._confirm_correction(candidate, [], False) is False
    assert prompts == [
        "If you understand this, type YES to attempt to correct the data: ",
        "Does this entire string exactly match your recovery card? [y/N]: ",
    ]


def test_redirected_correct_uses_terminal_gate_without_second_confirmation(monkeypatch):
    source = VECTOR_1["secret_s"]
    candidate = _candidate(source)
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return "YES"

    monkeypatch.setattr(_cli_input, "_confirmation_input", confirm)
    monkeypatch.setattr(
        cli, "_correction_candidates", lambda *args, **kwargs: ((candidate,), True, None, False)
    )
    stdout, stderr = io.StringIO(), _TTYOutput()
    with (
        patch.object(sys, "stdin", io.StringIO(source[:-1] + "?")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(["correct"]) == 1
    assert prompts == ["If you understand this, type YES to attempt to correct the data: "]
    assert source in stderr.getvalue() and stdout.getvalue() == ""
    assert _cli_input._card_text(source) not in stderr.getvalue()


def test_redirected_recovery_uses_terminal_gate_then_whole_card_confirmation(monkeypatch):
    source = VECTOR_1["secret_s"]
    candidate = _candidate(source)
    prompts = []
    answers = iter(("YES", "y"))

    def confirm(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(_cli_input, "_confirmation_input", confirm)
    monkeypatch.setattr(_cli_input, "_suggestions", lambda *args, **kwargs: (candidate,))
    stdout, stderr = io.StringIO(), _TTYOutput()
    with (
        patch.object(sys, "stdin", io.StringIO(source[:-1] + "?")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(["secret", "--plain"]) == 0
    assert prompts == [
        "If you understand this, type YES to attempt to correct the data: ",
        "Does this entire string exactly match your recovery card? [y/N]: ",
    ]
    assert stdout.getvalue() == source + "\n"
    assert "Possible correction:" in stderr.getvalue()


def test_redirected_recovery_without_terminal_reveals_nothing(monkeypatch):
    source = VECTOR_1["secret_s"]
    candidate = _candidate(source)
    monkeypatch.setattr(_cli_input, "_suggestions", lambda *args, **kwargs: (candidate,))
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO(source[:-1] + "?")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(["secret", "--plain"]) == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "codex32: interactive confirmation required\n"


@pytest.mark.parametrize("degree", (13, 15))
def test_residue_completion_is_gated_but_ordinary_repair_is_not(degree):
    residue = "q" * degree
    positions = tuple(range(degree))
    corrections = correct_worksheet_residue(residue, erasure_indices=positions)
    assert corrections
    assert _residue_low_discrimination(residue, positions, corrections)
    ordinary = correct_worksheet_residue("2ppjkw73qdjvc")
    assert ordinary and not _residue_low_discrimination("2ppjkw73qdjvc", (), ordinary)
    stdout, stderr = io.StringIO(), io.StringIO()
    args = ["correct", "--residue"]
    for position in positions:
        args.extend(("--erasure", str(position + 1)))
    with (
        patch.object(sys, "stdin", io.StringIO(residue)),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        assert cli.main(args) == 3
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "codex32: interactive confirmation required\n"


@pytest.mark.parametrize("residue", ("secretshare32", "secretshare32ex"))
def test_residue_exactly_five_bits_is_not_gated_even_with_zero_addends(residue):
    positions = tuple(range(len(residue) - 1))
    corrections = correct_worksheet_residue(residue, erasure_indices=positions)
    assert corrections and all(item.addend == "q" for item in corrections)
    assert not _residue_low_discrimination(residue, positions, corrections)


def test_previous_case_interpretation_search_is_charged_even_without_a_candidate(monkeypatch):
    candidate = replace(_candidate(), capture_volume=(1 << 60) + 1)
    monkeypatch.setattr(indel, "_frontier", lambda *args: {(48, indel._FIXED, 0, 0): 1})
    monkeypatch.setattr("codex32._competitors._search_competitors", lambda *args: ((candidate,), True))
    previous = [(1 << 60, 65)]
    result, _ = indel._search_many(
        (CorrectionContext("ms", 48),),
        VECTOR_1["secret_s"],
        primary=frozenset((48,)),
        competitors=True,
        capture_layers=previous,
    )
    assert result[0].cumulative_capture_volume == (1 << 60) + 1
    assert result[0].low_checksum_discrimination


@pytest.mark.parametrize("profile", ("bip39_12w", "bip39_24w"))
def test_cli_derives_hand_produced_bip39_set_but_rejects_invalid_implied_secret(profile):
    from test_generic_hrp import _invoke

    vector = SHARING_VECTORS[profile]
    assert _invoke(cli.main, ["share", "d", "--plain"], vector["A"] + "\n" + vector["C"]) == (
        0,
        vector["D"] + "\n",
        "",
    )
    invalid = INVALID_BIP39_IMPLIED_SECRET
    status, output, error = _invoke(cli.main, ["share", "d"], invalid["A"] + "\n" + invalid["C"])
    assert status == 1 and output == "" and "embedded BIP39 entropy checksum is invalid" in error
