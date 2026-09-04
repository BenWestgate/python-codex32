# fmt: off
# Bounded stdin and deliberately small interactive codex32 entry.
# ruff: noqa: I001

from __future__ import annotations

import contextlib
import difflib
import os
import sys
from collections.abc import Iterator
from time import monotonic
from typing import Any, Literal

from codex32.bech32 import CHARSET
from codex32.bip93 import Secret, Share, _validate_basis_prefix, _validate_recovery_prefix, parse_codex32
from codex32.correction import CorrectionCandidate, CorrectionContext, _best
from codex32.errors import CodexError, DuplicateShareIndex, ExistingTargetIndex, InvalidChecksum
from codex32.errors import MismatchedIdentifier, MismatchedPayloadLength, MismatchedProfile
from codex32.errors import MismatchedThreshold, SecretInRecoverySet
from codex32.profiles import Profile, _profile_rules
from codex32.profiles.ms32 import TEXT_LENGTHS, _text_length

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025

_line_editor: Any
try:
    import readline as _line_editor
except ImportError:
    _line_editor = None

class InputError(Exception): pass

def _stderr(text: str, *, end: str = "\n") -> None:
    print(text, end=end, file=sys.stderr, flush=True)

def _stdin() -> str:
    value = sys.stdin.read(_MAX_INPUT + 1)
    if len(value) > _MAX_INPUT: raise InputError("The supplied input is too long.")
    return value

def _editable_input(prompt: str, prefill: str = "") -> str:
    editor = _line_editor
    if editor is not None: editor.set_auto_history(False)

    def insert() -> None: editor.insert_text(prefill)

    if editor is not None and prefill: editor.set_startup_hook(insert)
    try:
        with _input_display(): return input(prompt)
    finally:
        if editor is not None: editor.set_startup_hook(None)

@contextlib.contextmanager
def _input_display() -> Iterator[None]:
    try: stdout_fd, stderr_fd = sys.stdout.fileno(), sys.stderr.fileno()
    except (AttributeError, OSError):
        with contextlib.redirect_stdout(sys.stderr): yield
        return
    sys.stdout.flush()
    saved_stdout = os.dup(stdout_fd)
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(os.close, saved_stdout)
        cleanup.callback(os.dup2, saved_stdout, stdout_fd)
        cleanup.callback(sys.stdout.flush)
        os.dup2(stderr_fd, stdout_fd)
        yield

def read_text(prompt: str, *, optional: bool = False, preserve_groups: bool = False,
              locked: str = "", prefill: str = "") -> str:
    if sys.stdin.isatty():
        shown = " ".join(locked[start : start + 4] for start in range(0, len(locked), 4))
        value = locked + _editable_input(f"{prompt}: {shown}{' ' if shown else ''}", prefill)
        _stderr("")
    else: value = _stdin().strip()
    if not preserve_groups: value = "".join(value.split())
    if not "".join(value.split()) and not optional: raise InputError("No input was provided.")
    return value

