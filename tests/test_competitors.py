"""CLI competitor scheduling, proof boundaries, and differential scoring."""

from dataclasses import replace
from time import monotonic
from unittest.mock import patch

import pytest

from codex32 import CorrectionContext, MasterSeed, Profile, Share, indel
from codex32 import _competitors as search
from codex32.bech32 import CHARSET
from codex32.correction import _correct_fixed
from codex32.profiles.ms32 import TEXT_LENGTHS

SOURCE = MasterSeed.from_seed(bytes(range(16)), identifier="test").text
REPORTED = "ms12namedll4f8jkh4e5vdvuldlfxu2jhdnlsm97xcenrxeg"
INTENDED = "ms12namedll4f8jlh4e5vdvuldlfxu2jhdnlsm97xvenrxeg"


def _state(text, target=48):
    result = indel._prepare(CorrectionContext(Profile.MS, target, text[:3]), text, indel._CLASSES)
    assert result is not None
    return result


def _substitute(text, count):
    damaged = list(text)
    for position in (12, 19, 26, 33)[:count]:
        damaged[position] = CHARSET[CHARSET.index(damaged[position]) ^ 1]
    return "".join(damaged)


def _run(text, *, target=None, **kwargs):
    lengths = TEXT_LENGTHS if target is None else (target,)
    contexts = tuple(CorrectionContext(Profile.MS, length, text[:3]) for length in lengths)
    return indel._search_many(contexts, text, primary=frozenset(lengths), competitors=True, **kwargs)


def test_reported_substitutions_exhaust_competitors_without_redundant_enumeration():
    original = indel._views
    searched = []

    def views(text, target, shape, immutable, base):
        searched.append((target, shape.operations, shape.unit))
        assert not (shape.unit == 1 and (shape.adjacent or shape.distant))
        yield from original(text, target, shape, immutable, base)

    with patch.object(indel, "_views", side_effect=views):
        candidates, complete = _run(REPORTED)

    assert complete and candidates[0].search_complete
    assert candidates[0].artifact.text == INTENDED
    assert candidates[0].capture_volume == 951_390
    assert (48, ("I", "O"), 1) in searched
    assert (48, ("AT",), 4) in searched
    assert {target for target, _, _ in searched} == {48}


@pytest.mark.parametrize(
    ("pairs", "volume"),
    (
        (((12, 13),), 44),
        (((12, 27),), 946),
        (((12, 13), (20, 21)), 1936),
        (((12, 27), (17, 39)), 894_916),
        (((12, 13), (13, 14)), 1936),
    ),
)
def test_known_swap_classification_retains_the_lower_capture_explanation(pairs, volume):
    damaged = list(SOURCE)
    for left, right in pairs:
        damaged[left], damaged[right] = damaged[right], damaged[left]
    candidates, complete = _run("".join(damaged), target=48)
    assert complete
    assert candidates[0].artifact.text == SOURCE
    assert candidates[0].capture_volume == volume
    assert candidates[0].addend_hamming_weight == 0
    assert any(edit.kind == "transposition" for edit in candidates[0].edits)


@pytest.mark.parametrize("substitutions", (0, 1, 2))
@pytest.mark.parametrize("seed", (bytes(range(16)), bytes([1]) * 16))
def test_directed_swap_views_match_exhaustive_alignment_scoring(substitutions, seed):
    # A small mutable suffix permits exhaustive comparison, including duplicate
    # characters, overlapping swaps, temporary disturbances, and residual errors.
    artifact = MasterSeed.from_seed(seed, identifier="test")
    damaged = list(artifact.text)
    damaged[-6], damaged[-5] = damaged[-5], damaged[-6]
    for position in (-1, -2)[:substitutions]:
        damaged[position] = CHARSET[CHARSET.index(damaged[position]) ^ 1]
    text = "".join(damaged)
    state = replace(_state(text), immutable=len(text) - 6)
    candidate = _correct_fixed(artifact.text, suspected_profile=Profile.MS)
    assert candidate is not None
    target = tuple(CHARSET.index(c) for c in artifact.text[3:])
    matches = 0
    for shape in indel._CHARACTER_CLASSES:
        if shape.inserted or shape.omitted:
            continue
        expected = {
            tuple(view)
            for view in indel._views(text, 48, shape, state.immutable, state.base)
            if sum(a != b for a, b in zip(view, target)) == substitutions
        }
        actual = {
            tuple(view)
            for view in search._known_swaps(state, shape, substitutions, candidate, monotonic() + 10)
        }
        assert actual == expected, (shape, substitutions, seed)
        matches += len(actual)
    assert matches


def test_minimum_distance_pruning_stops_at_the_proven_boundary():
    shape = indel._StructuralClass(0, 0, adjacent=3)
    for substitutions, covered in ((2, True), (3, False)):
        text = _substitute(SOURCE, substitutions)
        fixed = _correct_fixed(text, suspected_profile=Profile.MS)
        assert fixed is not None
        result = search._covered_candidates(_state(text), shape, 0, 0, fixed, (fixed,))
        assert (result == (fixed,)) is covered
    other_length = MasterSeed.from_seed(bytes(range(20)), identifier="test")
    witness = replace(fixed, artifact=other_length)
    assert search._covered_candidates(_state(text), shape, 0, 0, None, (witness,)) is None


