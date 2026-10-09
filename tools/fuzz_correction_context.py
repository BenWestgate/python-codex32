"""Dependency-free structured fuzz target for full-string correction context."""

from __future__ import annotations

import sys

from codex32 import CorrectionContext, Profile, correct
from codex32.errors import CodexError

MAX_INPUT = 4096
_PROFILES = tuple(Profile)
_TARGETS = {
    Profile.MS: (48, 74, 127),
    Profile.CL: (74,),
    Profile.BIP39_12W: (56,),
    Profile.BIP39_24W: (82,),
}


def LLVMFuzzerTestOneInput(data: bytes) -> int:
    if not data or len(data) > MAX_INPUT:
        return 0
    selector, payload = data[0], data[1:]
    profile = _PROFILES[selector % len(_PROFILES)]
    text = payload.decode("utf-8", "surrogateescape")
    targets = _TARGETS[profile]
    expected_length = None if selector & 4 else targets[selector % len(targets)]
    base = f"{profile.value}1"
    immutable_prefix = None if selector & 8 else text[: len(base) + 5]
    excluded_indices = () if selector & 16 else tuple(text[5:37])
    try:
        correct(
            CorrectionContext(
                profile,
                expected_length,
                immutable_prefix,
                excluded_indices,
            ),
            text,
        )
    except CodexError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(LLVMFuzzerTestOneInput(sys.stdin.buffer.read(MAX_INPUT + 1)))
