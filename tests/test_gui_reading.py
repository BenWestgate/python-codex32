"""What the graphical entry field makes of typed text, without a display."""

import pytest
from data.bip93_vectors import VECTOR_2, VECTOR_3, VECTOR_5

from codex32_gui.reading import (
    PREFIX,
    expected_length,
    grouped,
    header_fault,
    lookalike_fault,
    normalize,
    read,
    repair,
)

SHARE_A = VECTOR_2["share_A"]
SHARE_C = VECTOR_2["share_C"]
SECRET_S = VECTOR_2["secret_S"]


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("", PREFIX),
        ("M", PREFIX),
        ("MS", PREFIX),
        ("ms1", PREFIX),
        ("ms12nameacd", "MS12NAMEACD"),
        ("MS12 NAME ACD", "MS12NAMEACD"),
        ("  ms1 2name\tacd ", "MS12NAMEACD"),
        ("2NAMEACD", "MS12NAMEACD"),
        (VECTOR_3["share_a"], VECTOR_3["share_a"].upper()),
    ],
)
def test_the_field_only_ever_holds_one_canonical_form(typed: str, canonical: str) -> None:
    assert normalize(typed) == canonical


def test_characters_outside_the_charset_cannot_be_entered() -> None:
    assert normalize("MS12nameb io1l+ acd") == "MS12NAMELACD"
    assert normalize("MS12NAME?") == "MS12NAME?"


def test_text_is_shown_in_four_character_windows() -> None:
    assert grouped(SHARE_C) == "MS12 NAME CACD EFGH JKLM NPQR STUV WXYZ 023F TR2G DZMP Y6PN"


def test_a_header_that_cannot_belong_to_any_card_is_reported() -> None:
    assert "0, or 2 through 9" in header_fault("MS1XNAMEA")
    assert "never split is card S" in header_fault("MS10NAMEA")
    assert header_fault("MS12NAMEA") == ""
    assert header_fault("MS10NAMES") == ""


def test_an_unreadable_header_is_not_judged() -> None:
    assert header_fault("MS1?NAMEA") == ""
    assert header_fault("MS12NAM?A") == ""


def test_a_card_already_entered_is_refused_by_name() -> None:
    assert "Card A has already been entered" in header_fault("MS12NAMEA", ("a",))
    assert header_fault("MS12NAMEC", ("a",)) == ""


def test_a_complete_card_reports_its_artifact() -> None:
    result = read(SHARE_C)
    assert result.artifact is not None and result.artifact.text == SHARE_C
    assert result.complete and not result.repairable
    assert result.level == "success"


def test_a_complete_secret_reports_its_artifact() -> None:
    assert read(SECRET_S).artifact is not None


def test_a_broken_checksum_offers_a_repair_rather_than_an_artifact() -> None:
    result = read(SHARE_C[:-1] + "M")
    assert result.artifact is None
    assert result.repairable
    assert result.level == "error"


def test_unreadable_characters_are_counted_and_never_parsed() -> None:
    result = read(SHARE_C[:-3] + "?" + SHARE_C[-2:])
    assert result.artifact is None and result.repairable
    assert result.unreadable == 1
    assert result.message == "1 character unreadable."


def test_partial_input_counts_towards_the_length_being_typed() -> None:
    result = read(SHARE_C[:20])
    assert result.message == "20 of 48 characters"
    assert not result.complete and not result.repairable


def test_the_length_of_the_first_card_fixes_the_rest_of_the_set() -> None:
    assert read(SHARE_C[:20], length=74).message == "20 of 74 characters"
    assert expected_length(20, None) == 48
    assert expected_length(60, None) == 61
    assert expected_length(200, None) == 127


def test_an_empty_field_invites_the_first_character() -> None:
    assert read(PREFIX).message.startswith("Start typing")
    assert read(PREFIX).artifact is None


def test_a_card_from_another_set_is_still_read_as_itself() -> None:
    assert read(SHARE_A).artifact is not None


def test_one_repair_is_offered_for_one_damaged_character() -> None:
    from codex32 import CorrectionCandidate

    found = repair(SHARE_C[:-1] + "M", None)
    assert isinstance(found, CorrectionCandidate)
    assert found.artifact.text == SHARE_C
    assert not found.low_checksum_discrimination


def test_a_card_that_fits_no_repair_says_so_instead_of_guessing() -> None:
    assert isinstance(repair(PREFIX + "Q" * 45, None), str)


def test_a_repair_that_repeats_an_accepted_card_is_not_offered() -> None:
    assert isinstance(repair(SHARE_A[:-1] + "Q", 48, ("a",)), str)


@pytest.mark.parametrize(("card", "checksum_length"), ((SHARE_C, 13), (VECTOR_5["secret_s"], 15)))
def test_a_card_with_too_little_checksum_left_demands_the_warning(card: str, checksum_length: int) -> None:
    from codex32 import CorrectionCandidate

    found = repair(card[:-checksum_length] + "?" * checksum_length, None)
    assert isinstance(found, CorrectionCandidate)
    assert found.low_checksum_discrimination


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("B", "8"), ("I", "J or L"), ("O", "0, a zero"), ("1", "L")],
)
def test_a_character_no_card_can_carry_is_named_with_what_it_is_probably(typed: str, expected: str) -> None:
    fault = lookalike_fault(f"MS12NAMEC{typed}")
    assert typed in fault
    assert expected in fault


def test_the_prefix_keeps_its_own_one() -> None:
    assert lookalike_fault("MS1") == ""
    assert lookalike_fault("ms12namec") == ""


def test_an_ordinary_stray_key_is_still_dropped_in_silence() -> None:
    assert lookalike_fault("MS12NAMEC!,. ") == ""


def test_several_confusable_characters_are_all_named() -> None:
    fault = lookalike_fault("MS12NAMEBO")
    assert "B or O" in fault
    assert "B is probably 8" in fault
    assert "O is probably 0" in fault
