"""Deadline regression for mixed-case embedded recovery."""

from time import monotonic

from codex32 import Profile
from codex32._cli_input import _case_interpretation, _scheduled_candidates


def test_embedded_mixed_case_completes_both_interpretations_within_deadline() -> None:
    source = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"
    damaged = "ms10testsxPxxxxxPxxxxxPxxxxxPxxxxxP4nzvca9cmczlw"
    interpretation = _case_interpretation(damaged, "", (Profile.MS,), None)

    assert interpretation is not None
    direct, normalized, erased, _prefix = interpretation
    assert direct is None
    separator = normalized.rfind("1")
    deadline = monotonic() + 10

    candidates, complete = _scheduled_candidates(
        normalized,
        erased,
        Profile.MS,
        None,
        normalized[: separator + 1],
        deadline=deadline,
    )

    assert complete
    assert len(candidates) == 1
    assert candidates[0].artifact.text == source
