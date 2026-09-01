"""Independent arithmetic evidence for the final Gate 3 structural envelope."""

from fractions import Fraction
from math import comb
from unittest.mock import patch

import pytest

from tools.gate3_capture import (
    FALSE_BOUND_DENOMINATOR,
    Shape,
    alignment_count,
    alignment_distribution,
    capture_volume,
    checksum_bits,
    classes,
    cross_length_classes,
    main,
    supported_shapes,
)


def test_cross_length_cli_rejects_the_single_target_erasure_count() -> None:
    with (
        patch("sys.argv", ["gate3_capture.py", "--observed-length", "48", "--erasures", "8"]),
        pytest.raises(SystemExit) as failure,
    ):
        main()
    assert failure.value.code == 2


def test_checksum_spaces_follow_expanded_lengths() -> None:
    assert checksum_bits("ms", 48) == 65
    assert checksum_bits("ms", 91) == 65
    assert checksum_bits("ms", 94) == 75


def test_checksum_gap_is_rejected() -> None:
    for length in (92, 93):
        try:
            checksum_bits("ms", length)
        except ValueError as error:
            assert "gap" in str(error)
        else:
            raise AssertionError("invalid expanded checksum length was accepted")


def test_supported_shape_families_are_exact() -> None:
    shapes = supported_shapes()
    characters = [shape for shape in shapes if shape.name.startswith("characters")]
    groups = [shape for shape in shapes if shape.name.startswith("groups")]

    assert len(characters) == 14
    assert len(groups) == 5
    assert all(0 < shape.inserted + shape.omitted <= 4 for shape in characters)
    assert all(0 < shape.inserted + shape.omitted <= 2 for shape in groups)


def test_first_share_character_alignment_table() -> None:
    expected = {
        (0, 4): 148_995,
        (1, 3): 610_170,
        (0, 3): 14_190,
        (0, 2): 990,
        (1, 2): 43_560,
        (0, 1): 45,
        (1, 1): 2_025,
        (2, 2): 980_100,
        (1, 0): 46,
        (2, 1): 46_575,
        (2, 0): 1_081,
        (3, 1): 729_675,
        (3, 0): 17_296,
        (4, 0): 211_876,
    }

    for (inserted, omitted), count in expected.items():
        shape = Shape("character", inserted, omitted)
        assert alignment_count(shape, 48, 3) == count


def test_first_and_confirmed_share_group_counts_are_exact() -> None:
    shapes = {
        (0, 1): Shape("group", 0, 1, 4),
        (1, 0): Shape("group", 1, 0, 4),
        (0, 2): Shape("group", 0, 2, 4),
        (1, 1): Shape("group", 1, 1, 4),
        (2, 0): Shape("group", 2, 0, 4),
    }

    assert {pair: alignment_count(shape, 48, 3) for pair, shape in shapes.items()} == {
        (0, 1): 11,
        (1, 0): 12,
        (0, 2): 55,
        (1, 1): 121,
        (2, 0): 78,
    }
    assert {pair: alignment_count(shape, 48, 8) for pair, shape in shapes.items()} == {
        (0, 1): 10,
        (1, 0): 11,
        (0, 2): 45,
        (1, 1): 100,
        (2, 0): 66,
    }


def test_two_missing_groups_fit_strict_result_bound() -> None:
    shape = Shape("two-groups", omitted=2, unit=4)
    volume = capture_volume(shape, 48, 3, substitutions=0)

    assert volume == 55 * 32**8
    assert FALSE_BOUND_DENOMINATOR * volume < 2**65


def test_two_each_with_two_substitutions_exceeds_strict_result_bound() -> None:
    shape = Shape("two-each", inserted=2, omitted=2)
    volume = capture_volume(shape, 48, 3, substitutions=2)

    assert volume == comb(45, 2) ** 2 * 32**2 * comb(43, 2) * 31**2
    assert FALSE_BOUND_DENOMINATOR * volume > 2**65


def test_explicit_erasures_are_counted_once_in_the_fixed_volume() -> None:
    shape = Shape("one-each", inserted=1, omitted=1)

    assert capture_volume(shape, 48, 3, substitutions=0, explicit_erasures=1) == (comb(45, 1) ** 2 * 32**2)
    assert all(item.substitutions == 0 for item in classes("ms", 48, explicit_erasures=8))
    assert classes("ms", 48, explicit_erasures=9) == ()


def test_every_reported_safety_result_uses_exact_cumulative_inequality() -> None:
    for hrp, length, prefix in (
        ("ms", 48, None),
        ("ms", 48, "ms10test"),
        ("ms", 74, None),
        ("ms", 127, None),
        ("cl", 74, None),
    ):
        space = 1 << checksum_bits(hrp, length)
        for item in classes(hrp, length, prefix):
            assert item.safe == (FALSE_BOUND_DENOMINATOR * item.cumulative_volume < space)


