"""Bounded stdin and deliberately small interactive codex32 entry."""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable, Iterator
from typing import Protocol

from codex32.bip93 import (
    Secret,
    Share,
    _validate_basis_prefix,
    _validate_recovery_prefix,
    parse_codex32,
)
from codex32.errors import (
    CodexError,
    DuplicateShareIndex,
    InvalidChecksum,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    SecretInRecoverySet,
)
from codex32.profiles import Profile, _profile_label

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025


class _LineEditor(Protocol):
    def insert_text(self, text: str) -> None: ...

    def set_auto_history(self, enabled: bool) -> None: ...

    def set_startup_hook(self, function: Callable[[], object] | None) -> None: ...


_line_editor: _LineEditor | None
try:
    import readline as _readline
except ImportError:
    _line_editor = None
else:
    _line_editor = _readline


class InputError(Exception):
    """Report invalid command input without a traceback."""


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
        assert editor is not None
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
    try:
        os.dup2(stderr_fd, stdout_fd)
        yield
    finally:
        try:
            sys.stdout.flush()
        finally:
            try:
                os.dup2(saved_stdout, stdout_fd)
            finally:
                os.close(saved_stdout)


def read_text(prompt: str, *, optional: bool = False) -> str:
    if sys.stdin.isatty():
        value = _editable_input(f"{prompt}: ")
    else:
        value = _stdin()
    value = "".join(value.split())
    if not value and not optional:
        raise InputError("No input was provided.")
    return value


def _parse(value: str, profiles: tuple[Profile, ...]) -> Artifact:
    try:
        artifact = parse_codex32(value)
    except CodexError as error:
        message = _FRIENDLY_SET_ERRORS.get(type(error), str(error))
        raise InputError(message) from error
    if artifact.profile not in profiles:
        allowed = " or ".join(_profile_label(profile) for profile in profiles)
        raise InputError(f"This command accepts only {allowed} input.")
    return artifact


def _prompt_entry(label: str, prefix: str, prefill: str) -> str:
    return "".join(_editable_input(f"{label}: {prefix}", prefill).split())


def _retry_text(value: str, prefix: str) -> str:
    if not prefix or "1" not in value:
        return value
    if value[: len(prefix)].lower() == prefix.lower():
        return value[len(prefix) :]
    return ""


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
    *, basis: bool, one: bool, profiles: tuple[Profile, ...]
) -> list[Artifact]:
    accepted: list[Artifact] = []
    prefix, prefill, required = "", "", 1
    while len(accepted) < required:
        number = len(accepted) + 1
        label = (
            "Enter a codex32 string" if not accepted else f"Enter string {number} of {required}"
        )
        try:
            value = _prompt_entry(label, prefix, prefill)
            artifact = _parse(value if "1" in value else prefix + value, profiles)
            if not one and (accepted or isinstance(artifact, Share) or basis):
                validator = _validate_basis_prefix if basis else _validate_recovery_prefix
                validator([*accepted, artifact])
        except (CodexError, InputError) as error:
            message = _FRIENDLY_SET_ERRORS.get(type(error), str(error))
            _stderr(f"Rejected: {message}")
            prefill = _retry_text(value, prefix)
            continue
        prefill = ""
        if one:
            return [artifact]
        if not accepted and isinstance(artifact, Secret) and not basis:
            _stderr("Secret accepted.")
            return [artifact]
        if not accepted:
            required = artifact.header.threshold
            prefix = f"{artifact.profile.value}1{required}{artifact.header.identifier}"
            if artifact.text.isupper():
                prefix = prefix.upper()
        accepted.append(artifact)
        _stderr(f"{'String' if basis else 'Share'} {len(accepted)} of {required} accepted.")
    return accepted


def read_artifacts(
    *,
    basis: bool = False,
    one: bool = False,
    profiles: tuple[Profile, ...] = tuple(Profile),
) -> list[Artifact]:
    if not sys.stdin.isatty():
        return _redirected(profiles)
    return _interactive(basis=basis, one=one, profiles=profiles)
