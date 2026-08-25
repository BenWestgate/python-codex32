"""Gate 4 BCH, profile-adapter, and private-residue correction tests."""

import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2, VECTOR_5
from data.sharing_vectors import SHARING_VECTORS
from hypothesis import given, settings
from hypothesis import strategies as st
from test_profiles import _oracle_encode

import codex32
from codex32 import CorrectionCandidate, CorrectionContext, CorrectionEdit, Profile, correct
from codex32.bech32 import CHARSET
from codex32.checksums import _CODEX32, _CODEX32_LONG
from codex32.correction import (
    _LONG_SPEC,
    _SHORT_SPEC,
    _correct_fixed,
    correct_worksheet_residue,
)
from codex32.errors import InvalidCorrectionInput
from tools.verify_correction_constants import verify


def _change(
    value: str,
    positions: list[int],
    *,
    erasures: int = 0,
) -> str:
    characters = list(value)
    split = len(positions) - erasures
    for order, position in enumerate(positions[:split], 1):
        current = CHARSET.index(characters[position].lower())
        replacement = CHARSET[current ^ order]
        characters[position] = replacement.upper() if value.isupper() else replacement
    for position in positions[split:]:
        characters[position] = "?"
    return "".join(characters)


def _success(
    damaged: str,
    profile: Profile = Profile.MS,
) -> CorrectionCandidate:
    result = _correct_fixed(damaged, suspected_profile=profile)
    assert isinstance(result, CorrectionCandidate)
    return result


def _pack(values: tuple[int, ...]) -> int:
    packed = 0
    for value in values:
        packed = (packed << 5) | value
    return packed


def test_p70_target_constants_match_checksum_layer() -> None:
    assert _pack(_SHORT_SPEC.target) == _CODEX32.constant
    assert _pack(_LONG_SPEC.target) == _CODEX32_LONG.constant


def test_frozen_bch_constants_are_reproducible() -> None:
    verify()


def test_frozen_p70_differential_corpus() -> None:
    path = Path(__file__).parent / "data" / "p70_correction_vectors.json"
    document = json.loads(path.read_text())
    assert document["source"]["head"] == ("610cbad30258c80cd862b3773a20f8099d25e36e")
    for case in document["cases"]:
        result = _correct_fixed(
            case["damaged"],
            suspected_profile=Profile.MS,
        )
        if case["expected"] is None:
            assert result is None
        else:
            assert isinstance(result, CorrectionCandidate)
            assert result.artifact.text == case["expected"]


_DISTRIBUTIONS = tuple(
    (errors, erasures)
    for errors in range(5)
    for erasures in range(9)
    if errors + erasures and 2 * errors + erasures <= 8
)


@pytest.mark.parametrize("source", (VECTOR_1["secret_s"], VECTOR_5["secret_s"]))
@pytest.mark.parametrize(("errors", "erasures"), _DISTRIBUTIONS)
def test_every_bch_error_erasure_distribution(
    source: str,
    errors: int,
    erasures: int,
) -> None:
    count = errors + erasures
    positions = [3 + ((index * 11 + errors * 3 + erasures) % (len(source) - 3)) for index in range(count)]
    assert len(set(positions)) == count
    result = _success(_change(source, positions, erasures=erasures))
    assert result.artifact.text == source


