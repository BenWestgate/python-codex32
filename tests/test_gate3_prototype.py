"""Behavior and work evidence for the Gate 3 alignment prototype."""

from data.bip93_vectors import VECTOR_1

from codex32 import Profile
from tools.gate3_capture import supported_shapes
from tools.gate3_prototype import benchmark, candidates

SOURCE = VECTOR_1["secret_s"]
SHAPES = {shape.name: shape for shape in supported_shapes()}


def _groups(text: str) -> list[str]:
    return [text[start : start + 4] for start in range(0, len(text), 4)]


def test_character_insertion_and_omission_recover_source() -> None:
    inserted = SOURCE[:14] + "q" + SOURCE[14:]
    omitted = SOURCE[:19] + SOURCE[20:]

    extra_result = benchmark(inserted, Profile.MS, len(SOURCE), SHAPES["arbitrary-1i-0o"])
    missing_result = benchmark(omitted, Profile.MS, len(SOURCE), SHAPES["arbitrary-0i-1o"])

    assert extra_result["results"] == missing_result["results"] == [SOURCE]
    assert extra_result["checked"] <= len(SOURCE) - 2
    assert missing_result["checked"] == len(SOURCE) - 3


def test_balanced_character_edits_finish_complete_class() -> None:
    damaged = SOURCE[:12] + "q" + SOURCE[12:27] + SOURCE[28:]
    result = benchmark(damaged, Profile.MS, len(SOURCE), SHAPES["arbitrary-1i-1o"])

    assert result["results"] == [SOURCE]
    assert 0 < result["checked"] <= (len(SOURCE) - 3) ** 2


def test_two_missing_groups_use_preserved_cli_boundaries() -> None:
    grouped = _groups(SOURCE)
    damaged = " ".join(group for index, group in enumerate(grouped) if index not in (3, 8))
    result = benchmark(damaged, Profile.MS, len(SOURCE), SHAPES["groups-2o"])

    assert result["checked"] == 55
    assert result["results"] == [SOURCE]


def test_four_extra_groups_are_bounded_and_recover_source() -> None:
    grouped = _groups(SOURCE)
    for index in (10, 7, 4, 2):
        grouped.insert(index, "qqqq")
    damaged = " ".join(grouped)
    result = benchmark(damaged, Profile.MS, len(SOURCE), SHAPES["groups-4i"])

    assert result["checked"] <= 1_365
    assert result["results"] == [SOURCE]


def test_candidate_generator_rejects_wrong_length_delta() -> None:
    values = candidates(SOURCE, Profile.MS, len(SOURCE), SHAPES["arbitrary-1i-0o"])

    assert tuple(values) == ()


def test_character_candidates_preserve_uppercase_prefix() -> None:
    source = SOURCE.upper()
    damaged = source[:20] + source[21:]
    values = candidates(damaged, Profile.MS, len(source), SHAPES["arbitrary-0i-1o"])

    assert all(value.startswith("MS1") for value in values)
