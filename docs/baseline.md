# Gate 0 baseline report

## Snapshot

- Base commit: `6b02914047c2eb3771f61faa41ba5241faeac6d2`
- Runtime: CPython 3.13.12
- Relevant installed packages: `bip32==5.0.0`, `coincurve==21.0.0`,
  `click==8.1.8`, `pytest==8.4.2`
- Collection before the Gate 0 fix: 57 tests
- Result before the Gate 0 fix: 56 passed, 1 failed
- Failing test: `tests/test_bip93.py::test_invalid_prefix_or_separator`
- Failure: a parseable unexpected HRP reached checksum validation and raised
  `InvalidChecksum` instead of `MismatchedHrp`.
- Collection after the Gate 0 regression was added: 58 tests
- Result after the Gate 0 fix: 58 passed

The worktree was already dirty when implementation began. Gate 0 preserves the
following pre-existing changes as user work:

```text
 M README.md
 M src/codex32/__init__.py
 M src/codex32/bech32.py
 M src/codex32/bip93.py
 M src/codex32/checksums.py
 M src/codex32/cli.py
 M tests/data/bip93_vectors.py
 M tests/test_bip93.py
?? json
?? os
?? src/codex32/correction.py
?? tests/test_cli.py
?? tests/test_correction.py
```

The untracked files named `json` and `os` were not inspected as requirements
evidence, modified, or deleted.

## Gate 0 patch contract

Incorrect path:

```text
Codex32String.from_string(expected_hrp, text)
  -> decode(expected_hrp, text)
  -> codex32_decode(text)
  -> checksum interpretation
  -> expected-HRP comparison (too late)
```

Required invariant: lexical parsing happens first; when a syntactically
parseable HRP differs from the caller's expected HRP, the code reports
`MismatchedHrp` before applying checksum semantics. A string with the expected
HRP still receives the same checksum, length, header, and payload validation as
before.

Legitimate behavior to preserve:

- missing separators, empty HRPs, invalid characters, and mixed case remain
  lexical errors;
- valid official BIP93 and current CL examples still parse;
- invalid checksums under the expected HRP still raise `InvalidChecksum`;
- Gate 0 does not broaden accepted strings or repair the deferred profile/API
  findings below.

## Reproduced deferred findings

The following fixed, non-secret probes were run before edits:

| Finding | Reproduction evidence | Assigned gate |
|---|---|---|
| Non-`S` share construction from bytes | `Codex32String.from_seed(bytes(range(16)), "ms12testa", 0)` succeeded and exposed 16 bytes | Gate 1 |
| Mutable authenticated metadata | assigning `ident = "faux"` changed the serialized checksummed string | Gate 1 |
| Unknown-HRP fallback | `encode("zz", "0tests", bytes(range(16)), 0)` produced a valid-looking string | Gate 1 |
| Valid BIP93 lengths rejected | encoding a 17-byte `ms` seed raised `InvalidSeedLength` | Gate 1 |
| Wrong checksum selector input | 74 data symbols with an eight-character HRP selected Long codex32 | Gate 1 |
| Existing target is not fresh | `interpolate_at` returns a matching input target unchanged | Gate 2 |
| CRC exposed on all artifacts | public `pad_val`, `has_valid_crc_padding`, and `convertbits(..., "CRC")` are available to shares | Gates 1 and 3 |
| Correction complexity | `src/codex32/correction.py` is 1,471 physical lines and mixes BCH, indels, ranking, deadlines, and result policy | Gates 4–5 |
| CLI/domain coupling | `src/codex32/cli.py` is 1,092 lines and owns RNG, identifiers, interpolation, BIP32, descriptors, correction policy, and hidden account state | Gates 3, 6, and 7 |
| Packaging gap | Click is transitive, no console entry point exists, and CI versions conflict with `requires-python` | Gates 6 and 8 |

These are plausible security or correctness findings, not Gate 0 remediation.
Keeping them executable temporarily is not acceptance; stronger negative tests
must replace unsafe compatibility tests in the same later gate that removes the
behavior.

## Test classification

| Test file | Gate 0 disposition | Evidence value / limitation | Replacement owner |
|---|---|---|---|
| `tests/test_bech32.py` | Keep | Useful inherited Bech32/SegWit primitive regression, but not BIP93 profile evidence | Gate 1 separates reusable codec coverage from unrelated address code |
| `tests/test_bip93.py` | Keep and add focused HRP regression | Official vectors and broad invalid corpus; also asserts mutable/generic API behavior that later becomes invalid | Gates 1–2 replace unsafe API assertions with typed/profile tests |
| `tests/test_cli.py` | Keep | Useful official-vector happy paths and worksheet warning checks; direct `CliRunner` use does not prove installed CLI, capability denial, bounded input, or stdout/stderr contract | Gate 6 replaces with installed subprocess contract tests |
| `tests/test_correction.py` | Keep | Strong BCH/indel outcome examples; several assertions are coupled to current ranking metadata, worker timing, and heuristic internals | Gates 4–5 split algebraic, structural, completeness, proof-state, and benchmark suites |
| `tests/test_descriptor.py` | Keep | Descriptor checksum only; does not validate wallet boundary, authority, derivation, or trusted-template policy | Gate 7 |
| `tests/test_roundtrip_interpolated.py` | Keep temporarily | Encodes the unsafe ability to construct ordinary shares from bytes/padding and therefore must not define the final API | Gate 1 removes it only alongside stronger symbol-level and negative tests |

No Gate 0 test is skipped, marked expected-failure, weakened, or regenerated
from the implementation under test.

## Baseline limitations

- Passing this gate means the evidence is frozen and the pre-existing suite is
  honestly green. It does not mean any row other than the HRP error-ordering
  slice is compliant.
- The baseline includes untracked correction and CLI tests because they are
  part of the assessed worktree, not because their contracts are accepted.
- `README.md` remains WIP and non-authoritative.

## Gate 0 verification

Run from the repository root with the existing virtual environment:

| Command | Result |
|---|---|
| `git status --short` | Succeeded; pre-existing dirty files remain and only the scoped source/test edits plus `docs/` were added |
| `.venv/bin/python -m pytest --collect-only -q` | 58 tests collected |
| `.venv/bin/python -m pytest -q` | 58 passed |
| `.venv/bin/python -O -m pytest -q tests/test_bip93.py::test_invalid_prefix_or_separator tests/test_bip93.py::test_expected_hrp_is_checked_before_checksum_semantics` | 2 passed; pytest emitted its expected warning that ordinary test `assert` statements are disabled under `-O` |
| `git diff --check` | Passed with no whitespace errors |

The focused regression also proves that a damaged checksum still raises
`InvalidChecksum` when `ms` is expected, while the same input raises
`MismatchedHrp` before checksum interpretation when `cl` is expected. No
fallback path bypassing `decode` was added.