@given(
    st.sampled_from((VECTOR_1["secret_s"], VECTOR_5["secret_s"])),
    st.sampled_from(_DISTRIBUTIONS),
    st.data(),
)
@settings(max_examples=80, deadline=None)
def test_bch_positions_and_addends_property(
    source: str,
    distribution: tuple[int, int],
    data,
) -> None:
    errors, erasures = distribution
    count = errors + erasures
    positions = data.draw(
        st.lists(
            st.integers(min_value=3, max_value=len(source) - 1),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )
    result = _success(_change(source, positions, erasures=erasures))
    assert result.artifact.text == source


@pytest.mark.parametrize(
    ("source", "degree"),
    ((VECTOR_1["secret_s"], 13), (VECTOR_5["secret_s"], 15)),
)
def test_every_consecutive_erasure_burst(
    source: str,
    degree: int,
) -> None:
    prefix_length = 3
    for start in range(prefix_length, len(source) - degree + 1):
        positions = list(range(start, start + degree))
        result = _success(_change(source, positions, erasures=degree))
        assert result.artifact.text == source


@pytest.mark.parametrize(
    ("profile", "source"),
    (
        (Profile.MS, VECTOR_1["secret_s"]),
        (Profile.MS, VECTOR_5["secret_s"]),
        (Profile.CL, SHARING_VECTORS["cl"]["S"]),
        (Profile.BIP39_12W, SHARING_VECTORS["bip39_12w"]["S"]),
        (Profile.BIP39_24W, SHARING_VECTORS["bip39_24w"]["S"]),
    ),
)
def test_all_registered_profiles_use_public_correction_api(
    profile: Profile,
    source: str,
) -> None:
    prefix_length = len(profile.value) + 1
    positions = [prefix_length + offset for offset in (2, 7, 12, 17)]
    result = correct(CorrectionContext(profile), _change(source, positions))
    assert len(result) == 1 and result[0].artifact.text == source


def test_public_candidate_reports_fixed_edits_and_ranking_inputs() -> None:
    source = VECTOR_1["secret_s"]
    positions = [7, 11]
    damaged = _change(source, positions, erasures=1)
    result = correct(CorrectionContext(Profile.MS), damaged)

    assert len(result) == 1
    candidate = result[0]
    edits = {edit.reverse_index: edit for edit in candidate.edits}
    assert edits[len(source) - positions[0] - 1] == CorrectionEdit(
        "substitution",
        len(source) - positions[0] - 1,
        damaged[positions[0]],
        source[positions[0]],
    )
    assert edits[len(source) - positions[1] - 1] == CorrectionEdit(
        "erasure",
        len(source) - positions[1] - 1,
        "?",
        source[positions[1]],
    )
    assert candidate.capture_volume > 0
    assert candidate.erasures_filled == 1
    assert candidate.addend_hamming_weight > 0
    assert isinstance(candidate.crc_padding_match, bool)


def test_public_context_constrains_length_prefix_and_used_indices() -> None:
    source = VECTOR_2["share_A"]
    valid = CorrectionContext(
        Profile.MS,
        expected_length=len(source),
        immutable_prefix=source[:8],
    )
    candidate = correct(valid, source)

    assert len(candidate) == 1 and candidate[0].artifact.text == source
    assert correct(CorrectionContext(Profile.MS, expected_length=74), source) == ()
    assert correct(CorrectionContext(Profile.MS, immutable_prefix="ms12cash"), source) == ()
    assert correct(CorrectionContext(Profile.MS, excluded_indices=("A",)), source) == ()


@pytest.mark.parametrize(
    "context",
    (
        CorrectionContext("ms"),  # type: ignore[arg-type]
        CorrectionContext(Profile.MS, expected_length=True),  # type: ignore[arg-type]
        CorrectionContext(Profile.MS, expected_length=49),
        CorrectionContext(Profile.MS, immutable_prefix="ms11test"),
        CorrectionContext(Profile.MS, immutable_prefix="ms10tes!"),
        CorrectionContext(Profile.MS, excluded_indices=["a"]),  # type: ignore[arg-type]
        CorrectionContext(Profile.MS, excluded_indices=("s",)),
        CorrectionContext(Profile.MS, excluded_indices=("a", "A")),
    ),
)
def test_malformed_public_context_is_rejected(context: CorrectionContext) -> None:
    with pytest.raises(InvalidCorrectionInput):
        correct(context, VECTOR_1["secret_s"])


def test_public_records_are_frozen_slotted_and_unchanged_input_is_a_candidate() -> None:
    context = CorrectionContext(Profile.MS)
    candidate = correct(context, VECTOR_1["secret_s"])[0]

    assert not hasattr(context, "__dict__")
    assert not hasattr(candidate, "__dict__")
    assert not hasattr(CorrectionEdit("erasure", 0, "?", "q"), "__dict__")
    assert candidate.edits == ()
    with pytest.raises(FrozenInstanceError):
        context.expected_length = 48  # type: ignore[misc]


def test_public_correction_keeps_prefix_immutable_and_types_strict() -> None:
    source = VECTOR_1["secret_s"]
    assert correct(CorrectionContext(Profile.MS), "cl1" + source[3:]) == ()
    assert correct(CorrectionContext(Profile.MS), source[:2] + "x" + source[3:]) == ()
    with pytest.raises(TypeError):
        correct(Profile.MS, source)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        correct(CorrectionContext(Profile.MS), b"backup")  # type: ignore[arg-type]


def test_uppercase_input_preserves_case_and_reverse_addends() -> None:
    source = VECTOR_1["secret_s"].upper()
    position = 10
    damaged = _change(source, [position])
    result = _success(damaged)
    assert result.artifact.text == source
    assert result.edits == (
        CorrectionEdit(
            "substitution",
            len(source) - position - 1,
            damaged[position],
            source[position],
        ),
    )
    addend = CHARSET.index(source[position].lower()) ^ CHARSET.index(damaged[position].lower())
    assert result.addend_hamming_weight == addend.bit_count()


def test_fixed_failures_are_fail_closed() -> None:
    mixed = "M" + VECTOR_1["secret_s"][1:]
    damaged = list(VECTOR_1["secret_s"])
    damaged[8:22] = "?" * 14
    body_failure = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx8ueney9awjglu"
    cases = (
        (mixed, Profile.MS),
        ("cl1" + VECTOR_1["secret_s"][3:], Profile.MS),
        ("cl1" + "q" * 40, Profile.CL),
        ("".join(damaged), Profile.MS),
        (body_failure, Profile.MS),
    )
    assert all(_correct_fixed(value, suspected_profile=profile) is None for value, profile in cases)


def test_bch_and_linear_failures_return_no_candidate() -> None:
    source = VECTOR_1["secret_s"]
    five_errors = _change(source, [5, 12, 19, 26, 33])
    mixed = _change(source, [5, 8, 11, 14, 17, 20, 23, 26, 29, 32], erasures=9)
    assert _correct_fixed(five_errors, suspected_profile=Profile.MS) is None
    assert _correct_fixed(mixed, suspected_profile=Profile.MS) is None


def test_bip39_outer_correction_must_reparse_embedded_checksum() -> None:
    invalid = _oracle_encode("bip39_12w", "0tests" + "q" * 27)
    damaged = _change(invalid, [invalid.rfind("1") + 8])
    result = _correct_fixed(
        damaged,
        suspected_profile=Profile.BIP39_12W,
    )
    assert result is None


@pytest.mark.parametrize(
    ("value", "profile"),
    (
        ("ms1" + "q" * 1022, Profile.MS),
        ("ms10test\n" + "q" * 40, Profile.MS),
    ),
)
def test_fixed_input_is_bounded_before_algebra(
    value: str,
    profile: Profile,
) -> None:
    result = _correct_fixed(value, suspected_profile=profile)
    assert result is None


def test_suspected_profile_is_not_inferred() -> None:
    result = _correct_fixed(
        SHARING_VECTORS["cl"]["S"],
        suspected_profile=Profile.MS,
    )
    assert result is None
    with pytest.raises(TypeError):
        _correct_fixed(VECTOR_1["secret_s"], suspected_profile="ms")  # type: ignore[arg-type]


def test_private_book_residue_uses_reverse_index() -> None:
    assert correct_worksheet_residue("2ppjkw73qdjvc") == (codex32.WorksheetCorrection(37, "x"),)
    assert correct_worksheet_residue("secretshare32") == ()


def test_unmapped_short_locator_roots_are_not_silently_dropped() -> None:
    assert correct_worksheet_residue("t9cxwv58l0sgd") is None

    damaged = (
        "ms10testsqqqsyquyq5rqwzqfpg9scrgwpugpzysnzs23v9ccrydpk8varg0jzgfzyvjz2f389q5j52ev9cmlrfhvw53es26"
    )
    result = _correct_fixed(damaged, suspected_profile=Profile.MS)
    assert result is None


@pytest.mark.parametrize(
    ("residue", "expected"),
    (
        ("vass072kvekqd", (37, "p")),
        ("sc8n6wqutkxqv", (63, "p")),
    ),
)
def test_bip39_worksheet_residues_need_no_profile(
    residue: str,
    expected: tuple[int, str],
) -> None:
    result = correct_worksheet_residue(residue)
    assert result is not None
    assert tuple((item.reverse_index, item.addend) for item in result) == (expected,)


@pytest.mark.parametrize(
    ("residue", "endpoint", "outside"),
    (
        ("secretshare32", 92, 93),
        ("secretshare32ex", 1022, 1023),
    ),
)
def test_residue_indices_are_bounded_only_by_checksum_period(
    residue: str,
    endpoint: int,
    outside: int,
) -> None:
    assert correct_worksheet_residue(
        residue,
        erasure_indices=(endpoint,),
    ) == (codex32.WorksheetCorrection(endpoint, "q"),)
    with pytest.raises(InvalidCorrectionInput):
        correct_worksheet_residue(residue, erasure_indices=(outside,))


@pytest.mark.parametrize(
    "indices",
    (
        (True,),
        (-1,),
        (1, 1),
        {1},
        "1",
    ),
)
def test_residue_erasure_indices_are_strict(indices: object) -> None:
    with pytest.raises(InvalidCorrectionInput):
        correct_worksheet_residue(
            "secretshare32",
            erasure_indices=indices,  # type: ignore[arg-type]
        )
    assert (
        correct_worksheet_residue(
            "secretshare32",
            erasure_indices=tuple(range(14)),
        )
        is None
    )
    assert (
        correct_worksheet_residue(
            "secretshare32",
            erasure_indices=range(100_000_000),
        )
        is None
    )


@pytest.mark.parametrize(
    "residue",
    (
        "secretshare3",
        "secretshare32q",
        "secretShare32",
        "secretshare3!",
    ),
)
def test_residue_lexical_validation(residue: str) -> None:
    with pytest.raises(InvalidCorrectionInput):
        correct_worksheet_residue(residue)


def test_public_surface_exports_full_and_worksheet_correction() -> None:
    assert "residue" in inspect.signature(codex32.correct_worksheet_residue).parameters
    assert tuple(inspect.signature(codex32.correct).parameters) == ("context", "damaged_text")
    for name in (
        "CorrectionCandidate",
        "CorrectionContext",
        "CorrectionEdit",
        "InvalidCorrectionInput",
        "WorksheetCorrection",
        "correct",
    ):
        assert name in codex32.__all__ and hasattr(codex32, name)
    for legacy in (
        "Correction",
        "CorrectionSearchResult",
        "correct_codex32_string",
        "corrections_from_residue",
        "search_codex32_corrections",
    ):
        assert not hasattr(codex32, legacy)