def test_cross_length_bound_is_strict_for_every_40_to_56_observation() -> None:
    for observed in range(40, 57):
        admitted = [item for item in cross_length_classes(observed) if item.admitted]
        if not admitted:
            continue
        maximum = max(item.checksum_bits for item in admitted)
        cumulative = sum(item.volume << (maximum - item.checksum_bits) for item in admitted)

        assert FALSE_BOUND_DENOMINATOR * cumulative < 1 << maximum


def test_automatic_48_compatible_cumulative_bounds_are_exact() -> None:
    expected = {
        40: Fraction(55, 33_554_432),
        44: Fraction(49_550_963, 8_796_093_022_208),
        45: Fraction(9_244_785, 562_949_953_421_312),
        46: Fraction(48_584_517_267, 18_014_398_509_481_984),
        47: Fraction(1_229_275_380_015, 1_152_921_504_606_846_976),
        48: Fraction(127_246_374_791_303, 36_893_488_147_419_103_232),
        49: Fraction(3_853_028_054_033, 18_446_744_073_709_551_616),
        50: Fraction(183_552_742_479_439, 36_893_488_147_419_103_232),
        51: Fraction(130_377_745_889, 576_460_752_303_423_488),
        52: Fraction(23_225_724_342_457, 9_223_372_036_854_775_808),
        56: Fraction(164_824_085_127_117, 18_446_744_073_709_551_616),
    }

    for observed, bound in expected.items():
        admitted = [item for item in cross_length_classes(observed) if item.admitted]
        actual = sum(
            (Fraction(item.volume, 1 << item.checksum_bits) for item in admitted),
            Fraction(),
        )

        assert actual == bound
        assert actual < Fraction(1, FALSE_BOUND_DENOMINATOR)


def test_every_secondary_stretch_shape_admits_pure_structural_recovery() -> None:
    requested = tuple(
        shape
        for shape in supported_shapes()
        if shape.name != "fixed"
        and (
            shape.unit == 1
            and shape.inserted + shape.omitted <= 3
            or shape.unit == 4
            and shape.inserted + shape.omitted <= 2
        )
    )

    for target in (54, 61, 67):
        for shape in requested:
            layers = cross_length_classes(target + shape.delta)
            assert any(
                item.admitted
                and item.target_length == target
                and item.shape == shape.name
                and item.remaining_explicit == 0
                and item.substitutions == 0
                for item in layers
            )


def test_secondary_third_order_substitution_frontiers_are_exact() -> None:
    expected = {
        (54, "characters-0i-3o"): {0, 1},
        (61, "characters-0i-3o"): {0, 1},
        (67, "characters-0i-3o"): {0, 1},
        (54, "characters-1i-2o"): {0, 1, 2},
        (61, "characters-1i-2o"): {0, 1, 2},
        (67, "characters-1i-2o"): {0, 1},
        (54, "characters-2i-1o"): {0, 1, 2},
        (61, "characters-2i-1o"): {0, 1, 2},
        (67, "characters-2i-1o"): {0, 1, 2},
        (54, "characters-3i-0o"): {0, 1, 2, 3},
        (61, "characters-3i-0o"): {0, 1, 2, 3},
        (67, "characters-3i-0o"): {0, 1, 2, 3},
    }

    for (target, name), substitutions in expected.items():
        shape = next(item for item in supported_shapes() if item.name == name)
        admitted = {
            item.substitutions
            for item in cross_length_classes(target + shape.delta)
            if item.admitted
            and item.target_length == target
            and item.shape == name
            and item.remaining_explicit == 0
        }
        assert admitted == substitutions


def test_cross_length_frontier_uses_actual_explicit_and_immutable_domains() -> None:
    character = Shape("character", inserted=1)
    group = Shape("group", inserted=1, unit=4)

    assert alignment_distribution(character, 49, 48, 3, (12,)) == {0: 1, 1: 45}
    assert alignment_distribution(character, 49, 48, 8, (12,)) == {0: 1, 1: 40}
    assert alignment_distribution(group, 52, 48, 3, (3, 4, 5, 8)) == {2: 1, 3: 1, 4: 10}

    for prefix in ("ms1", "ms10test"):
        for observed in range(40, 57):
            for erasures in (1, 4, 8):
                positions = tuple(range(len(prefix), min(observed, len(prefix) + erasures)))
                admitted = [
                    item
                    for item in cross_length_classes(
                        observed,
                        immutable_prefix=prefix,
                        explicit_positions=positions,
                    )
                    if item.admitted
                ]
                if not admitted:
                    continue
                maximum = max(item.checksum_bits for item in admitted)
                cumulative = sum(item.volume << (maximum - item.checksum_bits) for item in admitted)
                assert FALSE_BOUND_DENOMINATOR * cumulative < 1 << maximum


def test_unknown_length_offers_full_intermediate_families_and_truncates_by_rank() -> None:
    layers = cross_length_classes(46, reduced_targets=())
    intermediate = [item for item in layers if not item.primary]

    assert any(item.target_length == 54 and item.shape == "groups-0gi-2go" for item in intermediate)
    ranks = sorted({item.volume for item in intermediate})
    admitted = {item.volume for item in intermediate if item.admitted}
    if admitted:
        assert admitted == set(ranks[: ranks.index(max(admitted)) + 1])
