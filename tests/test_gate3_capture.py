"""Independent arithmetic evidence for the final Gate 3 structural envelope."""

from math import comb

from tools.gate3_capture import (
    FALSE_BOUND_DENOMINATOR,
    Shape,
    alignment_count,
    capture_volume,
    checksum_bits,
    classes,
    supported_shapes,
)


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
