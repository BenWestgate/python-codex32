"""Both interfaces align transcriptions without completing or interpreting them."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codex32._confirmation import _compact, _entered_groups


@pytest.mark.parametrize(
    ("expected", "observed", "groups", "changed"),
    [
        ("ABCDEFGH", "ABCDXEFGH", ["ABCD", "XEFGH"], {1}),
        ("ABCDDEFG", "ABCDEFG", ["ABCD", "EFG"], {1}),
        ("ABCDEFGHJKLMNPQR", "ABCDFGHJKLMNXPQR", ["ABCD", "FGH", "JKLM", "NXPQR"], {1, 3}),
        ("ABCDEFGH", "ABCD B1!O", ["ABCD ", "B1!O"], {1}),
        ("ABCDEFKG", "ABCDEFKG", ["ABCD", "EFKG"], {1}),
    ],
)
def test_alignment_preserves_leading_matches_and_invalid_characters(
    expected: str, observed: str, groups: list[str], changed: set[int]
) -> None:
    assert _entered_groups(observed, expected) == (groups, changed)


def test_input_over_twice_the_card_is_all_wrong_without_alignment() -> None:
    assert _entered_groups("ABCDABCDA bc", "ABCD") == (["ABCD", "ABCD", "Abc"], {0, 1, 2})


@given(st.text(alphabet="ABCD!? 1K", max_size=20))
def test_alignment_only_returns_characters_the_operator_entered(observed: str) -> None:
    groups, changed = _entered_groups(observed, "ABCDABCD")
    assert _compact("".join(groups)) == _compact(observed)
    assert bool(changed) == (_compact(observed) != "abcdabcd")
