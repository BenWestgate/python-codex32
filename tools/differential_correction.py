"""Verify the compact decoder against the frozen codex32 PR #70 corpus."""

import argparse
import hashlib
import json
from pathlib import Path

from codex32.correction import (
    _correct_fixed,
    _FixedCorrectionFailure,
    _FixedCorrectionSuccess,
)
from codex32.profiles import Profile

_CORPUS_SHA256 = "6aa552b34c0bb2878d45dee2655c331d52e40e41e61cef523415d314ad9948e5"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", required=True)
    arguments = parser.parse_args()
    assert arguments.verify

    root = Path(__file__).resolve().parents[1]
    path = root / "tests" / "data" / "p70_correction_vectors.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _CORPUS_SHA256:
        raise SystemExit("frozen PR #70 corpus digest does not match the manifest")
    document = json.loads(raw)
    if document["source"]["head"] != "610cbad30258c80cd862b3773a20f8099d25e36e":
        raise SystemExit("frozen PR #70 source revision does not match")
    checked = 0
    for case in document["cases"]:
        result = _correct_fixed(
            case["damaged"],
            suspected_profile=Profile.MS,
        )
        expected = case["expected"]
        if expected is None:
            if not isinstance(result, _FixedCorrectionFailure):
                raise SystemExit(f"case {checked}: expected no correction")
        elif not (isinstance(result, _FixedCorrectionSuccess) and result.artifact.text == expected):
            raise SystemExit(f"case {checked}: differential mismatch")
        checked += 1
    print(f"verified {checked} frozen PR #70 correction cases")


if __name__ == "__main__":
    main()
