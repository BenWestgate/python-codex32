"""Length diagnostics preserve generic failures and correction eligibility."""

import pytest

from codex32 import Profile
from codex32._cli_input import InputError, _parse, _prefixed_input_error, _suggestions
from codex32.errors import InvalidChecksum, InvalidLength


@pytest.mark.parametrize(
    ("length", "message", "cause"),
    (
        (10, "codex32 string must contain at least 21 characters", InvalidLength),
        (92, "expanded codex32 lengths 94 and 95 are invalid", InvalidLength),
        (93, "expanded codex32 lengths 94 and 95 are invalid", InvalidLength),
        (1022, "expanded codex32 codeword exceeds 1023 symbols", InvalidLength),
        (48, "The checksum does not match.", InvalidChecksum),
        (
            95,
            (
                "This input has 95 characters. A Bitcoin master-seed backup must have "
                "exactly 48, 54, 61, 67, 74, or 127 characters."
            ),
            InvalidChecksum,
        ),
    ),
)
def test_generic_length_profile_length_and_checksum_diagnostics(length, message, cause):
    value = "ms10fauxs" + "x" * (length - 9)
    with pytest.raises(InputError) as failure:
        _parse(value, (Profile.MS,))
    assert str(failure.value) == message
    assert isinstance(failure.value.__cause__, cause)
    if cause is InvalidLength:
        assert _prefixed_input_error(failure.value, value, "MS1", []) == message


def test_reported_invalid_length_vector_in_neutral_entry():
    value = "ms10fauxs" + "x" * 73 + "r335l5tv88js3"
    with pytest.raises(InputError, match="This input has 95 characters") as failure:
        _parse(value, (Profile.MS,))
    assert _prefixed_input_error(failure.value, value, "", []) == str(failure.value)


def test_unknown_profile_does_not_replace_checksum_failure_with_a_length_guess():
    with pytest.raises(InputError, match="The checksum does not match"):
        _parse("zz10fauxs" + "x" * 87, (Profile.MS,))


def test_opaque_correction_skips_lengths_inside_the_checksum_gap():
    # 90 characters: nearby targets 92 and 93 would expand to the forbidden 94/95.
    source = "zz10tests" + "q" * 68 + "eqq7qmrek3dw3"
    damaged = source[:87] + "p" + source[88:]

    assert [candidate.artifact.text for candidate in _suggestions(damaged, "", None, [])] == [source]
