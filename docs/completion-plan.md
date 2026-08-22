# BIP93 reference API and CLI completion roadmap

This is the version-controlled canonical roadmap. The README is WIP context,
not a requirements authority. Source revisions are frozen in
`source-manifest.md`, requirements in `traceability.md`, and accepted or open
interpretations in `divergences.md`.

A gate is complete only after its implementation, direct tests, full regression
suite, static checks, and documentation pass. Tests may not be weakened, skipped,
or marked expected-failure to advance a gate.

## Status

| Gate | Subject | Status |
|---:|---|---|
| 0 | Frozen evidence and honest baseline | Complete |
| 1 | Immutable codec, artifacts, and profiles | Complete |
| 2 | Interpolation, recovery, and fresh share derivation | Complete |
| 3 | Audited generation, CRC, identifiers, and random indices | Complete |
| 4 | Compact P70-derived BCH correction core | Complete |
| 5 | Bounded structural correction and result states | Not started |
| 6 | Thin installed core CLI | Not started |
| 7 | Wallet API, xpub, and descriptors | Not started |
| 8 | Independent audit and release readiness | Not started |

## Gate 0 — Frozen evidence and baseline

Own the source manifest, traceability matrix, divergence ledger, and a green
baseline without treating the README as normative. Preserve existing work and
never conceal baseline failures. Completed artifacts are in `docs/`.

## Gate 1 — Immutable codec, artifacts, and profiles

Own bounded lexical parsing, the four fixed profiles, immutable Header/Share/S
artifacts, all 16–64-byte `ms` lengths, data-only short/long checksum selection,
CL semantics, isolated BIP39 S validation, and removal of unsafe byte/share and
unknown-HRP APIs. Completed with ordinary and optimized-Python profile tests,
mypy, the full suite, and public-export checks.

## Gate 2 — Interpolation, recovery, and fresh share derivation

Own R07, R08, the interpolation portion of R10, and BIP39 recovery/derivation in
R20. `recover_secret` requires exactly `k` ordinary shares. `derive_share`
accepts exactly `k` artifacts, may include S, and rejects S, existing, excluded,
or malformed targets. All four fixed profiles opt in explicitly.

Payload and outer checksum are interpolated together. The target header is
explicit and every result is reparsed. BIP39 derivation validates the implied S.
The CLI recovers BIP39 S but does not expose BIP39 derivation. Direct behavior,
property tests, optimized Python, mypy, Ruff, full regression, and documentation
must all pass before this status is Complete.

## Gate 3 — Audited generation, CRC, identifiers, and random indices

The pre-implementation Gate 3A review is accepted in
`security/generation/design-review.md`. Gate 3B centralizes `ms`/CL generation
and S-only splitting in `generation.py`: one batched OS-CSPRNG call per attempted
mask basis, CRC/zero-pad rejection, bounded set-header exclusions, metadata-only
fallback, and unsorted explicit or `SystemRandom.sample` output order.

`split_secret` is restricted to thresholds 2–9; profile-specific generation
APIs alone own threshold zero. Raw `ms` bytes and all CL inputs require an
explicit identifier. Partial-basis and BIP39 generation remain prohibited.
The compact private CRC table is frozen with a complete bit convention and no
human-error optimality claim. Gate 3C reviewed every scoped production file and
every generation entropy/padding/identifier/index branch, remediated one
supporting correction input-boundary defect, and sealed a complete scan with no
reportable or unresolved medium-or-higher finding. The final suite is 287 tests;
the property, optimized-Python, mypy, Ruff, public-export, and diff checks also
pass. The durable decision is in `security/generation/audit-record.md`.
Depends on Gates 1–2.

## Gate 4 — Compact P70-derived BCH correction core

The 645-line `correction.py` has a visible P70 provenance boundary and imports
shared lexical, checksum, profile, parse, and GF(32) behavior. It preserves four
substitutions, every `2e+v <= 8` distribution, eight arbitrary erasures, and the
13/15 consecutive-erasure paths. Reverse index zero is always the final symbol.

`_correct_fixed` requires a suspected registered profile, cannot edit the HRP
or separator, and reparses every candidate. The public residue adapter selects
only by a 13- or 15-symbol residue, accepts period-relative reverse indices, and
learns no HRP or shortened-string length. Existing structural code is isolated
unchanged in internal `indel.py` for Gate 5. Frozen source-derived P70 cases,
property tests, all four profiles, both BIP39 worksheets, optimized Python, and
the size check pass. Decoder outputs additionally require complete legal-period
root mapping and an exact algebraic target check. The focused review found one
medium decoder-soundness defect and one low allocation issue; both were fixed,
retested, and accepted with no unresolved medium-or-higher finding in
`security/correction/audit-record.md`. Depends on Gates 1–3.

## Gate 5 — Bounded structural correction and result states

Add a small structural adapter for bounded insertions/deletions, `?` erasures,
duplicate groups, and transpositions. The complete API is untimed and returns
all best ties; the CLI-facing search distinguishes proven, provisional timeout,
and no-candidate results. Keep correction implementation under 1,000 physical
lines and freeze time/memory budgets. Depends on Gate 4.

Ranking research must evaluate estimated search-space bits, filled erasures,
and known-character substitution addends. For each substitution, consider the
addend's set-bit count together with the number of source characters that could
produce it, then determine a justified sum/product composition. Gate 4 does not
freeze the formula, precedence, units, or tie semantics.

## Gate 6 — Thin installed core CLI

Package `codex32`, declare Click directly, and make non-wallet commands thin
adapters. Enforce the profile capability matrix, sequential protected recovery
input, strict worksheet sizes, BIP39 migration-only UI, correction stderr/status
rules, bounded stdin, and no hidden state or memory-locking claims. Target fewer
than 600 CLI lines. Depends on Gates 1–5.

## Gate 7 — Wallet API, xpub, and descriptors

Move BIP32, BIP48 coordinator xpub, and trusted descriptor rendering into one
stateless `MasterSeed`-only wallet API. Keep root-xprv private descriptors with
an explicit authority warning, remove arbitrary rewriting and the account DB,
and default recovery timestamps to zero. Pin and assess `bip32>=5,<6`. Depends
on Gates 1–3 and 6. "if you already have an RNG capable of generating the source entropy, use it to generate the k initial shares directly, preferably mixing fresh entropy between them."

## Gate 8 — Independent audit and release readiness

Run all unit, property, differential, malformed-input, performance, clean-wheel,
dependency, and Python 3.12–3.14 checks. Independently map every non-deferred
matrix row to one owning function and direct test. Ship only with no unaccepted
medium-or-higher finding, a complete accepted-risk register, security guidance,
migration guide, CLI manual, reproducible release artifacts, and a green matrix.
No GUI work starts before acceptance of this gate.
