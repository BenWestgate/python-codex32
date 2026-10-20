"""Incremental alignment agrees with independent full polynomial evaluation."""

from random import Random

import pytest

from codex32._alignment import _IncrementalSyndromes, _View
from codex32.correction import (
    _ALIGNMENT_CACHE_SIZE,
    _LONG_SPEC,
    _SHORT_SPEC,
    _pack_syndromes,
    _residue,
    _syndrome_alignment,
    _syndromes,
)


def test_syndrome_alignment_cache_is_bounded_for_untrusted_hrps():
    _syndrome_alignment.cache_clear()

    for index in range(_ALIGNMENT_CACHE_SIZE + 5):
        _syndrome_alignment(_SHORT_SPEC, f"attacker{index}", 45)

    info = _syndrome_alignment.cache_info()
    assert info.maxsize == _ALIGNMENT_CACHE_SIZE
    assert info.currsize == _ALIGNMENT_CACHE_SIZE


def test_syndrome_alignment_cache_fits_one_unknown_length_search():
    observed = 50
    targets = sorted({observed + delta for delta in (*range(-4, 5), -8, 8)})
    _syndrome_alignment.cache_clear()

    first = [_syndrome_alignment(_SHORT_SPEC, "generic", target) for target in targets]
    before = _syndrome_alignment.cache_info()
    second = [_syndrome_alignment(_SHORT_SPEC, "generic", target) for target in targets]
    after = _syndrome_alignment.cache_info()

    assert len(targets) == _ALIGNMENT_CACHE_SIZE
    assert all(left is right for left, right in zip(first, second, strict=True))
    assert after.misses == before.misses
    assert after.hits == before.hits + len(targets)


def test_syndrome_alignment_cache_still_reuses_recent_entries():
    _syndrome_alignment.cache_clear()
    first = _syndrome_alignment(_SHORT_SPEC, "ms", 45)
    before = _syndrome_alignment.cache_info()

    second = _syndrome_alignment(_SHORT_SPEC, "ms", 45)

    after = _syndrome_alignment.cache_info()
    assert first is second
    assert after.hits == before.hits + 1


@pytest.mark.parametrize(
    ("hrp", "length", "spec"),
    (
        ("ms", 45, _SHORT_SPEC),
        ("bip39_12w", 46, _SHORT_SPEC),
        ("ms", 124, _LONG_SPEC),
    ),
)
def test_incremental_composition_matches_polynomial(hrp, length, spec):
    rng = Random(37)
    source = tuple(rng.randrange(-1, 32) for _ in range(length))
    base = _View(source, ((0, length),), length)
    views = [base, base.swap(7, 25, 1), base.swap(8, 32, 4)]
    views += [
        base.splice(9, 1, 0).splice(28, 0, 1),
        base.splice(8, 4, 0).splice(24, 0, 4),
        base.swap(10, 11, 1).splice(11, 0, 1).splice(30, 1, 0),
        base.splice(8, 0, 4).swap(8, 28, 4).splice(16, 4, 0),
    ]
    incremental = _IncrementalSyndromes(_syndrome_alignment(spec, hrp, length), source)
    for view in views:
        expected = _pack_syndromes(
            _syndromes(spec, _residue(spec, hrp, [max(v, 0) for v in view]), target=True)
        )
        assert incremental.packed(view) == expected
        explicit = tuple(i for i, value in enumerate(source) if value < 0)
        assert sorted(p for p, _ in view.unknown_positions(explicit)) == [
            i for i, v in enumerate(view) if v < 0
        ]


def test_group_mask_and_overlapping_edits_match_polynomial():
    source = tuple(range(32)) + tuple(range(13))
    view = _View(source, ((0, 45),), 45).mask(5, 4).swap(5, 29, 4)
    view = view.splice(12, 1, 0).splice(20, 0, 1)
    engine = _IncrementalSyndromes(_syndrome_alignment(_SHORT_SPEC, "ms", 45), source)
    assert engine.packed(view) == _pack_syndromes(
        _syndromes(_SHORT_SPEC, _residue(_SHORT_SPEC, "ms", [max(v, 0) for v in view]), target=True)
    )
    assert sorted(p for p, _ in view.unknown_positions(())) == [i for i, v in enumerate(view) if v < 0]


