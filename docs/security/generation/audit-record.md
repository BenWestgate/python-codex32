# Gate 3C implementation-audit record

## Review identity

- Date: 2026-08-09
- Base revision: `6b02914047c2eb3771f61faa41ba5241faeac6d2`
- Reviewed working-tree snapshot: `codex-security-snapshot/v1:sha256:783b5deb6f982092480c0f61a71f0698565240a2d3549cc6bb33e111af4a94e8`
- Independent generation reviewer: Codex sub-agent `/root/gate3_diff_audit`
- Supporting full-file reviewer: `/root/gate3_diff_audit/repo_surface_map`
- Implementing agent: `/root`
- Decision: **Accepted; no unresolved medium-or-higher finding**

This is an independent agent review, not an external human audit. The complete
sealed scan report is at
`/tmp/codex-security-scans/python-codex32/6b029140_20260809T205214Z/report.md`
for the current workspace session.

## Coverage

The reviewer inspected all Gate 3 generation paths and their direct boundaries:

- every `secrets.token_bytes` and `SystemRandom.sample` call;
- batched u5 mask splitting and absence of entropy injection;
- fresh and existing-S hidden bases;
- CRC and CL zero-padding rejection;
- full-20 and legacy 10+10 identifier calculation;
- bounded set-header exclusions and metadata-only collision fallback;
- payload preservation during reheadering;
- output-index selection and ordering;
- raw-seed and CL identifier requirements;
- BIP39 and partial-basis rejection;
- CLI delegation to the generation API.

All twelve production worklist rows have full-file completion receipts in the
sealed scan bundle. The generation reviewer found no plausible generation
vulnerability.

## Finding and disposition

One supporting-diff candidate was found outside generation: the newly exported
correction search accepted damaged strings beyond its supported envelope before
structural work. Runtime validation confirmed the availability defect. The
repository exposes only an offline library/local CLI, so attack-path policy did
not retain it as a reportable cross-boundary vulnerability. It was nonetheless
fixed before Gate completion by enforcing a 135-character bound—127 canonical
characters plus the documented eight-character recovery allowance—at the
shared decoder before allocation. Both correction entry points have regression
coverage, all 27 correction tests pass, and the full suite passes.

No finding remains unresolved.

## Verification evidence

- Gate 3 focused tests: 81 passed.
- Generation property suite: 55 passed; 20 generated round-trip examples.
- Optimized-Python generation/CRC/BIP93 suite: 147 passed.
- Full suite: 287 passed.
- Mypy: 12 source files passed.
- Ruff: source plus Gate 3/correction tests passed.
- Public export smoke check and `git diff --check`: passed.
- Canonical scan: sealed, complete coverage, 12 work receipts, one candidate
  with discovery/validation/attack-path/remediation receipts, zero reportable
  findings.

## Accepted residual risks

- Fingerprint-derived identifiers disclose approximately 20 seed-derived bits;
  with `k−1` shares and a guessed S, the complete 10+10 predicate is testable.
- Raw provenance is enforceable only at the immediate byte-entry API; a typed
  `MasterSeed` cannot prove its creation history.
- The design depends on CPython 3.12–3.14 behavior and the host OS entropy source.
- CPython does not promise complete secret-object zeroization.
- The long legacy set-tag serialization relies on `bip32` v5 behavior outside
  BIP32's recommended seed-length range.

These are explicit accepted risks or environmental limits, not unresolved audit
findings. Gate 8 must revalidate them before release.
