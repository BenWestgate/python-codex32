# Bounded stdin and deliberately small interactive codex32 entry.

from __future__ import annotations

import contextlib
import difflib
import os
import sys
from collections.abc import Iterator
from time import monotonic
from typing import Any, Literal, cast

from codex32.bip93 import (
    Secret,
    Share,
    _validate_basis_prefix,
    _validate_recovery_prefix,
    parse_codex32,
    recover_secret,
)
from codex32.correction import CorrectionCandidate, CorrectionContext, _best
from codex32.errors import (
    CodexError,
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidChecksum,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    SecretInRecoverySet,
)
from codex32.profiles import Profile, _profile_rules
from codex32.profiles.ms32 import (
    TEXT_LENGTHS,
    MasterSeed,
    _fingerprint_from_seed,
    _text_length,
)

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025

_line_editor: Any
try:
    import readline as _line_editor
except ImportError:
    _line_editor = None


class InputError(Exception):
    pass


def _stderr(text: str, *, end: str = "\n") -> None:
    print(text, end=end, file=sys.stderr, flush=True)


def _stdin() -> str:
    value = sys.stdin.read(_MAX_INPUT + 1)
    if len(value) > _MAX_INPUT:
        raise InputError("The supplied input is too long.")
    return value


def _editable_input(prompt: str, prefill: str = "") -> str:
    editor = _line_editor
    if editor is not None:
        editor.set_auto_history(False)

    def insert() -> None:
        editor.insert_text(prefill)

    if editor is not None and prefill:
        editor.set_startup_hook(insert)
    try:
        with _input_display():
            return input(prompt)
    finally:
        if editor is not None:
            editor.set_startup_hook(None)


@contextlib.contextmanager
def _input_display() -> Iterator[None]:
    try:
        stdout_fd, stderr_fd = sys.stdout.fileno(), sys.stderr.fileno()
    except (AttributeError, OSError):
        with contextlib.redirect_stdout(sys.stderr):
            yield
        return
    sys.stdout.flush()
    saved_stdout = os.dup(stdout_fd)
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(os.close, saved_stdout)
        cleanup.callback(os.dup2, saved_stdout, stdout_fd)
        cleanup.callback(sys.stdout.flush)
        os.dup2(stderr_fd, stdout_fd)
        yield


def read_text(
    prompt: str,
    *,
    optional: bool = False,
    preserve_groups: bool = False,
    prefill: str = "",
    prompt_end: str = ": ",
) -> str:
    if sys.stdin.isatty():
        value = _editable_input(prompt + prompt_end, prefill)
        _stderr("")
    else:
        value = _stdin().strip()
    if not preserve_groups:
        value = "".join(value.split())
    if not "".join(value.split()) and not optional:
        raise InputError("No input was provided.")
    return value


