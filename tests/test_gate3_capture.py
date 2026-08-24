"""Independent arithmetic evidence for the Gate 3 structural envelope."""

from tools.gate3_capture import (
    FALSE_BOUND_DENOMINATOR,
    Shape,
    alignment_count,
    capture_volume,
    checksum_bits,
    classes,
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


def test_twelve_unknown_symbols_fail_regular_bound_without_alignment_cost() -> None:
    shape = Shape("known-burst", omitted=12, burst=True)
    volume = capture_volume(shape, "ms", 48, substitutions=0)

    assert volume >= 32**12
    assert FALSE_BOUND_DENOMINATOR * 32**12 > 2**65


def test_arbitrary_alignment_count_uses_combinations() -> None:
    shape = Shape("two-each", inserted=2, omitted=2)

    assert alignment_count(shape, "ms", 48) == 980_100


def test_group_alignment_uses_cli_four_character_boundaries() -> None:
    omitted = Shape("two-groups", omitted=8, grouped=True)
    inserted = Shape("four-groups", inserted=16, grouped=True)

    assert alignment_count(omitted, "ms", 48) == 55
    assert alignment_count(inserted, "ms", 48) == 1_365


def test_regular_policy_rejects_unsafe_burst_and_mixed_layers() -> None:
    result = classes("ms", 48, grouped=True)
    by_key = {(item.shape, item.substitutions): item for item in result}

    assert by_key[("burst-9o", 0)].safe
    assert not by_key[("burst-10o", 0)].safe
    assert by_key[("arbitrary-2i-2o", 2)].safe
    assert not by_key[("arbitrary-2i-2o", 3)].safe


def test_every_safe_class_satisfies_exact_cumulative_inequality() -> None:
    for hrp, length in (("ms", 48), ("ms", 74), ("ms", 127), ("cl", 74)):
        space = 1 << checksum_bits(hrp, length)
        for item in classes(hrp, length, grouped=True):
            assert item.safe == (FALSE_BOUND_DENOMINATOR * item.cumulative_volume < space)