def test_character_sphere_matches_independent_small_breadth_first_search():
    from codex32.indel import _CHARACTER_CLASSES, _FIXED, _views

    original = (0, 1, 2)
    levels = [set() for _ in range(5)]
    levels[0].add(original)
    for distance in range(4):
        for word in levels[distance]:
            for i in range(len(word) + 1):
                levels[distance + 1].add(word[:i] + (-1,) + word[i:])
            for i in range(len(word)):
                levels[distance + 1].add(word[:i] + word[i + 1 :])
                for j in range(i + 1, len(word)):
                    cost = 1 if j == i + 1 else 2
                    if distance + cost <= 4:
                        changed = list(word)
                        changed[i], changed[j] = changed[j], changed[i]
                        levels[distance + cost].add(tuple(changed))
    expected = set.union(*levels)
    actual = set()
    for shape in (_FIXED, *_CHARACTER_CLASSES):
        target = 6 - shape.delta
        if target >= 3:
            actual.update(tuple(v) for v in _views("ms1qpz", target, shape, 3, 3))
    assert actual == expected


def test_group_sphere_matches_independent_small_breadth_first_search():
    from codex32.indel import _FIXED, _GROUP_CLASSES, _views

    original = ((0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11))
    levels = [set() for _ in range(3)]
    levels[0].add(original)
    for distance in range(2):
        for word in levels[distance]:
            for i in range(len(word) + 1):
                levels[distance + 1].add(word[:i] + ((-1,) * 4,) + word[i:])
            for i in range(len(word)):
                levels[distance + 1].add(word[:i] + word[i + 1 :])
                levels[distance + 1].add(word[:i] + ((-1,) * 4,) + word[i + 1 :])
                for j in range(i + 1, len(word)):
                    cost = 1 if j == i + 1 else 2
                    if distance + cost <= 2:
                        changed = list(word)
                        changed[i], changed[j] = changed[j], changed[i]
                        levels[distance + cost].add(tuple(changed))
    expected = {(12,) + sum(word, ()) for word in set.union(*levels)}
    from codex32.bech32 import CHARSET

    text = "ms1" + CHARSET[12] + "".join(CHARSET[i] for i in range(12))
    actual = set()
    for shape in (_FIXED, *_GROUP_CLASSES):
        actual.update(tuple(v) for v in _views(text, len(text) - shape.delta, shape, 3, 3))
    assert actual == expected


def test_raw_admission_bounds_cover_generated_erasure_strata():
    from collections import Counter

    from codex32.indel import _CLASSES, _alignment_counts, _views

    for text in ("ms1qp?", "ms1qqpzr9x8?"):
        for shape in _CLASSES:
            target = len(text) - shape.delta
            if target < 3:
                continue
            counts = Counter(
                sum(v < 0 for v in view) - shape.erasures for view in _views(text, target, shape, 3, 3)
            )
            bound = _alignment_counts(shape, text, target, 3)
            assert all(
                count <= bound.get(remaining, 0)
                for remaining, count in counts.items()
                if 0 <= remaining + shape.erasures <= 8
            )


@pytest.mark.parametrize(
    ("shape_args", "swaps", "masked_groups"),
    (
        ({"adjacent": 1}, ((17, 18),), ()),
        ({"distant": 1}, ((17, 30),), ()),
        ({"unit": 4, "adjacent": 1}, ((16, 20),), ()),
        ({"unit": 4, "distant": 1}, ((12, 32),), ()),
        ({"unit": 4, "corrupted": 1}, (), (16,)),
    ),
)
def test_structural_alignment_leaves_bch_capacity_for_substitutions(shape_args, swaps, masked_groups):
    from dataclasses import replace

    from codex32 import CorrectionContext, MasterSeed, Profile
    from codex32.bech32 import CHARSET
    from codex32.indel import _CLASSES, _frontier, _prepare, _search_target, _StructuralClass

    source = MasterSeed.from_seed(bytes(range(16)), identifier="test").text
    chars = list(source)
    width = shape_args.get("unit", 1)
    for p, q in swaps:
        chars[p : p + width], chars[q : q + width] = chars[q : q + width], chars[p : p + width]
    for p in masked_groups:
        chars[p : p + 4] = [CHARSET[CHARSET.index(c) ^ 1] for c in chars[p : p + 4]]
    for p in (10, 38, 42)[: 2 if masked_groups else 3]:
        chars[p] = CHARSET[CHARSET.index(chars[p]) ^ 1]
    context = CorrectionContext(Profile.MS, len(source))
    state = _prepare(context, "".join(chars), _CLASSES)
    assert state is not None
    shape = _StructuralClass(0, 0, **shape_args)
    frontier = _frontier((state,), frozenset((len(source),)))
    results = {}
    assert _search_target(replace(state, counts={shape: state.counts[shape]}), frontier, results, None)
    assert source in results


