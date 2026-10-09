"""Deadline regression for mixed-case embedded recovery."""

from dataclasses import replace
from time import monotonic

import pytest

from codex32 import Profile
from codex32._cli_input import _case_interpretation, _correction_candidates, _scheduled_candidates

SOURCE = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"


@pytest.mark.parametrize(
    ("damaged", "erasure_fixes", "normalized_fixes"),
    [
        # Five minority-case P: five erasures are correctable, five substitutions are not.
        ("ms10testsxPxxxxxPxxxxxPxxxxxPxxxxxP4nzvca9cmczlw", True, False),
        # Fifteen minority-case X, one mistyped: fifteen erasures are not correctable,
        # one substitution after case normalization is.
        ("ms10testsXXXXXXXPXXXXXXXxxxxxxxxxxx4nzvca9cmczlw", False, True),
    ],
)
def test_embedded_mixed_case_recovers_either_sole_interpretation_within_deadline(
    damaged: str, erasure_fixes: bool, normalized_fixes: bool
) -> None:
    interpretation = _case_interpretation(damaged, "", (Profile.MS,), None)

    assert interpretation is not None
    direct, normalized, erased, _prefix = interpretation
    assert direct is None
    immutable = normalized[: normalized.rfind("1") + 1]
    for value, fixes in ((erased, erasure_fixes), (normalized, normalized_fixes)):
        alone, alone_complete, _deadline = _correction_candidates(
            value, Profile.MS, None, immutable, deadline=monotonic() + 10, required_only=True
        )
        assert alone_complete
        assert [candidate.artifact.text for candidate in alone] == ([SOURCE] if fixes else [])

    candidates, complete = _scheduled_candidates(
        normalized,
        erased,
        Profile.MS,
        None,
        immutable,
        deadline=monotonic() + 10,
    )

    # The exhaustive optional search may truncate at the deadline; the
    # candidate must still be found and must report that truncation.
    assert [candidate.artifact.text for candidate in candidates] == [SOURCE]
    assert candidates[0].search_complete is complete


def test_scheduled_truncation_survives_a_complete_later_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    damaged = "ms10testsxPxxxxxPxxxxxPxxxxxPxxxxxP4nzvca9cmczlw"
    interpretation = _case_interpretation(damaged, "", (Profile.MS,), None)
    assert interpretation is not None
    _direct, normalized, erased, _prefix = interpretation
    immutable = normalized[: normalized.rfind("1") + 1]
    found, _complete, _deadline = _correction_candidates(
        erased, Profile.MS, None, immutable, deadline=monotonic() + 10, required_only=True
    )
    full_searches: list[str] = []

    def truncated_first(value: str, *_args: object, **kwargs: object) -> tuple[object, bool, float]:
        if kwargs.get("required_only"):
            return (), True, 0.0
        assert kwargs.get("optional_only") is True
        full_searches.append(value)
        if len(full_searches) == 1:
            return (replace(found[0], search_complete=False),), False, 0.0
        return (), True, 0.0

    monkeypatch.setattr("codex32._cli_input._correction_candidates", truncated_first)

    candidates, complete = _scheduled_candidates(normalized, erased, Profile.MS, None, immutable)

    assert full_searches == [erased, normalized]
    assert not complete
    assert [(candidate.artifact.text, candidate.search_complete) for candidate in candidates] == [
        (SOURCE, False)
    ]
