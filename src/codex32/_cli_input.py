# Bounded stdin and deliberately small interactive codex32 entry.

from __future__ import annotations

import contextlib
import difflib
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Literal

from codex32.bip93 import (
    MS,
    Codex32String,
    MasterSeed,
    _text_length,
    _validate_ms_length,
    _validate_recovery_prefix,
    _validate_share_set,
    parse_codex32,
    recover_secret,
)
from codex32.correction import CorrectionCandidate, CorrectionContext, _best, _correct_complete
from codex32.errors import (
    CodexError,
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidChecksum,
    InvalidCorrectionInput,
    InvalidLength,
)

_MAX_INPUT = 9 * 1025

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
    if not sys.stdin.isatty():
        raise InteractiveConfirmationRequired
    return _editable_input(prompt)


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
    accepted: list[Codex32String],
    basis: bool,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> bool | None:
    _require_correction_confirmation(candidate.low_checksum_discrimination)
    artifact = candidate.artifact
    # Provisional recovery is exclusively for this fingerprint preview.
    preview = artifact
    try:
        if (
            artifact.share_idx != "s"
            and artifact.hrp == MS
            and not basis
            and (len(accepted) + 1 == int(artifact.k))
        ):
            preview = recover_secret([*accepted, artifact])
        fingerprint_text = (
            f"Master fingerprint: {fingerprint(preview).hex().upper()}\n\n"
            if isinstance(preview, MasterSeed) and fingerprint is not None
            else ""
        )
    except CodexError:
        _stderr("Rejected: Could not recover a valid Bitcoin master seed using this correction.")
        return None
    _stderr(f"Possible correction:\n\n{fingerprint_text}{_card_text(artifact.s, sys.stderr.isatty())}\n")
    return _confirmation_input(
        "Does this entire string exactly match your recovery card? [y/N]: "
    ).strip().lower() in ("y", "yes")


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


def _parse(value: str, hrp: str | None) -> Codex32String:
    try:
        artifact = parse_codex32(value)
    except InvalidChecksum as error:
        # The parser checks checksums before master-seed lengths; explain a
        # wrong length without changing that order.
        try:
            _validate_ms_length(value[: value.rfind("1")].lower(), len(value))
        except InvalidLength as length_error:
            raise InputError(str(length_error)) from error
        raise InputError(str(error)) from error
    except CodexError as error:
        raise InputError(str(error)) from error
    if hrp is not None and artifact.hrp != hrp:
        raise InputError("This command accepts only Bitcoin master seed input.")
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


def _accepted_prefix(accepted: list[Codex32String]) -> str:
    first = accepted[0]
    prefix = f"{first.hrp}1{first.k}{first.ident}"
    return prefix.upper() if all(artifact.s.isupper() for artifact in accepted) else prefix


def _display_prefix(prefix: str, grouped: bool) -> str:
    if not grouped:
        return prefix
    groups = [prefix[index : index + 4] for index in range(0, len(prefix), 4)]
    displayed = " ".join(groups)
    if len(prefix) % 4 == 0:
        displayed += "  " if len(groups) % 4 == 0 else " "
    return displayed