def test_fixed_coverage_accounts_for_explicit_erasures_and_residual_substitutions():
    shape = indel._StructuralClass(0, 0, adjacent=1)
    for erasures, covered in ((2, True), (3, False)):
        text = SOURCE[:20] + "?" * erasures + SOURCE[20 + erasures :]
        result = search._covered_candidates(_state(text), shape, erasures, 1, None, ())
        assert (result == ()) is covered


def test_cancelled_indel_layer_is_distinct_from_retained_erasure_and_relocation():
    state = _state(REPORTED)
    fixed = _correct_fixed(REPORTED, suspected_profile=Profile.MS)
    assert fixed is not None
    adjacent = indel._StructuralClass(1, 1, adjacent=1)
    distant = indel._StructuralClass(1, 1, distant=1)
    assert (
        tuple(search._competitor_views(state, (48, adjacent, -1, 0), fixed, (fixed,), monotonic() + 10)) == ()
    )
    assert search._competitor_views(state, (48, adjacent, 0, 0), fixed, (fixed,), monotonic() + 10) is None
    assert search._competitor_views(state, (48, distant, -1, 0), fixed, (fixed,), monotonic() + 10) is None


def test_mask_duplicates_require_a_completed_covering_layer():
    single = indel._StructuralClass(0, 0, unit=4, corrupted=1)
    double = replace(single, corrupted=2)
    completed = {(48, single, 0, 1)}
    assert search._duplicate_layer((48, double, -4, 1), completed)
    assert not search._duplicate_layer((48, double, -4, 1), set())
    assert not search._duplicate_layer((48, double, 0, 0), completed)
    removed = indel._StructuralClass(1, 0, unit=4)
    masked_removed = replace(removed, corrupted=1)
    assert search._duplicate_layer((48, masked_removed, -4, 0), {(48, removed, 0, 0)})


@pytest.mark.parametrize("adjacent", (1, 2))
def test_cancelled_indel_bound_matches_exhaustive_alignments(adjacent):
    shape = indel._StructuralClass(1, 1, adjacent=adjacent)
    original = tuple(CHARSET.index(c) for c in SOURCE[3:])
    cancelled = 0
    for view in indel._views(SOURCE, 48, shape, 44, 3):
        values = tuple(view)
        if -1 in values:
            continue
        cancelled += 1
        assert sorted(values) == sorted(original)
        assert sum(a != b for a, b in zip(values, original)) <= 2 * adjacent
    assert cancelled


def test_group_duplicate_proofs_match_exhaustive_alignment_values():
    for text, simpler, duplicate in (
        (
            SOURCE,
            indel._StructuralClass(0, 0, unit=4, corrupted=1),
            indel._StructuralClass(0, 0, unit=4, corrupted=2),
        ),
        (
            SOURCE + "qpzr",
            indel._StructuralClass(1, 0, unit=4),
            indel._StructuralClass(1, 0, unit=4, corrupted=1),
        ),
    ):
        expected = {tuple(view) for view in indel._views(text, 48, simpler, 32, 3)}
        covered = {
            tuple(view)
            for view in indel._views(text, 48, duplicate, 32, 3)
            if tuple(view).count(-1) == simpler.erasures
        }
        assert covered == expected


@pytest.mark.parametrize("count", (1, 2, 3, 4))
@pytest.mark.parametrize("length", (16, 32, 64))
def test_deadline_returns_usable_fixed_candidate_with_incomplete_metadata(count, length):
    source = MasterSeed.from_seed(bytes(range(length)), identifier="test").text
    damaged = _substitute(source, count)
    clock = [0.0]
    original = search._search_fixed

    def fixed(*args):
        result = original(*args)
        clock[0] = 10.0
        return result

    with (
        patch.object(search, "monotonic", side_effect=lambda: clock[0]),
        patch.object(search, "_search_fixed", side_effect=fixed),
    ):
        candidates, complete = _run(damaged, target=len(source), deadline=10.0)
    assert not complete and len(candidates) == 1
    assert not candidates[0].search_complete
    assert candidates[0].artifact.text == source


def test_ineligible_fixed_candidate_cannot_prune_other_layers():
    calls = []

    def layer(state, frontier, results, deadline, *, allowed, views):
        calls.append(next(iter(frontier.values())))
        assert not results
        assert not allowed(_correct_fixed(REPORTED, suspected_profile=Profile.MS))
        return False

    with patch.object(search, "_search_target", side_effect=layer):
        candidates, complete = _run(REPORTED, allowed=lambda c: not isinstance(c.artifact, Share))
    assert not complete and not candidates and calls


