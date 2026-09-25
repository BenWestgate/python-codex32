# Bounded stdin and deliberately small interactive codex32 entry.

from __future__ import annotations

import contextlib
import difflib
import os
import sys
from collections.abc import Callable, Iterator
from time import monotonic
from typing import Any, Literal, cast

from codex32.bech32 import interpret_mixed_case
from codex32.bip93 import (
    Secret,
    Share,
    _checksum_for_encoded_length,
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
    InvalidLength,
    InvalidThreshold,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    SecretInRecoverySet,
)
from codex32.profiles import Profile, _optional_profile_rules, _profile_rules
from codex32.profiles.ms32 import (
    TEXT_LENGTHS,
    MasterSeed,
    _text_length,
)

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025
_MAX_CORRECTION_LENGTH_DELTA = 8

_line_editor: Any
try:
    import readline as _line_editor
except ImportError:
    _line_editor = None


class InputError(Exception):
    pass


class CorrectionDeclined(Exception):
    pass


class InteractiveConfirmationRequired(Exception):
    pass


def _confirmation_input(prompt: str) -> str:
    if sys.stdin.isatty():
        return _editable_input(prompt)
    if not sys.stderr.isatty():
        raise InteractiveConfirmationRequired
    terminal_name = "CONIN$" if os.name == "nt" else "/dev/tty"
    try:
        with open(terminal_name, encoding="utf-8", buffering=1) as terminal:
            if not terminal.isatty():
                raise InteractiveConfirmationRequired
            print(prompt, end="", file=sys.stderr, flush=True)
            answer = terminal.readline()
    except OSError:
        raise InteractiveConfirmationRequired from None
    if not answer:
        raise EOFError
    return answer.rstrip("\r\n")


def _require_correction_confirmation(low_discrimination: bool) -> None:
    if not low_discrimination:
        return
    if not sys.stderr.isatty():
        raise InteractiveConfirmationRequired
    label = "\x1b[1;31mWarning:\x1b[0m"
    _stderr(
        f"{label} If you are generating new data and attempting to fill in the missing\n"
        "squares to complete a checksum, ensure that you have transcribed the data\n"
        "exactly as it will be used. There is no way to detect or correct transcription\n"
        'errors, so any errors you have made up to this point will be "locked in" by\n'
        "completing the checksum.\n\n"
        "If you are recovering data with this many missing characters, understand that\n"
        "the completion may be incorrect and you may need to resort to other methods\n"
        "(e.g. grinding through possible typos) to recover your data.\n"
    )
    try:
        answer = _confirmation_input("If you understand this, type YES to attempt to correct the data: ")
    except EOFError:
        raise CorrectionDeclined from None
    if answer.strip() != "YES":
        raise CorrectionDeclined


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


