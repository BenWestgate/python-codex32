# Gate 6 reviewability report

The analysis and editing pass completed within the 45-minute maximum. Test,
lint, type-check, build, and integration time is excluded from that timebox.

## Before

- installed Python: 2,998 physical lines;
- excluding `correction.py` and `indel.py`: 1,903 lines;
- largest modules: `correction.py` 710, `cli.py` 385, `indel.py` 385, and
  `bip93.py` 334 lines.

## After

- installed Python: 2,997 physical lines;
- excluding `correction.py` and `indel.py`: 1,903 lines;
- largest modules: `correction.py` 709, `cli.py` 385, `indel.py` 385, and
  `bip93.py` 334 lines;
- net reduction: one installed line, while retaining the Gate 4 behavior added
  immediately before this pass.

The pass removed a one-use correction-profile alias, simplified rejected-input
prefill flow, reused a single deadline value, and removed an unnecessary local
immutable-prefix forwarding variable. It restored readable wrapping around the
new profile and target selection rather than manufacturing a larger reduction
through dense lines.

## Human-reader review

The three CLI modules were reviewed as a proposed consolidation. They remain
separate because grammar construction, protected terminal input, and command
dispatch/presentation are distinct boundaries; one roughly 770-line CLI module
would save little and obscure stdout/stderr and immutable-prefix reasoning.

One-use helpers in checksum selection, BIP32 adaptation, interpolation,
generation, and correction were retained where their names expose a normative
algorithm or validation boundary. The fixed and structural correctors remain
separate under the invariant that `indel.py` enumerates alignments and
`correction.py` repairs symbols. Some explicit code was deliberately left less
compact because shortening it would require dense comprehensions, generic flag
helpers, or hidden conversions.

## Compatibility and security

- CLI commands, options, defaults, prompt meaning, exit statuses, and stream
  separation are unchanged by the Gate 6 refactor.
- No public Python API was removed or intentionally changed.
- Validated artifacts, immutable correction context, complete-frontier search,
  correction-as-suggestion, entropy, sharing, and wallet boundaries are
  preserved.
- No dependency was added for source reduction.

Larger reductions require product or compatibility decisions. They are recorded
in [reviewability-removals.md](reviewability-removals.md), including BIP39 and
Core Lightning profiles, direct private-authority exports, and moving structural
recovery into a separately audited package.

## Verification

The complete ordinary and optimized suites, strict mypy, Ruff lint and format,
Hypothesis runs, frozen correction differential, wallet differential, checksum
constant verification, package-size check, build, and Twine validation pass.
The final installed package contains 2,997 physical Python lines.

Clean installed wheel and sdist environments passed the package verifier and
the Bitcoin Core 31.1.0 regtest workflow. Two builds with the same
`SOURCE_DATE_EPOCH` produced byte-identical wheels and sdists; a focused backend
regression also verifies deterministic archive metadata. The printable HTML
recovery materials are present in the sdist.

Gate 6 passes. Gate 5's human study remains independently open and therefore
blocks Gate 7; this reviewability result does not claim that study or a final
independent audit occurred.
