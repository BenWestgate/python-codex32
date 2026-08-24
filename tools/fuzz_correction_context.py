"""Dependency-free structured fuzz target for full-string correction context."""

from __future__ import annotations

import sys

from codex32 import CorrectionContext, Profile, correct
from codex32.errors import CodexError

MAX_INPUT = 4096
_PROFILES = tuple(Profile)


def LLVMFuzzerTestOneInput(data: bytes) -> int:
    if not data or len(data) > MAX_INPUT:
        return 0
    selector, payload = data[0], data[1:]
    profile = _PROFILES[selector % len(_PROFILES)]
    text = payload.decode("utf-8", "surrogateescape")
    expected_length = None if selector & 4 else len(text)
    expected_header = None if selector & 8 else text[:5]
    excluded_indices = () if selector & 16 else tuple(text[5:37])
    try:
        correct(CorrectionContext(profile, expected_length, expected_header, excluded_indices), text)
    except CodexError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(LLVMFuzzerTestOneInput(sys.stdin.buffer.read(MAX_INPUT + 1)))
