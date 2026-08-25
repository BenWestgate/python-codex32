"""Gate 3 structural-family, immutable-prefix, ranking, and completion evidence."""

from itertools import combinations
from math import comb
from unittest.mock import patch

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_5
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO, BIP39_24W_ZERO

from codex32 import CorrectionContext, MasterSeed, Profile, correct
from codex32.correction import CorrectionCandidate, _best, _erasure_state, _primary
from codex32.generation import _fingerprint_identifier
from codex32.indel import (
    _CHARACTER_CLASSES,
    _FIXED,
    _GROUP_CLASSES,
    _alignment_count,
    _capacities,
    _has_consecutive_ambiguity,
    _reductions,
    _required_header_substitutions,
    _volumes,
)

SOURCE = VECTOR_1["secret_s"]
CONTEXT = CorrectionContext(Profile.MS, expected_length=len(SOURCE))


def _groups(text: str) -> list[str]:
    return [text[start : start + 4] for start in range(0, len(text), 4)]


def _character_damage(source: str, inserted: int, omitted: int) -> str:
    characters = list(source)
    for position in reversed((14, 22, 30, 38)[:omitted]):
        characters.pop(position)
    extras = "qpzr"
    for order, position in enumerate((12, 20, 28, 36)[:inserted]):
        characters.insert(position, extras[order])
    return "".join(characters)


@pytest.mark.parametrize(
    ("inserted", "omitted"),
    (
        (0, 4),
        (1, 3),
        (0, 3),
        (0, 2),
        (1, 2),
        (0, 1),
        (1, 1),
        (2, 2),
        (1, 0),
        (2, 1),
        (2, 0),
        (3, 1),
        (3, 0),
        (4, 0),
    ),
)
def test_complete_character_family_recovers_source(inserted: int, omitted: int) -> None:
    damaged = _character_damage(SOURCE, inserted, omitted)

    assert [candidate.artifact.text for candidate in correct(CONTEXT, damaged)] == [SOURCE]


def test_character_class_set_is_exact() -> None:
    pairs = {(shape.inserted, shape.omitted) for shape in _CHARACTER_CLASSES}

    assert len(pairs) == 14
    assert pairs == {
        (inserted, omitted) for inserted in range(5) for omitted in range(5) if 0 < inserted + omitted <= 4
    }


@pytest.mark.parametrize(
    ("inserted", "omitted"),
    ((0, 1), (0, 2), (1, 0), (2, 0), (1, 1)),
)
def test_complete_group_family_recovers_ungrouped_source(
    inserted: int,
    omitted: int,
) -> None:
    groups = _groups(SOURCE)
    for position in reversed((4, 8)[:omitted]):
        groups.pop(position)
    for order, position in enumerate((3, 7)[:inserted]):
        groups.insert(position, ("qqqq", "pppp")[order])
    damaged = "".join(groups)

    assert [candidate.artifact.text for candidate in correct(CONTEXT, damaged)] == [SOURCE]


def test_group_class_set_and_first_share_counts_are_exact() -> None:
    pairs = {(shape.inserted, shape.omitted) for shape in _GROUP_CLASSES}
    counts = {
        pair: _alignment_count(shape, 48 + shape.delta, 48, 3)
        for shape in _GROUP_CLASSES
        if (pair := (shape.inserted, shape.omitted))
    }

    assert pairs == {(0, 1), (1, 0), (0, 2), (1, 1), (2, 0)}
    assert counts == {
        (0, 1): 11,
        (1, 0): 12,
        (0, 2): 55,
        (1, 1): 121,
        (2, 0): 78,
    }


def test_group_search_does_not_depend_on_spaces() -> None:
    groups = _groups(SOURCE)
    groups.pop(7)
    groups.insert(3, "qqqq")
    ungrouped = "".join(groups)
    grouped = "  ".join(groups)

    plain = correct(CONTEXT, ungrouped)
    presented = correct(CONTEXT, grouped)

    assert [candidate.artifact.text for candidate in plain] == [SOURCE]
    assert [candidate.artifact.text for candidate in presented] == [SOURCE]
    assert plain[0].capture_volume == presented[0].capture_volume == 121 * 32**4


