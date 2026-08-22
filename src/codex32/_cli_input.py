"""Bounded stdin and deliberately small interactive codex32 entry."""

from __future__ import annotations

import sys

from codex32.bip93 import (
    Secret,
    Share,
    _validate_basis_prefix,
    _validate_recovery_prefix,
    parse_codex32,
)
from codex32.errors import CodexError
from codex32.profiles import Profile

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025


class InputError(Exception):
    """Report invalid command input without a traceback."""


def _stderr(text: str, *, end: str = "\n") -> None:
    print(text, end=end, file=sys.stderr, flush=True)


def _stdin() -> str:
    value = sys.stdin.read(_MAX_INPUT + 1)
    if len(value) > _MAX_INPUT:
        raise InputError("stdin: input is too long")
    return value


def read_text(prompt: str, *, optional: bool = False) -> str:
    if sys.stdin.isatty():
        _stderr(f"{prompt}: ", end="")
        value = input()
    else:
        value = _stdin()
    value = "".join(value.split())
    if not value and not optional:
        raise InputError("stdin: input must not be empty")
    return value


def _parse(value: str, profiles: tuple[Profile, ...]) -> Artifact:
    try:
        artifact = parse_codex32(value)
    except CodexError as error:
        raise InputError(str(error)) from error
    if artifact.profile not in profiles:
        allowed = " or ".join(profile.value for profile in profiles)
        raise InputError(f"this command accepts only {allowed} codex32 input")
    return artifact


def _prompt_entry(label: str, prefix: str, profiles: tuple[Profile, ...]) -> Artifact:
    _stderr(f"{label}: {prefix}", end="")
    value = "".join(input().split())
    return _parse(value if "1" in value else prefix + value, profiles)


def _redirected(profiles: tuple[Profile, ...]) -> list[Artifact]:
    tokens = _stdin().split()
    if not tokens:
        raise InputError("stdin: input must not be empty")
    if len(tokens) > 9:
        raise InputError("stdin: at most nine artifacts are accepted")
    return [_parse(token, profiles) for token in tokens]


def _interactive(
    *, basis: bool, one: bool, profiles: tuple[Profile, ...]
) -> list[Artifact]:
    accepted: list[Artifact] = []
    prefix, required = "", 1
    while len(accepted) < required:
        number = len(accepted) + 1
        label = (
            "Codex32 share or secret"
            if not accepted
            else f"Codex32 share {number} of {required}"
        )
        try:
            artifact = _prompt_entry(label, prefix, profiles)
            candidate = [*accepted, artifact]
            if not one and (accepted or isinstance(artifact, Share) or basis):
                validator = _validate_basis_prefix if basis else _validate_recovery_prefix
                validator(candidate)
        except (CodexError, InputError) as error:
            _stderr(f"Rejected: {error}")
            continue
        if one:
            return [artifact]
        if not accepted and isinstance(artifact, Secret) and not basis:
            _stderr("Accepted secret.")
            return [artifact]
        if not accepted:
            required = artifact.header.threshold
            prefix = f"{artifact.profile.value}1{required}{artifact.header.identifier}"
            if artifact.text.isupper():
                prefix = prefix.upper()
        accepted.append(artifact)
        noun = "basis item" if basis else "share"
        _stderr(
            f"Accepted {noun} {len(accepted)} "
            f"({len(accepted)} of {required} required)."
        )
    return accepted


def read_artifacts(
    *,
    basis: bool = False,
    one: bool = False,
    profiles: tuple[Profile, ...] = tuple(Profile),
) -> list[Artifact]:
    """Read validated artifacts from bounded stdin or simple TTY prompts."""
    if not sys.stdin.isatty():
        return _redirected(profiles)
    return _interactive(basis=basis, one=one, profiles=profiles)