def _aligned_groups(observed: str, expected: str, highlight: bool) -> str:
    compact: list[str] = []; gaps = [""]
    for character in observed:
        if character.isspace(): gaps[-1] += character
        else: compact.append(character); gaps.append("")
    slots = [" "] * len(compact); insertions: dict[int, str] = {}; groups: set[int] = set()
    for tag, left, right, start, end in difflib.SequenceMatcher(
        None, "".join(compact).lower(), expected.lower(), autojunk=False
    ).get_opcodes():
        paired = min(right - left, end - start); slots[left:left + paired] = expected[start:start + paired]
        if start + paired < end: insertions[left + paired] = expected[start + paired:end]
        if tag == "equal": continue
        if start < end: groups.update(range(start // 4 + 1, (end - 1) // 4 + 2))
        if start == end or right - left > end - start:
            groups.update(filter(None, ((end - 1) // 4 + 1 if end else 0,
                                        end // 4 + 1 if end < len(expected) else 0)))
    initial = insertions.get(0, ""); shown = [initial, gaps[0][len(initial):]]
    for position, character in enumerate(slots, 1):
        addition = insertions.get(position, ""); shown.extend((character, addition, gaps[position][len(addition):]))
    result = "".join(shown)
    if not highlight: return result
    position = 0; styled = []
    for character in result:
        space = character.isspace(); position += not space
        marked = not space and (position + 3) // 4 in groups
        styled.append(f"\x1b[1;31m{character}\x1b[0m" if marked else character)
    return "".join(styled)

def _entered_groups(observed: str, expected: str) -> tuple[str, str]:
    # Align without copying any expected character into the displayed entry.
    observed = "".join(observed.split()); expected = "".join(expected.split())
    rows = [[0] * (len(expected) + 1) for _ in range(len(observed) + 1)]
    for left in range(len(observed), -1, -1): rows[left][-1] = len(observed) - left
    for right in range(len(expected), -1, -1): rows[-1][right] = len(expected) - right
    for left in range(len(observed) - 1, -1, -1):
        for right in range(len(expected) - 1, -1, -1):
            rows[left][right] = min(rows[left + 1][right] + 1, rows[left][right + 1] + 1,
                rows[left + 1][right + 1] + (observed[left].lower() != expected[right].lower()))
    slots: list[list[str]] = [[] for _ in range((len(expected) + 3) // 4)]
    missing = [0] * len(slots); changed: set[int] = set(); pending = [(0, 0)]; seen = set()
    while pending:
        point = pending.pop()
        if point in seen: continue
        seen.add(point); left, right = point; cost = rows[left][right]
        if left < len(observed) and right < len(expected):
            edit = observed[left].lower() != expected[right].lower()
            if rows[left + 1][right + 1] + edit == cost:
                pending.append((left + 1, right + 1)); changed.update((right // 4,) if edit else ()); continue
        if left < len(observed) and rows[left + 1][right] + 1 == cost:
            pending.append((left + 1, right)); changed.add(min(right // 4, len(slots) - 1))
        if right < len(expected) and rows[left][right + 1] + 1 == cost:
            pending.append((left, right + 1)); changed.add(right // 4)
    left = right = 0
    while left < len(observed) or right < len(expected):
        active = left < len(observed) and right < len(expected)
        equal = active and observed[left].lower() == expected[right].lower()
        if active and (equal or rows[left][right] == rows[left + 1][right + 1] + 1):
            entered, position = observed[left], right; left += 1; right += 1
        elif left < len(observed) and rows[left][right] == rows[left + 1][right] + 1:
            entered, position = observed[left], right; left += 1
        else: entered, position = "", right; right += 1
        group = min(position // 4, len(slots) - 1)
        if entered: slots[group].append(entered)
        if not entered: missing[group] += 1
    locked_groups = next((group for group in range(len(slots)) if
                          observed[group * 4 : group * 4 + 4].lower()
                          != expected[group * 4 : group * 4 + 4].lower()), len(slots))
    if len(observed) != len(expected) and locked_groups == len(slots): locked_groups -= 1
    positional = {index for index in range(len(slots)) if
                  observed[index * 4 : index * 4 + 4].lower()
                  != expected[index * 4 : index * 4 + 4].lower()}
    if len(observed) == len(expected) and len(positional) < len(changed):
        slots = [list(observed[index : index + 4]) for index in range(0, len(observed), 4)]
        missing, changed = [0] * len(slots), positional
    changed.difference_update(range(locked_groups)); shown = []
    for index, characters in enumerate(slots):
        value = "".join(characters).upper(); width = min(4, len(expected) - index * 4)
        if not value and missing[index] == width: value = "_" * width
        shown.append(f"\x1b[1;31m{value}\x1b[0m" if index in changed else value)
    grouped = " ".join(value + (" " if (index + 1) % 4 == 0 else "")
                       for index, value in enumerate(shown)).rstrip()
    return grouped, observed[: locked_groups * 4]

def _raw_suffix(value: str, prefix: str) -> str:
    if not prefix: return value
    compact = "".join(value.split()); count = 0
    if not compact.lower().startswith(prefix.lower()): return ""
    for position, character in enumerate(value):
        count += not character.isspace()
        if count == len(prefix): return value[position + 1 :]
    return ""

def _parse(value: str, profiles: tuple[Profile, ...]) -> Artifact:
    try: artifact = parse_codex32(value)
    except CodexError as error:
        raise InputError(_FRIENDLY_SET_ERRORS.get(type(error), str(error))) from error
    if artifact.profile not in profiles:
        allowed = " or ".join(_profile_rules(profile).label for profile in profiles)
        raise InputError(f"This command accepts only {allowed} input.")
    return artifact

def _retry_text(value: str, prefix: str) -> str:
    compact = "".join(value.split())
    if not (prefix and "1" in compact): return value
    return _raw_suffix(value, prefix)

_PRIMARY_MS = (48, 74, 127)
_REDUCED_MS = frozenset((54, 61, 67))
_TIMED_48_COUNTS = frozenset((40, *range(44, 53), 56))

def _correction_plan(
    profile: Profile, byte_length: int | Literal["?"] | None, count: int, target: int | None,
) -> tuple[tuple[int, ...], frozenset[int], frozenset[int], bool]:
    if target is not None:
        return (target,), frozenset((target,)), frozenset(), target == 48 and count in _TIMED_48_COUNTS
    if profile is Profile.CL: return (74,), frozenset((74,)), frozenset(), False
    if isinstance(byte_length, int):
        return ((length := _text_length(byte_length)),), frozenset((length,)), frozenset(), False
    if byte_length == "?": return TEXT_LENGTHS, frozenset(_PRIMARY_MS), frozenset(), False
    nearest = min(_PRIMARY_MS, key=lambda length: abs(count - length))
    targets = (nearest, *(length for length in TEXT_LENGTHS if length != nearest))
    return targets, frozenset(_PRIMARY_MS), _REDUCED_MS, count in _TIMED_48_COUNTS

def _correction_candidates(
    value: str, profile: Profile, byte_length: int | Literal["?"] | None, immutable: str,
    excluded: tuple[str, ...] = (), *, target: int | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool, float | None, bool]:
    count = len(value.replace(" ", ""))
    targets, primary, reduced, timed = _correction_plan(profile, byte_length, count, target)
    deadline = monotonic() + 10 if timed else None
    contexts = tuple(CorrectionContext(profile, length, immutable, excluded) for length in targets)
    from codex32.indel import _consecutive_witnesses, _search_many

    candidates, complete = _search_many(
        contexts, value, primary=primary, reduced=reduced, deadline=deadline,
    )
    ambiguous = False
    if complete and sum(char.lower() not in CHARSET for char in value.replace(" ", "")) > 8:
        witnesses, complete = _consecutive_witnesses(
            contexts, value, reduced=reduced, deadline=deadline,
        )
        observed = witnesses | {item.artifact.text.lower() for item in candidates}
        ambiguous = complete and len(observed) > 1
    results = _best(candidates, prefer_common=byte_length == "?") if complete and not ambiguous else ()
    return results, complete, deadline, ambiguous

def _suggestions(
    value: str, prefix: str, profiles: tuple[Profile, ...], accepted: list[Artifact],
) -> tuple[CorrectionCandidate, ...]:
    if not prefix: return ()
    profile = next(
        (item for item in (Profile.MS, Profile.CL) if value.lower().startswith(f"{item}1")), None,
    )
    if profile is None or profile not in profiles: return ()
    excluded = tuple(artifact.header.index for artifact in accepted)
    target = len(accepted[0].text) if accepted else None
    return _correction_candidates(value, profile, None, prefix, excluded, target=target)[0]

def _redirected(profiles: tuple[Profile, ...]) -> list[Artifact]:
    tokens = _stdin().split()
    if not tokens: raise InputError("No input was provided.")
    if len(tokens) > 9: raise InputError("At most nine codex32 strings may be provided at once.")
    return [_parse(token, profiles) for token in tokens]


_FRIENDLY_SET_ERRORS: dict[type[Exception], str] = {
    InvalidChecksum: "The checksum does not match.",
    MismatchedProfile: "These strings are for different applications.",
    MismatchedThreshold: "These strings require different numbers of shares.",
    MismatchedIdentifier: "These strings have different identifiers.",
    MismatchedPayloadLength: "These strings have different lengths.",
    DuplicateShareIndex: "That share index was already entered.",
    SecretInRecoverySet: "Enter ordinary shares rather than the shared secret.",
}

def _interactive(
    *, basis: bool, one: bool, excluded_index: str | None, profiles: tuple[Profile, ...]
) -> list[Artifact]:
    accepted: list[Artifact] = []
    prefix = "ms1" if profiles == (Profile.MS,) else ""
    prefill, required = "", 1
    while len(accepted) < required:
        label = (
            "Enter a codex32 string"
            if not accepted
            else (f"Enter {'string' if basis else 'share'} {len(accepted) + 1} of {required}")
        )
        displayed_prefix = prefix if accepted else ""
        entered = _editable_input(f"{label}: {displayed_prefix}", prefill)
        value = "".join(entered.split())
        complete_value = value if "1" in value else prefix + value
        try: artifact = _parse(complete_value, profiles)
        except InputError as error:
            candidates = _suggestions(complete_value, prefix, profiles, accepted)
            for candidate in candidates:
                shown = _aligned_groups(
                    displayed_prefix + entered, candidate.artifact.text, sys.stderr.isatty())
                _stderr(f"Possible correction:{' ' * max(1, len(label) - 18)}{shown}")
            confirmed = len(candidates) == 1 and _editable_input(
                "Use this correction? [y/N]: "
            ).strip().lower() in ("y", "yes")
            if not confirmed:
                _stderr(f"Rejected: {error}")
                prefill = _retry_text(entered, prefix)
                continue
            artifact = candidates[0].artifact
        try:
            if basis and artifact.header.index == excluded_index:
                raise ExistingTargetIndex("That index was requested for the additional share.")
            if not one and (accepted or isinstance(artifact, Share) or basis):
                recovering = not basis and isinstance(artifact, Share)
                validator = _validate_recovery_prefix if recovering else _validate_basis_prefix
                validator([*accepted, artifact])
        except CodexError as error:
            _stderr(f"Rejected: {_FRIENDLY_SET_ERRORS.get(type(error), str(error))}")
            duplicate = isinstance(error, (DuplicateShareIndex, ExistingTargetIndex))
            prefill = "" if duplicate else _retry_text(entered, prefix)
            continue
        prefill = ""
        if one: return [artifact]
        if isinstance(artifact, Secret) and not basis: return [artifact]
        if not accepted:
            required = artifact.header.threshold
            prefix = f"{artifact.profile.value}1{required}{artifact.header.identifier}"
            if artifact.text.isupper(): prefix = prefix.upper()
        accepted.append(artifact)
        if len(accepted) < required: _stderr(
            f"{'String' if basis else 'Share'} {len(accepted)} of {required} accepted.")
    return accepted

def read_artifacts(
    *,
    basis: bool = False,
    one: bool = False,
    excluded_index: str | None = None,
    profiles: tuple[Profile, ...] = tuple(Profile),
) -> list[Artifact]:
    if not sys.stdin.isatty(): return _redirected(profiles)
    result = _interactive(basis=basis, one=one, excluded_index=excluded_index, profiles=profiles)
    _stderr("")
    return result
