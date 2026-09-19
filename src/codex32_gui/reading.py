"""What a field of codex32 text means. No toolkit, no widgets, no state."""

from __future__ import annotations

from dataclasses import dataclass

from codex32 import (
    CorrectionCandidate,
    CorrectionContext,
    Header,
    Profile,
    Secret,
    Share,
    correct,
    parse_codex32,
)
from codex32.bech32 import CHARSET
from codex32.correction import _best
from codex32.errors import CodexError, InvalidShareIndex
from codex32.profiles.ms32 import TEXT_LENGTHS

PREFIX = "MS1"
ALLOWED = frozenset(CHARSET.upper() + "?")
HEADER_LENGTH = 6
GROUP = 4
SLACK = 8


@dataclass(frozen=True, slots=True)
class Reading:
    """What the field currently holds, and what may be done with it."""

    text: str
    artifact: Share | Secret | None
    message: str
    level: str
    expected: int
    unreadable: int

    @property
    def complete(self) -> bool:
        return len(self.text) == self.expected

    @property
    def repairable(self) -> bool:
        return self.complete and self.artifact is None


def normalize(raw: str) -> str:
    """Return the canonical compact text for whatever was typed or pasted."""
    typed = "".join(raw.split()).upper()
    keep = max(size for size in range(len(PREFIX) + 1) if typed[:size] == PREFIX[:size])
    return PREFIX + "".join(character for character in typed[keep:] if character in ALLOWED)


def grouped(text: str) -> str:
    """Return the text in four-character windows."""
    return " ".join(text[start : start + GROUP] for start in range(0, len(text), GROUP))


def header_fault(text: str, accepted: tuple[str, ...] = ()) -> str:
    """Report a header that cannot belong to any card, before more is typed."""
    body = text[len(PREFIX) :]
    if len(body) < HEADER_LENGTH or "?" in body[:HEADER_LENGTH]:
        return ""
    if body[0] not in "023456789":
        return "The character after MS1 is how many cards recovery needs: 0, or 2 through 9."
    try:
        Header(int(body[0]), body[1:5], body[5])
    except InvalidShareIndex:
        return (
            "A backup that was never split is card S. Change the last letter to S, or change the "
            "first character to how many cards recovery should need."
        )
    except CodexError as error:
        return str(error)
    if body[5].lower() in accepted:
        return f"Card {body[5].upper()} has already been entered. This must be a different card."
    return ""


def expected_length(count: int, length: int | None) -> int:
    """Return the backup length being typed towards."""
    if length is not None:
        return length
    return next((valid for valid in TEXT_LENGTHS if valid >= count), TEXT_LENGTHS[-1])


def read(text: str, *, accepted: tuple[str, ...] = (), length: int | None = None) -> Reading:
    """Describe one field value without ever accepting it on the operator's behalf."""
    unreadable = text.count("?")
    expected = expected_length(len(text), length)
    if fault := header_fault(text, accepted):
        return Reading(text, None, fault, "error", expected, unreadable)
    if len(text) == len(PREFIX):
        return Reading(text, None, "Start typing what the card says.", "", expected, unreadable)
    if len(text) != expected:
        counted = f"{len(text)} of {expected} characters"
        return Reading(
            text,
            None,
            f"{counted}, {unreadable} unreadable" if unreadable else counted,
            "",
            expected,
            unreadable,
        )
    if unreadable:
        plural = "s" if unreadable > 1 else ""
        return Reading(
            text, None, f"{unreadable} character{plural} unreadable.", "warning", expected, unreadable
        )
    try:
        artifact = parse_codex32(text)
    except CodexError:
        message = "Every character is there, but they do not check out together."
        return Reading(text, None, message, "error", expected, unreadable)
    return Reading(artifact.text, artifact, "Every character checks out.", "success", expected, 0)


def repair(text: str, length: int | None, excluded: tuple[str, ...] = ()) -> CorrectionCandidate | str:
    """Ask the library for one repair, and offer nothing at all when it is unsure.

    `_best` is the command line's own tie-breaker, minus its Bitcoin Core
    fingerprint hint, which would make repairing a card need a running node.
    Anything still tied afterwards is reported as ambiguous rather than shown.
    """
    try:
        found = _best(correct(CorrectionContext(Profile.MS, length, PREFIX, excluded), text))
    except CodexError as error:
        return str(error)
    if not found:
        return "No repair fits this card. Compare what you typed with the paper again."
    if len(found) > 1:
        return "More than one repair is possible, so none is shown. Check the card again."
    return found[0]