def test_immutable_confirmed_header_reduces_domains_and_cannot_be_repaired() -> None:
    prefix = SOURCE[:8]
    context = CorrectionContext(Profile.MS, 48, prefix)
    character = next(shape for shape in _CHARACTER_CLASSES if (shape.inserted, shape.omitted) == (2, 2))
    two_groups = next(shape for shape in _GROUP_CLASSES if (shape.inserted, shape.omitted) == (0, 2))

    assert _alignment_count(character, 48, 48, len(prefix)) == comb(40, 2) ** 2
    assert _alignment_count(two_groups, 40, 48, len(prefix)) == 45
    assert correct(context, _character_damage(SOURCE, 1, 1))[0].artifact.text == SOURCE

    changed = ("2" if prefix[3] != "2" else "3") + SOURCE[4:]
    assert correct(context, SOURCE[:3] + changed) == ()
    assert correct(context, SOURCE[:5] + "?" + SOURCE[6:]) == ()


def test_header_pruning_is_a_lossless_lower_bound() -> None:
    ordinary = [0, 1, 2, 3, 4, 5]
    ordinary[0] = 15  # threshold 0
    ordinary[5] = 1  # changing this one symbol can satisfy both header rules

    assert _required_header_substitutions(ordinary, frozenset((1,))) == 1
    ordinary[0] = 1  # invalid threshold requires an independent repair
    assert _required_header_substitutions(ordinary, frozenset((1,))) == 2


def test_explicit_unknown_can_be_retained_or_deleted() -> None:
    retained = SOURCE[:19] + "?" + SOURCE[20:]
    extra = SOURCE[:19] + "?" + SOURCE[19:]

    retained_candidate = correct(CONTEXT, retained)[0]
    deleted_candidate = correct(CONTEXT, extra)[0]

    assert retained_candidate.artifact.text == deleted_candidate.artifact.text == SOURCE
    assert [edit.kind for edit in retained_candidate.edits] == ["erasure"]
    assert [edit.kind for edit in deleted_candidate.edits] == ["deletion"]


def test_structural_erasure_preserves_the_observed_character() -> None:
    damaged = SOURCE[:15] + "!" + SOURCE[16:25] + SOURCE[26:]

    candidate = correct(CONTEXT, damaged)[0]

    assert candidate.artifact.text == SOURCE
    assert {(edit.kind, edit.observed) for edit in candidate.edits} == {
        ("insertion", ""),
        ("erasure", "!"),
    }


def test_reductions_stream_each_unique_view_once() -> None:
    values = (1, 1, -1, 2, 1)
    expected = {
        tuple(value for index, value in enumerate(values) if index not in deleted)
        for deleted in combinations(range(len(values)), 2)
    }

    reductions = tuple(_reductions(values, "aa?ba", 2, 0))

    assert {retained for retained, _edits in reductions} == expected
    assert len(reductions) == len(expected)


def test_structural_capacity_does_not_borrow_linear_erasure_recovery() -> None:
    assert _capacities(8, 13) == range(1)
    assert _capacities(9, 13) == range(0)
    assert not hasattr(_erasure_state, "cache_info")

    consecutive = frozenset(range(12, 21))
    separated = frozenset(range(10, 28, 2))
    consecutive_text = "".join("?" if index in consecutive else value for index, value in enumerate(SOURCE))
    separated_text = "".join("?" if index in separated else value for index, value in enumerate(SOURCE))

    assert correct(CONTEXT, consecutive_text)[0].artifact.text == SOURCE
    assert correct(CONTEXT, separated_text) == ()


def test_every_expected_length_consecutive_fixed_erasure_burst() -> None:
    source = VECTOR_1["secret_s"]
    for count in range(9, 14):
        for start in range(3, len(source) - count + 1):
            positions = frozenset(range(start, start + count))
            damaged = "".join("?" if index in positions else value for index, value in enumerate(source))

            candidate = correct(CONTEXT, damaged)[0]

            assert candidate.artifact.text == source
            assert candidate.erasures_filled == count


def test_fixed_volume_retains_every_bch_substitution_layer() -> None:
    assert list(_volumes(_FIXED, 1, 45, 0, 13)) == [
        1,
        45 * 31,
        comb(45, 2) * 31**2,
        comb(45, 3) * 31**3,
        comb(45, 4) * 31**4,
    ]