def _fingerprint_matcher(
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> Callable[[CorrectionCandidate], bool | None] | None:
    if fingerprint is None:
        return None
    from codex32.generation import _fingerprint_identifier

    def matches(candidate: CorrectionCandidate) -> bool | None:
        artifact = candidate.artifact
        if not isinstance(artifact, MasterSeed) or artifact.k != "0":
            return None
        try:
            return _fingerprint_identifier(fingerprint(artifact)) == artifact.ident
        except CodexError:
            return None

    return matches


def _suggestions(
    value: str,
    prefix: str,
    required_hrp: str | None,
    accepted: Sequence[Codex32String],
    *,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
    byte_length: int | Literal["?"] | None = None,
) -> tuple[CorrectionCandidate, ...]:
    return _corrections(
        value,
        prefix,
        required_hrp,
        accepted,
        allowed=allowed,
        fingerprint=fingerprint,
        byte_length=byte_length,
    )[0]


def _corrections(
    value: str,
    prefix: str,
    required_hrp: str | None,
    accepted: Sequence[Codex32String],
    *,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
    byte_length: int | Literal["?"] | None = None,
    length: int | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    """Run the library search, then the CLI's Hamming, CRC, and fingerprint tie breakers."""
    separator = value.rfind("1")
    hrp = value[: max(separator, 0)].lower()
    if separator <= 0 or required_hrp not in (None, hrp):
        return (), True
    target = len(accepted[0].s) if accepted else length
    if isinstance(byte_length, int):
        target = _text_length(byte_length)
    immutable = prefix if prefix and value.lower().startswith(prefix.lower()) else value[: separator + 1]
    try:
        context = CorrectionContext.from_shares(
            accepted,
            hrp=hrp,
            expected_length=target,
            immutable_prefix=_prefix_for_suffix(immutable, value),
        )
        candidates, complete = _correct_complete(context, value, allowed=allowed, competitors=True)
    except InvalidCorrectionInput:
        return (), True
    best = _best(
        candidates, prefer_common=byte_length == "?", fingerprint_match=_fingerprint_matcher(fingerprint)
    )
    return best, complete


def _validate_operational_artifact(
    artifact: Codex32String,
    accepted: list[Codex32String],
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
) -> None:
    if basis and artifact.share_idx == excluded_index:
        raise ExistingTargetIndex("That index was requested for the additional share.")
    if not one and (accepted or artifact.share_idx != "s" or basis):
        recovering = not basis and artifact.share_idx != "s"
        if recovering:
            _validate_recovery_prefix([*accepted, artifact])
        else:
            _validate_share_set([*accepted, artifact], require_exact=False)


def _redirected(
    hrp: str | None,
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> list[Codex32String]:
    tokens = _stdin().split()
    if not tokens:
        raise InputError("No input was provided.")
    if len(tokens) > 9:
        raise InputError("At most nine codex32 strings may be provided at once.")
    accepted: list[Codex32String] = []
    for token in tokens:
        try:
            artifact = _parse(token, hrp)
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
                hrp,
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


def _interactive(
    *,
    basis: bool,
    one: bool,
    excluded_index: str | None,
    hrp: str | None,
    initial_prefix: str,
    fingerprint: Callable[[MasterSeed], bytes] | None,
) -> list[Codex32String]:
    accepted: list[Codex32String] = []
    prefix = initial_prefix
    prefill, required, grouped_prefix = "", 1, False

    def validate(artifact: Codex32String) -> None:
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
            artifact = _parse(complete_value, hrp)
        except InputError as error:
            candidates = (
                ()
                if one
                else _suggestions(
                    complete_value,
                    prefix,
                    hrp,
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
                _stderr(f"Rejected: {error}\n")
                prefill = _retry_text(entered, prefix)
                prefix = _prefix_for_suffix(prefix, prefill)
                continue
        try:
            validate(artifact)
        except CodexError as error:
            _stderr(f"Rejected: {error}\n")
            duplicate = isinstance(error, (DuplicateShareIndex, ExistingTargetIndex))
            prefill = "" if duplicate else _retry_text(entered, prefix)
            continue
        prefill = ""
        if one:
            return [artifact]
        if artifact.share_idx == "s" and not basis:
            return [artifact]
        if not accepted:
            required = int(artifact.k)
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
    hrp: str | None = None,
    initial_prefix: str = "",
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> list[Codex32String]:
    if not sys.stdin.isatty():
        return _redirected(
            hrp,
            basis=basis,
            one=one,
            excluded_index=excluded_index,
            fingerprint=fingerprint,
        )
    result = _interactive(
        basis=basis,
        one=one,
        excluded_index=excluded_index,
        hrp=hrp,
        initial_prefix=initial_prefix,
        fingerprint=fingerprint,
    )
    _stderr("")
    return result
