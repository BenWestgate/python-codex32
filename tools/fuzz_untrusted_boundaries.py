"""Dependency-free structured fuzz target for bounded untrusted inputs."""

from __future__ import annotations

import contextlib
import io
import shlex
import sys

from codex32 import CorrectionContext, Profile, complete_checksum, correct, parse_codex32, recover_secret
from codex32._cli_parser import parser
from codex32.errors import CodexError

MAX_INPUT = 4096
_PROFILES = tuple(Profile)


def LLVMFuzzerTestOneInput(data: bytes) -> int:
    """Exercise one selected boundary; validation failures are expected."""
    if not data or len(data) > MAX_INPUT:
        return 0
    mode, payload = data[0] % 5, data[1:]
    text = payload.decode("utf-8", "surrogateescape")
    try:
        if mode == 0:
            parse_codex32(text)
        elif mode == 1:
            complete_checksum(text)
        elif mode == 2:
            profile = _PROFILES[payload[0] % len(_PROFILES)] if payload else Profile.MS
            correct(CorrectionContext(profile), text)
        elif mode == 3:
            artifacts = [parse_codex32(token) for token in text.split()[:10]]
            recover_secret(artifacts)
        else:
            tokens = shlex.split(text)
            if len(tokens) <= 16 and all(len(token) <= 128 for token in tokens):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    parser().parse_args(tokens)
    except (CodexError, SystemExit, ValueError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(LLVMFuzzerTestOneInput(sys.stdin.buffer.read(MAX_INPUT + 1)))