def _card_text(text: str, highlight: bool = True, observed: str = "") -> str:
    # Only explicit correction inspection supplies observed text.
    changed: set[int] = set()
    for tag, left, right, start, end in (
        difflib.SequenceMatcher(
            None, "".join(observed.split()).lower(), text.lower(), autojunk=False
        ).get_opcodes()
        if observed
        else ()
    ):
        if tag == "equal":
            continue
        changed.update(range(start // 4, (end + 3) // 4))
        if start == end:
            changed.add(min(start // 4, (len(text) - 1) // 4))
    rendered = _render_groups(
        [text[i : i + 4] for i in range(0, len(text), 4)],
        changed,
        len(text),
        highlight=highlight,
    )
    return rendered if changed else rendered.replace("\x1b[0m ", " ")


def _confirm_correction(artifact: Artifact, accepted: list[Artifact], basis: bool) -> bool | None:
    # Provisional recovery is exclusively for this fingerprint preview.
    preview = artifact
    try:
        if (
            isinstance(artifact, Share)
            and artifact.profile is Profile.MS
            and not basis
            and (len(accepted) + 1 == artifact.header.threshold)
        ):
            preview = recover_secret(cast(list[Share], [*accepted, artifact]))
        fingerprint = (
            f"Master fingerprint: {_fingerprint_from_seed(preview.seed_bytes).hex().upper()}\n\n"
            if isinstance(preview, MasterSeed)
            else ""
        )
    except CodexError:
        _stderr("Rejected: Could not recover a valid Bitcoin master seed using this correction.")
        return None
    _stderr(f"Possible correction:\n\n{fingerprint}{_card_text(artifact.text, sys.stderr.isatty())}\n")
    return _editable_input(
        "Does this entire string exactly match your recovery card? [y/N]: "
    ).strip().lower() in ("y", "yes")


def _entered_groups(observed: str, expected: str) -> tuple[list[str], set[int]]:
    # Keep entered tokens whole unless they exactly span complete groups.
    # Unspaced input retains edit/group minimization and edit-order ties.
    positions = [i for i, char in enumerate(observed) if not char.isspace()]
    compact = "".join(observed.split())
    expected = "".join(expected.split()).lower()
    tokens = observed.split()
    grouped = len(tokens) > 1 and compact.lower() != expected
    boundaries = {0}
    splits: set[tuple[int, int]] = set()
    position = 0
    for token in tokens:
        for offset in range(0, len(expected), 4):
            if expected[offset : offset + len(token)] == token.lower() and (
                len(token) % 4 == 0 or offset + len(token) == len(expected)
            ):
                splits.update((position + i, offset + i) for i in range(4, len(token), 4))
        position += len(token)
        boundaries.add(position)
    scores = {0: (0, 0, b"", ())}  # type: dict[int, tuple[int, int, bytes, tuple[int, ...]]]
    for offset in range(0, len(expected), 4):
        canonical = expected[offset : offset + 4]
        following: dict[int, tuple[int, int, bytes, tuple[int, ...]]] = {}
        for start, (edits, disturbed, trace, ends) in scores.items():
            row = [(j, b"\x03" * j) for j in range(len(canonical) + 1)]
            for end in range(start, len(compact) + 1):
                if end > start:
                    current = [(end - start, b"\x02" * (end - start))]
                    for j, char in enumerate(canonical, 1):
                        edit = compact[end - 1].lower() != char
                        current.append(
                            min(
                                (row[j - 1][0] + edit, row[j - 1][1] + bytes([edit])),
                                (row[j][0] + 1, row[j][1] + b"\x02"),
                                (current[j - 1][0] + 1, current[j - 1][1] + b"\x03"),
                            )
                        )
                    row = current
                if grouped and end not in boundaries and (end, offset + len(canonical)) not in splits:
                    continue
                score = (
                    edits + row[-1][0],
                    disturbed + (not grouped and compact[start:end].lower() != canonical),
                    trace + row[-1][1],
                    (*ends, end),
                )
                if end not in following or score < following[end]:
                    following[end] = score
        scores = following
    groups = []
    start = 0
    for end in scores[len(compact)][3]:
        stop = positions[end] if end < len(positions) else len(observed)
        groups.append(observed[start:stop])
        start = stop
    changed = {
        i for i, value in enumerate(groups) if "".join(value.split()).lower() != expected[i * 4 : i * 4 + 4]
    }
    return groups, changed


def _render_groups(
    groups: list[str],
    changed: set[int],
    length: int,
    active: range = range(0),
    *,
    highlight: bool = True,
) -> str:
    shown = []
    for index, value in enumerate(groups):
        value = "".join(value.split()).upper() or "_" * min(4, length - index * 4)
        style = "1" if index % 2 == 0 else "22"
        if index in changed:
            style = "1;7;31" if index in active else "1;31"
        shown.append(f"\x1b[{style}m{value}\x1b[0m" if highlight else value)
    return " ".join(
        value + (" " if (index + 1) % 4 == 0 else "") for index, value in enumerate(shown)
    ).rstrip()


def _parse(value: str, profiles: tuple[Profile, ...]) -> Artifact:
    try:
        artifact = parse_codex32(value)
    except CodexError as error:
        raise InputError(_FRIENDLY_SET_ERRORS.get(type(error), str(error))) from error
    if artifact.profile not in profiles:
        allowed = " or ".join(_profile_rules(profile).label for profile in profiles)
        raise InputError(f"This command accepts only {allowed} input.")
    return artifact


def _retry_text(value: str, prefix: str) -> str:
    compact = "".join(value.split())
    if not (prefix and "1" in compact):
        return value
    if not compact.lower().startswith(prefix.lower()):
        return ""
    positions = (position for position, character in enumerate(value) if not character.isspace())
    for _character in prefix:
        position = next(positions)
    return value[position + 1 :]


_PRIMARY_MS = (48, 74, 127)


def _correction_plan(
    profile: Profile,
    byte_length: int | Literal["?"] | None,
    count: int,
    target: int | None,
) -> tuple[tuple[int, ...], frozenset[int], frozenset[int], bool]:
    if target is not None:
        return (
            (target,),
            frozenset((target,)),
            frozenset(),
            True,
        )
    if profile is Profile.CL:
        return (74,), frozenset((74,)), frozenset(), True
    if isinstance(byte_length, int):
        return (
            ((length := _text_length(byte_length)),),
            frozenset((length,)),
            frozenset(),
            True,
        )
    if byte_length == "?":
        return TEXT_LENGTHS, frozenset(TEXT_LENGTHS), frozenset(), True
    nearest = min(_PRIMARY_MS, key=lambda length: abs(count - length))
    targets = (nearest, *(length for length in TEXT_LENGTHS if length != nearest))
    return targets, frozenset(targets), frozenset(), True


def _correction_candidates(
    value: str,
    profile: Profile,
    byte_length: int | Literal["?"] | None,
    immutable: str,
    excluded: tuple[str, ...] = (),
    *,
    target: int | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool, float | None, bool]:
    count = len(value.replace(" ", ""))
    targets, primary, reduced, _timed = _correction_plan(profile, byte_length, count, target)
    deadline = monotonic() + 10
    contexts = tuple(CorrectionContext(profile, length, immutable, excluded) for length in targets)
    from codex32.indel import _search_many

    candidates, complete = _search_many(
        contexts,
        value,
        primary=primary,
        reduced=reduced,
        deadline=deadline,
    )
    results = (
        _best(candidates, prefer_common=byte_length == "?")
        if complete
        else candidates
        if len(candidates) == 1 and not candidates[0].search_complete
        else ()
    )
    return results, complete, deadline, False


def _suggestions(
    value: str,
    prefix: str,
    profiles: tuple[Profile, ...],
    accepted: list[Artifact],
) -> tuple[CorrectionCandidate, ...]:
    profile = next((p for p in (Profile.MS, Profile.CL) if value.lower().startswith(f"{p}1")), None)
    if profile is None or profile not in profiles:
        return ()
    excluded = tuple(artifact.header.index for artifact in accepted)
    target = len(accepted[0].text) if accepted else None
    candidates = _correction_candidates(
        value, profile, None, prefix or value[: len(profile.value) + 1], excluded, target=target
    )[0]
    if candidates and not candidates[0].search_complete:
        _stderr("Best-effort suggestion: the search is incomplete; uniqueness is not established.")
    return candidates


def _redirected(profiles: tuple[Profile, ...]) -> list[Artifact]:
    tokens = _stdin().split()
    if not tokens:
        raise InputError("No input was provided.")
    if len(tokens) > 9:
        raise InputError("At most nine codex32 strings may be provided at once.")
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
        entered = _editable_input(f"{label}:\n> {displayed_prefix}", prefill)
        value = "".join(entered.split())
        complete_value = value if "1" in value else prefix + value
        try:
            artifact = _parse(complete_value, profiles)
        except InputError as error:
            candidates = () if one else _suggestions(complete_value, prefix, profiles, accepted)
            confirmation = (
                _confirm_correction(candidates[0].artifact, accepted, basis) if len(candidates) == 1 else None
            )
            if confirmation is False:
                _stderr("")
                prefill = _retry_text(entered, prefix)
                continue
            if confirmation is True:
                artifact = candidates[0].artifact
            else:
                _stderr(f"Rejected: {error}")
                prefill = _retry_text(entered, prefix)
                continue
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
        if one:
            return [artifact]
        if isinstance(artifact, Secret) and not basis:
            return [artifact]
        if not accepted:
            required = artifact.header.threshold
            prefix = f"{artifact.profile.value}1{required}{artifact.header.identifier}"
            if artifact.text.isupper():
                prefix = prefix.upper()
        accepted.append(artifact)
        if len(accepted) < required:
            _stderr(f"{'String' if basis else 'Share'} {len(accepted)} of {required} accepted.")
    return accepted


def read_artifacts(
    *,
    basis: bool = False,
    one: bool = False,
    excluded_index: str | None = None,
    profiles: tuple[Profile, ...] = tuple(Profile),
) -> list[Artifact]:
    if not sys.stdin.isatty():
        return _redirected(profiles)
    result = _interactive(basis=basis, one=one, excluded_index=excluded_index, profiles=profiles)
    _stderr("")
    return result