@pytest.mark.parametrize(("interrupt_required", "tie"), ((True, False), (False, False), (False, True)))
def test_only_unique_optional_timeout_candidate_can_be_surfaced(interrupt_required, tie):
    from unittest.mock import patch

    from codex32 import CorrectionContext, MasterSeed, Profile
    from codex32.correction import CorrectionCandidate
    from codex32.indel import _FIXED, _search_many

    first = MasterSeed.from_seed(bytes(16), identifier="test")
    second = MasterSeed.from_seed(bytes(range(16)), identifier="test")
    candidate = CorrectionCandidate(first, (), 1 << 60, 0, 1, None)

    def search(state, frontier, results, deadline):
        if _FIXED in state.counts:
            return True
        required = all(s.unit == 4 or s.distance <= 2 for s in state.counts)
        results[first.text] = candidate
        if tie:
            results[second.text] = CorrectionCandidate(second, (), 1 << 60, 0, 2, None)
        return required and not interrupt_required

    with patch("codex32.indel._search_target", side_effect=search):
        candidates, complete = _search_many(
            (CorrectionContext(Profile.MS, 48),), "ms1" + "q" * 45, primary=frozenset((48,))
        )
    assert not complete
    if interrupt_required or tie:
        assert candidates == ()
    else:
        assert len(candidates) == 1 and candidates[0].artifact == first
        assert not candidates[0].search_complete


def test_group_operations_preserve_partial_display_edges():
    from codex32.indel import _GROUP_CLASSES, _views

    for shape in _GROUP_CLASSES:
        text = "ms1qqpzry9x8gf2tpz"
        for view in _views(text, len(text) - shape.delta, shape, 3, 3):
            assert view[0] == 0
            assert view[-2:] == (1, 2)


def test_global_frontier_admits_exact_ceiling_but_rejects_larger_batch():
    from unittest.mock import patch

    from codex32.indel import _FIXED, _frontier

    layers = ((1, 1, (48, _FIXED, 0, 0)), (1, 1, (54, _FIXED, 0, 0)))
    with patch("codex32.indel._layers", return_value=iter(layers)):
        assert _frontier((object(),), frozenset((48, 54))) == {key: volume for volume, _bits, key in layers}
    with patch("codex32.indel._layers", return_value=iter(layers[:1])):
        assert _frontier((object(),), frozenset((48,))) == {layers[0][2]: 1}

    with patch("codex32.indel._layers", return_value=iter((*layers, (1, 1, (61, _FIXED, 0, 0))))):
        assert _frontier((object(),), frozenset((48, 54, 61))) == {}


@pytest.mark.parametrize(("byte_length", "erasures"), ((16, 13), (64, 15)))
@pytest.mark.parametrize("known", (False, True))
def test_full_consecutive_erasure_capacity_at_inclusive_shared_ceiling(byte_length, erasures, known):
    from codex32 import CorrectionContext, MasterSeed, Profile, correct

    source = MasterSeed.from_seed(bytes(range(byte_length)), identifier="test").text
    damaged = source[:10] + "?" * erasures + source[10 + erasures :]
    result = correct(CorrectionContext(Profile.MS, len(source) if known else None), damaged)
    assert len(result) == 1 and result[0].artifact.text == source
    assert result[0].search_complete
    assert result[0].capture_volume == 32**erasures


def test_failed_alignment_does_not_scan_or_materialize_the_body():
    from unittest.mock import patch

    from codex32.correction import _FixedCorrector
    from codex32.profiles import Profile

    source = tuple(i % 32 for i in range(45))
    view = _View(source, ((0, 45),), 45).swap(8, 30, 1)
    solver = _FixedCorrector(Profile.MS, 45, False, 0)
    packed = _IncrementalSyndromes(solver.alignment, source).packed(view)
    with (
        patch("codex32.correction._aligned_syndromes", side_effect=AssertionError("full syndrome scan")),
        patch.object(_View, "__iter__", side_effect=AssertionError("body materialized")),
    ):
        assert solver.correct(view, (), (), packed) is None


def test_unknown_length_input_is_bounded_before_normalization():
    from codex32 import CorrectionContext, Profile, correct

    class Oversized(str):
        def replace(self, *args, **kwargs):
            pytest.fail("oversized input was normalized")

    assert correct(CorrectionContext(Profile.MS), Oversized("ms1" + "q" * 4096)) == ()