def test_structural_candidate_filter_is_applied_before_collection():
    state = _state(REPORTED)
    shape = indel._StructuralClass(0, 0, unit=4, adjacent=1)
    frontier = indel._frontier((state,), frozenset((48,)))
    share = _correct_fixed(REPORTED, suspected_profile=Profile.MS)
    secret = _correct_fixed(SOURCE, suspected_profile=Profile.MS)
    assert share is not None and secret is not None
    outputs = iter((replace(share, edits=(), capture_volume=1), secret))
    views = iter(tuple(indel._views(REPORTED, 48, shape, 3, 3))[:2])
    results = {}
    with patch.object(indel._FixedCorrector, "correct", side_effect=lambda *args: next(outputs)):
        assert indel._search_target(
            replace(state, counts={shape: state.counts[shape]}),
            {(48, shape, 0, 0): frontier[48, shape, 0, 0]},
            results,
            None,
            allowed=lambda c: not isinstance(c.artifact, Share),
            views=views,
        )
    assert tuple(results) == (SOURCE,)


@pytest.mark.parametrize("target", (None, 48))
@pytest.mark.parametrize("change", ("omit", "insert", "omit_group", "insert_group"))
def test_alignment_discovered_candidate_matches_unpruned_search(target, change):
    damaged = {
        "omit": SOURCE[:19] + SOURCE[20:],
        "insert": SOURCE[:19] + "q" + SOURCE[19:],
        "omit_group": SOURCE[:20] + SOURCE[24:],
        "insert_group": SOURCE[:20] + "qpzr" + SOURCE[20:],
    }[change]
    lengths = TEXT_LENGTHS if target is None else (target,)
    contexts = tuple(CorrectionContext(Profile.MS, length, damaged[:3]) for length in lengths)
    reference, reference_complete = indel._search_many(contexts, damaged, primary=frozenset(lengths))
    candidates, complete = _run(damaged, target=target)
    assert complete and reference_complete
    assert len(candidates) == len(reference) == 1
    assert candidates[0].artifact.text == reference[0].artifact.text == SOURCE
    assert candidates[0].capture_volume == reference[0].capture_volume
    assert candidates[0].addend_hamming_weight == reference[0].addend_hamming_weight


def test_global_tiers_cross_lengths_and_deadline_does_not_restart():
    text = SOURCE + "qq"
    calls = []

    def layer(state, frontier, results, deadline, **kwargs):
        key, volume = next(iter(frontier.items()))
        calls.append((search._tier(key[1]), volume, state.target))
        assert deadline == 100.0
        return True

    with (
        patch.object(search, "monotonic", return_value=0.0),
        patch.object(search, "_search_target", side_effect=layer),
    ):
        candidates, complete = _run(text, deadline=100.0)
    assert complete and not candidates
    assert calls == sorted(calls, key=lambda call: call[:2])
    assert {call[2] for call in calls} == {48, 54}


def test_incomplete_primary_ties_are_suppressed():
    first = _correct_fixed(SOURCE, suspected_profile=Profile.MS)
    second = _correct_fixed(
        MasterSeed.from_seed(bytes(16), identifier="test").text, suspected_profile=Profile.MS
    )
    assert first is not None and second is not None
    calls = []

    def layer(state, frontier, results, deadline, **kwargs):
        volume = next(iter(frontier.values()))
        calls.append(volume)
        results[first.artifact.text] = replace(first, capture_volume=volume)
        results[second.artifact.text] = replace(second, capture_volume=volume)
        return False

    with patch.object(search, "_search_target", side_effect=layer):
        candidates, complete = _run(SOURCE + "q")
    assert not complete and candidates == () and calls


@pytest.mark.parametrize("later_volume", (50, 100))
def test_equal_or_better_competitor_at_another_length_is_not_pruned(later_volume):
    text = SOURCE + "qq"
    states = (_state(text), _state(text, 54))
    shapes = (indel._StructuralClass(2, 0), indel._StructuralClass(0, 1, unit=4))
    frontier = {(48, shapes[0], 0, 0): later_volume, (54, shapes[1], 0, 0): 100}
    calls = []

    def layer(state, frontier, results, deadline, **kwargs):
        calls.append(state.target)
        artifact = MasterSeed.from_seed(bytes(16 if state.target == 48 else 20), identifier="test")
        candidate = _correct_fixed(artifact.text, suspected_profile=Profile.MS)
        results[artifact.text] = replace(candidate, capture_volume=next(iter(frontier.values())))
        return True

    with patch.object(search, "_search_target", side_effect=layer):
        candidates, complete = search._search_competitors(states, frontier, monotonic() + 10, None)
    assert complete and calls == [54, 48]
    assert len(candidates) == (1 if later_volume == 50 else 2)
    assert all(c.capture_volume == later_volume for c in candidates)


def test_pruning_does_not_change_mass_admission():
    state = _state(REPORTED)
    frontier = indel._frontier((state,), frozenset((48,)))
    original = dict(frontier)
    search._search_competitors((state,), frontier, monotonic() + 10, None)
    assert frontier == original
    assert sum(frontier.values()) <= 2**65
