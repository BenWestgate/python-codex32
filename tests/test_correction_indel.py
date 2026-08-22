"""Transitional Gate 5 structural-search regression tests."""

import time

import pytest
from data.bip93_vectors import VECTOR_1, VECTOR_2

from codex32 import InvalidCorrectionInput, Profile, parse_codex32
from codex32.bech32 import CHARSET
from codex32.indel import search_codex32_corrections


def _replace_with_different_bech32(value: str, positions: list[int]) -> str:
    characters = list(value)
    for position in positions:
        first, second = ("Q", "P") if value.isupper() else ("q", "p")
        characters[position] = first if characters[position] != first else second
    return "".join(characters)


def _valid_master_seed(value: str) -> bool:
    return parse_codex32(value).profile is Profile.MS


def test_structural_search_rejects_oversized_input() -> None:
    with pytest.raises(InvalidCorrectionInput, match="at most 135"):
        search_codex32_corrections(
            "ms1" + "q" * 133,
            max_seconds=1,
            validator=_valid_master_seed,
        )


@pytest.mark.parametrize(
    ("damaged", "insertions", "deletions"),
    (
        (VECTOR_1["secret_s"][:20] + VECTOR_1["secret_s"][21:], 1, 0),
        (
            VECTOR_1["secret_s"][:20] + "p" + VECTOR_1["secret_s"][20:],
            0,
            1,
        ),
    ),
)
def test_search_corrects_single_insertion_or_deletion(damaged, insertions, deletions):
    """Structural search repairs one missing or extra input character."""
    result = search_codex32_corrections(
        damaged,
        max_seconds=2,
        max_workers=4,
        validator=_valid_master_seed,
    )

    assert not result.timed_out
    assert result.candidate is not None
    assert result.candidate.string == VECTOR_1["secret_s"]
    assert len(result.candidate.inserted) == insertions
    assert len(result.candidate.deleted) == deletions


def test_search_combines_substitution_insertion_and_deletion():
    """Each structural alignment is passed through the fast BCH decoder."""
    valid = VECTOR_2["share_A"].lower()
    damaged = valid[:10] + "q" + valid[10:]
    damaged = damaged[:32] + damaged[33:]
    characters = list(damaged)
    characters[40] = CHARSET[CHARSET.index(characters[40]) ^ 1]

    result = search_codex32_corrections(
        "".join(characters),
        max_seconds=6,
        max_workers=4,
        validator=_valid_master_seed,
    )

    assert not result.timed_out
    assert result.candidate is not None
    assert result.candidate.string == valid
    assert len(result.candidate.inserted) == 1
    assert len(result.candidate.deleted) == 1
    assert len(result.candidate.substituted) == 1


def test_structural_search_honors_time_limit():
    """An unfinished structural search returns promptly with timeout status."""
    valid = VECTOR_2["share_A"].lower()
    characters = list(valid)
    for position in (10, 17, 24, 31, 38):
        characters[position] = CHARSET[CHARSET.index(characters[position]) ^ 1]

    started = time.monotonic()
    result = search_codex32_corrections(
        "".join(characters),
        max_seconds=0.01,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.timed_out
    assert time.monotonic() - started < 0.5


def test_known_erasures_are_scored_by_search_space_size():
    """Known erasures cost one unknown Bech32 value each."""
    damaged = "ms1?????????????90qwertyuasdfghjklz56cr2femfphh9"
    expected = "ms12testa234567890qwertyuasdfghjklz56cr2femfphh9"

    result = search_codex32_corrections(
        damaged,
        max_seconds=0.05,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == expected
    assert len(result.candidate.erased) == 13
    assert len(result.candidate.substituted) == 0
    assert result.candidate.weight_bits == pytest.approx(65.0)
    assert not result.timed_out
    assert result.variants_tested == 1


def test_later_separator_character_is_treated_as_erasure():
    """A later '1' is damaged data, not a replacement separator."""
    valid = VECTOR_1["secret_s"]
    damaged = valid[:10] + "1" + valid[11:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert result.candidate.erased == ((11, "1", valid[10]),)


def test_extra_later_separator_character_can_be_deleted():
    """An extra '1' in data is eligible for the invalid-character fast path."""
    valid = VECTOR_1["secret_s"]
    damaged = valid[:20] + "1" + valid[20:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert result.candidate.deleted == ((21, "1"),)


def test_common_invalid_character_confusion_is_prioritized():
    """A documented visual confusion has the smallest erasure tie-breaker."""
    valid = "ms12testa234567890qwertyuasdfghjklz56cr2femfphh9"
    position = valid.index("8")
    damaged = valid[:position] + "b" + valid[position + 1 :]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert result.candidate.search_space_bits == pytest.approx(0.0)


def test_adjacent_swap_is_one_transposition():
    """BCH substitutions forming a swap are classified as one event."""
    valid = VECTOR_1["secret_s"]
    position = next(
        index for index in range(3, len(valid) - 1) if valid[index] != valid[index + 1]
    )
    characters = list(valid)
    characters[position], characters[position + 1] = (
        characters[position + 1],
        characters[position],
    )

    result = search_codex32_corrections(
        "".join(characters),
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert result.candidate.substituted == ()
    assert len(result.candidate.transposed) == 1


def test_adjacent_duplication_uses_fast_deduplicated_path():
    """An adjacent duplicated character is recognized before general search."""
    valid = VECTOR_1["secret_s"]
    position = 20
    damaged = valid[:position] + valid[position] + valid[position:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert not result.timed_out
    assert result.candidate is not None
    assert result.candidate.string == valid
    assert result.candidate.duplicated
    assert result.variants_tested < 5


def test_independent_deletions_are_reclassified_as_duplications():
    """Separate repeated characters retain duplication metadata."""
    valid = VECTOR_1["secret_s"]
    positions = (37, 43)
    damaged = valid
    for position in reversed(positions):
        damaged = damaged[:position] + damaged[position] + damaged[position:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=2,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert len(result.candidate.deleted) == 2
    assert len(result.candidate.duplicated) == 2


def test_complete_group_transposition_fast_path():
    """Swapped complete transcription groups are repaired as one class."""
    valid = VECTOR_1["secret_s"]
    damaged = valid[:4] + valid[8:12] + valid[4:8] + valid[12:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert any(group.kind == "transposed" for group in result.candidate.groups)


def test_complete_group_omission_fast_path():
    """A missing complete group is inserted as four BCH erasures."""
    valid = VECTOR_1["secret_s"]
    damaged = valid[:8] + valid[12:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert any(group.kind == "omitted" for group in result.candidate.groups)


def test_complete_group_duplication_fast_path():
    """An extra copied group is recognized and deleted before general search."""
    valid = VECTOR_1["secret_s"]
    damaged = valid[:12] + valid[8:12] + valid[12:]

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert any(len(block) == 4 for _position, block in result.candidate.duplicated)


def test_complete_erroneous_group_is_classified():
    """Four aligned BCH substitutions are reported as one erroneous group."""
    valid = VECTOR_1["secret_s"]
    damaged = _replace_with_different_bech32(valid, [8, 9, 10, 11])

    result = search_codex32_corrections(
        damaged,
        max_seconds=1,
        max_workers=2,
        validator=_valid_master_seed,
    )

    assert result.candidate is not None
    assert result.candidate.string == valid
    assert any(group.kind == "erroneous" for group in result.candidate.groups)