def test_structural_search_requires_an_exact_target_length() -> None:
    damaged = SOURCE[:19] + SOURCE[20:]

    assert correct(CorrectionContext(Profile.MS), damaged) == ()
    assert correct(CONTEXT, damaged)[0].artifact.text == SOURCE


@pytest.mark.parametrize(
    ("profile", "source"),
    (
        (Profile.MS, VECTOR_5["secret_s"]),
        (Profile.CL, SHARING_VECTORS["cl"]["S"]),
        (Profile.BIP39_12W, BIP39_12W_ZERO),
        (Profile.BIP39_24W, BIP39_24W_ZERO),
    ),
)
def test_structural_search_supports_every_profile(profile: Profile, source: str) -> None:
    damaged = source[:17] + source[18:]

    result = correct(CorrectionContext(profile, expected_length=len(source)), damaged)

    assert [candidate.artifact.text for candidate in result] == [source]


def test_two_each_with_two_substitutions_exceeds_result_bound() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test").text
    damaged = list(source)
    damaged.pop(34)
    damaged.pop(16)
    damaged.insert(11, "q" if damaged[11] != "q" else "p")
    damaged.insert(28, "p" if damaged[28] != "p" else "q")
    damaged[3] = "2"
    damaged[41] = "q" if damaged[41] != "q" else "p"

    candidates = correct(CorrectionContext(Profile.MS, 48), "".join(damaged))

    assert all(candidate.artifact.text != source for candidate in candidates)


def test_two_each_with_one_substitution_uses_the_generic_fixed_core() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test").text
    damaged = list(source)
    for position in reversed((18, 32)):
        damaged.pop(position)
    for position, character in ((14, "q"), (28, "p")):
        damaged.insert(position, character)
    damaged[37] = "q" if damaged[37] != "q" else "p"

    candidate = correct(CorrectionContext(Profile.MS, 48), "".join(damaged))[0]

    assert candidate.artifact.text == source
    assert [edit.kind for edit in candidate.edits].count("substitution") == 1


def test_duplicate_reconstruction_keeps_lower_hamming_path() -> None:
    damaged = "ms102estssq9qsyqcyq5rqwqfpg9scrgwp76dy3vdu8w5xnk"

    candidate = correct(CONTEXT, damaged)[0]

    assert candidate.addend_hamming_weight == 2


def test_cli_tie_breaks_follow_hamming_crc_then_fingerprint() -> None:
    seed = bytes(range(16))
    fingerprint = MasterSeed.from_seed(seed, identifier=_fingerprint_identifier(seed))
    mismatch = MasterSeed.from_seed(seed, identifier="test")
    high_hamming = CorrectionCandidate(mismatch, (), 10, 0, 3, True)
    crc = CorrectionCandidate(mismatch, (), 10, 0, 2, True)
    fingerprint_match = CorrectionCandidate(fingerprint, (), 10, 0, 2, True)

    assert len(_primary((high_hamming, crc, fingerprint_match))) == 3
    assert _best((high_hamming, crc, fingerprint_match)) == (fingerprint_match,)


def test_lower_primary_volume_always_wins_cli_ties() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    better_volume = CorrectionCandidate(source, (), 9, 0, 5, False)
    better_hints = CorrectionCandidate(source, (), 10, 0, 1, True)

    assert _best((better_hints, better_volume)) == (better_volume,)


def test_structural_input_and_deadline_are_bounded() -> None:
    assert correct(CONTEXT, "ms1" + "q" * 200) == ()
    assert correct(CONTEXT, "ms1" + " " * 10_000 + SOURCE[3:]) == ()
    assert correct(CONTEXT, "ms1\t" + SOURCE[3:]) == ()

    from codex32.indel import _search

    with (
        patch("codex32.indel._correct_fixed", return_value=None),
        patch("codex32.indel._safe", return_value=True),
        patch("codex32.indel.monotonic", return_value=11.0),
    ):
        candidates, complete = _search(CONTEXT, SOURCE + "q", deadline=10.0)

    assert candidates == () and not complete

    with patch("codex32.indel.monotonic", return_value=11.0):
        assert not _has_consecutive_ambiguity(CONTEXT, SOURCE + "qqqq", 10.0)