def _confirm_correction(
    candidate: CorrectionCandidate,
    accepted: list[Artifact],
    basis: bool,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> bool | None:
    _require_correction_confirmation(candidate.low_checksum_discrimination)
    artifact = candidate.artifact
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
        fingerprint_text = (
            f"Master fingerprint: {fingerprint(preview).hex().upper()}\n\n"
            if isinstance(preview, MasterSeed) and fingerprint is not None
            else ""
        )
    except CodexError:
        _stderr("Rejected: Could not recover a valid Bitcoin master seed using this correction.")
        return None
    _stderr(f"Possible correction:\n\n{fingerprint_text}{_card_text(artifact.text, sys.stderr.isatty())}\n")
    return _confirmation_input(
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


def _parse(value: str, profiles: tuple[Profile, ...] | None) -> Artifact:
    try:
        artifact = parse_codex32(value)
    except CodexError as error:
        message = _FRIENDLY_SET_ERRORS.get(type(error), str(error))
        if isinstance(error, InvalidChecksum):
            # Parsing has already checked the container and generic length.
            # Explain an unsupported profile length without validating input
            # or changing the parser's checksum-before-profile boundary.
            try:
                _profile_rules(value[: value.rfind("1")]).validate_text_length(len(value))
            except InvalidLength as length_error:
                message = str(length_error)
            except CodexError:
                pass
        raise InputError(message) from error
    if profiles is not None and artifact.profile not in profiles:
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


def _prefix_for_suffix(prefix: str, suffix: str) -> str:
    """Match a fixed prefix to the editable suffix's prevailing case."""
    cased = [character for character in suffix if character.lower() != character.upper()]
    uppercase = sum(character.isupper() for character in cased)
    if uppercase > len(cased) / 2:
        return prefix.upper()
    if uppercase < len(cased) / 2:
        return prefix.lower()
    return prefix


def _accepted_prefix(accepted: list[Artifact]) -> str:
    first = accepted[0]
    prefix = f"{first.hrp}1{first.header.threshold}{first.header.identifier}"
    return prefix.upper() if all(artifact.text.isupper() for artifact in accepted) else prefix


def _display_prefix(prefix: str, grouped: bool) -> str:
    if not grouped:
        return prefix
    groups = [prefix[index : index + 4] for index in range(0, len(prefix), 4)]
    displayed = " ".join(groups)
    if len(prefix) % 4 == 0:
        displayed += "  " if len(groups) % 4 == 0 else " "
    return displayed


def _case_interpretation(
    value: str,
    prefix: str,
    profiles: tuple[Profile, ...] | None,
    allowed: Callable[[CorrectionCandidate], bool] | None,
) -> tuple[CorrectionCandidate | None, str, str, str] | None:
    """Normalize likely casing and mark contrary-case data as erasures."""
    separator = value.find("1")
    base_length = separator + 1 if separator >= 0 else 0
    immutable_length = len(prefix) if prefix and value.lower().startswith(prefix.lower()) else base_length
    interpretation = interpret_mixed_case(value, immutable_length)
    if interpretation is None:
        return None
    corrected, erased, uppercase = interpretation
    corrected_prefix = prefix.upper() if uppercase else prefix.lower()
    try:
        artifact = _parse(corrected, profiles)
    except InputError:
        candidate = None
    else:
        bits = (
            5 * _checksum_for_encoded_length(artifact.hrp, len(artifact.text) - len(artifact.hrp) - 1).length
        )
        proposed = CorrectionCandidate(artifact, (), 1, 0, 0, None, capture_space_bits=bits)
        candidate = proposed if allowed is None or allowed(proposed) else None
    return candidate, corrected, erased, corrected_prefix


_PRIMARY_MS = (48, 74, 127)


def _correction_plan(
    hrp: str | Profile,
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
    normalized_hrp = hrp.value if isinstance(hrp, Profile) else hrp.lower()
    if normalized_hrp == Profile.CL.value:
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
    if normalized_hrp == Profile.MS.value:
        nearest = min(_PRIMARY_MS, key=lambda length: abs(count - length))
        targets = (nearest, *(length for length in TEXT_LENGTHS if length != nearest))
        return targets, frozenset(targets), frozenset(), True
    rules = _optional_profile_rules(normalized_hrp)
    if rules is not None and hasattr(rules, "text_length"):
        targets = (rules.text_length,)
        return targets, frozenset(targets), frozenset(), True
    targets = tuple(sorted({count + delta for delta in (*range(-4, 5), -8, 8)}))
    return targets, frozenset(targets), frozenset(), True


def _correction_candidates(
    value: str,
    profile: str | Profile,
    byte_length: int | Literal["?"] | None,
    immutable: str,
    excluded: tuple[str, ...] = (),
    *,
    target: int | None = None,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    deadline: float | None = None,
    capture_layers: list[tuple[int, int]] | None = None,
    fingerprint_match: Callable[[CorrectionCandidate], bool | None] | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool, float | None]:
    count = len(value.replace(" ", ""))
    targets, primary, reduced, _timed = _correction_plan(profile, byte_length, count, target)
    deadline = monotonic() + 10 if deadline is None else deadline
    contexts = tuple(CorrectionContext(profile, length, immutable, excluded) for length in targets)
    from codex32.indel import _search_many

    candidates, complete = _search_many(
        contexts,
        value,
        primary=primary,
        reduced=reduced,
        deadline=deadline,
        competitors=True,
        allowed=allowed,
        capture_layers=capture_layers,
    )
    if allowed is not None:
        candidates = tuple(candidate for candidate in candidates if allowed(candidate))
    results = (
        _best(candidates, prefer_common=byte_length == "?", fingerprint_match=fingerprint_match)
        if complete
        else candidates
        if len(candidates) == 1 and not candidates[0].search_complete
        else ()
    )
    return results, complete, deadline


def _fingerprint_matcher(
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> Callable[[CorrectionCandidate], bool | None] | None:
    if fingerprint is None:
        return None
    from codex32.generation import _fingerprint_identifier

    def matches(candidate: CorrectionCandidate) -> bool | None:
        artifact = candidate.artifact
        if not isinstance(artifact, MasterSeed) or artifact.header.threshold:
            return None
        try:
            return _fingerprint_identifier(fingerprint(artifact)) == artifact.header.identifier
        except CodexError:
            return None

    return matches


def _suggestions(
    value: str,
    prefix: str,
    profiles: tuple[Profile, ...] | None,
    accepted: list[Artifact],
    *,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> tuple[CorrectionCandidate, ...]:
    fingerprint_match = _fingerprint_matcher(fingerprint)
    erased = value
    if interpretation := _case_interpretation(value, prefix, profiles, allowed):
        candidate, value, erased, prefix = interpretation
        if candidate is not None:
            return (candidate,)
    separator = value.lower().rfind("1")
    if separator <= 0:
        return ()
    hrp = value[:separator].lower()
    rules = _optional_profile_rules(hrp)
    profile = rules.profile if rules is not None else None
    if profiles is not None and profile not in profiles:
        return ()
    excluded = tuple(artifact.header.index for artifact in accepted)
    target = len(accepted[0].text) if accepted else None
    immutable = (
        value[: len(prefix)]
        if prefix and value.lower().startswith(prefix.lower())
        else prefix or value[: separator + 1]
    )
    deadline = monotonic() + 10
    capture_layers: list[tuple[int, int]] = []
    candidates = _correction_candidates(
        value,
        hrp,
        None,
        immutable,
        excluded,
        target=target,
        allowed=allowed,
        deadline=deadline,
        capture_layers=capture_layers,
        fingerprint_match=fingerprint_match,
    )[0]
    if candidates or erased == value:
        return candidates
    return _correction_candidates(
        erased,
        hrp,
        None,
        immutable,
        excluded,
        target=target,
        allowed=allowed,
        deadline=deadline,
        capture_layers=capture_layers,
        fingerprint_match=fingerprint_match,
    )[0]


def _validate_operational_artifact(
    artifact: Artifact,
    accepted: list[Artifact],
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
) -> None:
    if basis and artifact.header.index == excluded_index:
        raise ExistingTargetIndex("That index was requested for the additional share.")
    if not one and (accepted or isinstance(artifact, Share) or basis):
        recovering = not basis and isinstance(artifact, Share)
        validator = _validate_recovery_prefix if recovering else _validate_basis_prefix
        validator([*accepted, artifact])


def _redirected(
    profiles: tuple[Profile, ...] | None,
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> list[Artifact]:
    tokens = _stdin().split()
    if not tokens:
        raise InputError("No input was provided.")
    if len(tokens) > 9:
        raise InputError("At most nine codex32 strings may be provided at once.")
    accepted: list[Artifact] = []
    for token in tokens:
        try:
            artifact = _parse(token, profiles)
        except InputError:
            if one:
                raise

            def allowed(candidate: CorrectionCandidate) -> bool:
                try:
                    _validate_operational_artifact(
                        candidate.artifact,
                        accepted,
                        basis=basis,
                        one=one,
                        excluded_index=excluded_index,
                    )
                except CodexError:
                    return False
                return True

            candidates = _suggestions(
                token,
                "",
                profiles,
                accepted,
                allowed=allowed,
                fingerprint=fingerprint,
            )
            if len(candidates) != 1:
                raise
            if not _confirm_correction(candidates[0], accepted, basis, fingerprint):
                raise CorrectionDeclined
            artifact = candidates[0].artifact
        _validate_operational_artifact(
            artifact,
            accepted,
            basis=basis,
            one=one,
            excluded_index=excluded_index,
        )
        accepted.append(artifact)
    return accepted


_FRIENDLY_SET_ERRORS: dict[type[Exception], str] = {
    InvalidChecksum: "The checksum does not match.",
    MismatchedProfile: "These strings are for different applications.",
    MismatchedThreshold: "These strings require different numbers of shares.",
    MismatchedIdentifier: "These strings have different identifiers.",
    MismatchedPayloadLength: "These strings have different lengths.",
    DuplicateShareIndex: "That share index was already entered.",
    SecretInRecoverySet: "Enter ordinary shares rather than the shared secret.",
}


def _prefixed_input_error(
    error: InputError,
    value: str,
    prefix: str,
    accepted: list[Artifact],
) -> str:
    cause = error.__cause__
    if isinstance(cause, InvalidThreshold) and prefix.lower() == "ms1":
        found = value[len(prefix) : len(prefix) + 1].lower()
        if found:
            return f"After the prefilled {prefix}, enter a threshold of 0 or 2 through 9; found {found!r}."
    if not isinstance(cause, InvalidChecksum):
        return str(error)
    if accepted:
        if accepted[0].profile is not Profile.MS:
            return str(error)
        target = len(accepted[0].text)
        difference = len(value) - target
        if abs(difference) <= _MAX_CORRECTION_LENGTH_DELTA:
            return str(error)
        direction = "too long for" if difference > 0 else "short of"
        return (
            f"The string is {abs(difference)} characters {direction} the required {target}-character length."
        )
    if prefix.lower() != "ms1":
        return str(error)
    if min(abs(len(value) - target) for target in TEXT_LENGTHS) <= _MAX_CORRECTION_LENGTH_DELTA:
        return str(error)
    lengths = ", ".join(str(length) for length in TEXT_LENGTHS[:-1]) + f", or {TEXT_LENGTHS[-1]}"
    return (
        f"The string has {len(value)} characters; valid Bitcoin master-seed codex32 lengths are "
        f"{lengths} characters."
    )


def _interactive(
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
    profiles: tuple[Profile, ...] | None,
    initial_prefix: str,
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> list[Artifact]:
    accepted: list[Artifact] = []
    prefix = initial_prefix
    prefill, required, grouped_prefix = "", 1, False

    def validate(artifact: Artifact) -> None:
        _validate_operational_artifact(
            artifact,
            accepted,
            basis=basis,
            one=one,
            excluded_index=excluded_index,
        )

    def allowed(candidate: CorrectionCandidate) -> bool:
        try:
            validate(candidate.artifact)
        except CodexError:
            return False
        return True

    while len(accepted) < required:
        label = (
            "Enter a codex32 string"
            if not accepted
            else (f"Enter {'string' if basis else 'share'} {len(accepted) + 1} of {required}")
        )
        entered = _editable_input(f"{label}:\n> {_display_prefix(prefix, grouped_prefix)}", prefill)
        value = "".join(entered.split())
        supplied_prefix = bool(prefix) and "1" not in value
        complete_value = value if not supplied_prefix else _prefix_for_suffix(prefix, value) + value
        try:
            artifact = _parse(complete_value, profiles)
        except InputError as error:
            candidates = (
                ()
                if one
                else _suggestions(
                    complete_value,
                    prefix,
                    profiles,
                    accepted,
                    allowed=allowed,
                    fingerprint=fingerprint,
                )
            )
            confirmation = (
                _confirm_correction(candidates[0], accepted, basis, fingerprint)
                if len(candidates) == 1
                else None
            )
            if confirmation is False:
                _stderr("")
                prefill = _retry_text(entered, prefix)
                prefix = _prefix_for_suffix(prefix, prefill)
                continue
            if confirmation is True:
                artifact = candidates[0].artifact
            else:
                message = (
                    _prefixed_input_error(error, complete_value, prefix, accepted)
                    if supplied_prefix
                    else str(error)
                )
                _stderr(f"Rejected: {message}\n")
                prefill = _retry_text(entered, prefix)
                prefix = _prefix_for_suffix(prefix, prefill)
                continue
        try:
            validate(artifact)
        except CodexError as error:
            _stderr(f"Rejected: {_FRIENDLY_SET_ERRORS.get(type(error), str(error))}\n")
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
        accepted.append(artifact)
        prefix = _accepted_prefix(accepted)
        grouped_prefix = len(entered.split()) > 1
        if len(accepted) < required:
            _stderr(f"{'String' if basis else 'Share'} {len(accepted)} of {required} accepted.")
    return accepted


def read_artifacts(
    *,
    basis: bool = False,
    one: bool = False,
    excluded_index: str | None = None,
    profiles: tuple[Profile, ...] | None = None,
    initial_prefix: str = "",
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> list[Artifact]:
    if not sys.stdin.isatty():
        return _redirected(
            profiles,
            basis=basis,
            one=one,
            excluded_index=excluded_index,
            fingerprint=fingerprint,
        )
    result = _interactive(
        basis=basis,
        one=one,
        excluded_index=excluded_index,
        profiles=profiles,
        initial_prefix=initial_prefix,
        fingerprint=fingerprint,
    )
    _stderr("")
    return result
