# Security Hardening Proposal: Centralize Electronic Generation

## Decision

Adopt the retained-basis metadata-fallback design in
[implementation/metadata-fallback.md](../implementation/metadata-fallback.md).
`split_secret` is a sharing operation for thresholds 2–9; threshold-zero
creation belongs to profile-specific generation APIs. Snapshot at most 1,024
excluded set headers before entropy.

## Executive Recommendation

We considered Option 1, **independent random identifiers**; Option 2,
**fail or regenerate on collision**; and Option 3, **retain the basis and
replace metadata**. We should move all generation into one auditable module and
use Option 3 under the accepted usability policy. It keeps the requested
deterministic identifier behavior, but when it collides it relabels and
re-checksums the already accepted payloads instead of resampling them. This
preserves the mask distribution and avoids a TTY-only continuation.

The strongest privacy alternative is to use independent random identifiers for
every generated set. I would choose that option if eliminating the roughly
20-bit public predicate outweighed deterministic backup disambiguation. Under
the accepted current policy, metadata-only fallback is the narrower change.

## Evidence

I inspected the pre-Gate-3 generation helpers and the Gate 2 construction and
interpolation boundary. The observed ownership split, combined with the
inferred collision-conditioning risk, most influenced this proposal.

| Evidence | Finding or document | What it establishes |
|---|---|---|
| G-E03 | `src/codex32/bip93.py` | Immutable construction, exact-threshold recovery, and share derivation already have one domain owner. |
| G-E05 | `src/codex32/cli.py` | The CLI currently owns entropy, basis construction, identifiers, and output selection. |
| G-E07 | [BIP93 generation](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0093.mediawiki#generating-shares) | The two supported bases are `k` fresh masks or S plus `k-1` masks. |
| G-E09 | CPython `random.py` 3.12–3.14, inventoried in [evidence.md](../evidence.md) | `SystemRandom.sample` uses OS-backed rejection sampling and preserves selection order. |
| G-T01 | [Generation threat model](../threat-model.md) | Padding-rejection uniformity, identifier disclosure, and metadata-only collision reasoning. |

G-E03, G-E05, G-E07, and G-E09 are observed source/document claims. G-T01 is
an inferred security analysis derived from those sources and the accepted API
contract.

## Current Design And Failure Mode

The CLI currently samples one character at a time, constructs temporary
artifacts, derives metadata, and selects a canonical prefix of indices. There
is no public generation contract and no single owner that can be independently
checked for every entropy call.

A naïve collision fix would discard a basis whenever its deterministic header
is excluded. That is not merely inefficient: the successful default output is
then conditioned on a predicate derived from the secret or masks. Asking the
user to rerun does not remove the conditioning and creates separate TTY and
pipeline semantics.

An unbounded exclusion collection creates a different failure. If every
identifier for one threshold is excluded, random fallback never terminates;
near saturation permits attacker-controlled CSPRNG and CPU consumption. We
therefore snapshot a maximum of 1,024 entries before any entropy is drawn.

## Desired Invariants

- Every fresh basis mask symbol is an unbiased u5 value from one OS-CSPRNG
  byte batch per attempted basis.
- Existing-secret generation samples S plus exactly `k-1` uniform masks; fresh
  generation samples exactly `k` uniform masks.
- Padding rejection never rejects a basis because of metadata.
- Explicit target-header collisions fail before new mask entropy.
- Derived target-header collisions retain every payload symbol.
- Output selection happens after basis acceptance and preserves selection order.
- No public function accepts entropy, padding, partial shares, or continuation
  state.

## Constraints And Non-Goals

We support CPython 3.12–3.14 and depend on its OS-random `SystemRandom`
implementation. We do not promise deterministic tests for random order, memory
zeroization, recovery from a compromised host, partial-basis completion, BIP39
generation, or proof that the selected CRCs are optimal for transcription
damage.

## Before Architecture

[The before diagram](../diagrams/generation-boundary-before.mmd) shows the CLI
owning entropy, interpolation orchestration, identifiers, and presentation.
That ownership makes the specification-to-code mapping harder to audit and
invites a later GUI to duplicate domain behavior.

## Options

### Option 1: Independent random identifiers

This option is cryptographically cleanest. Four independent u5 symbols disclose
no fingerprint predicate and remove the weak-seed oracle. It has negligible
runtime and memory cost and simplifies the metadata branch.

Its cost is product semantics rather than implementation complexity: it gives
up the accepted deterministic wallet/set recognition behavior and changes
frozen output fixtures. It should win if independent review or user research
finds the linkage/disclosure cost greater than the disambiguation benefit.

The [before](../diagrams/generation-boundary-before.mmd) and
[Option 1 after](../diagrams/generation-boundary-independent-random-identifiers-after.mmd)
diagrams show identifier entropy becoming independent of the accepted basis.

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Identifier source | Seed/share fingerprint | Four independent u5 symbols | Removes the 20-bit seed predicate | Loses deterministic disambiguation and legacy fixtures |
| Generation owner | CLI helpers | One domain module | Prevents interface duplication | Foundational refactor |

Rollout would use the same new generation boundary as Option 3 but omit both
fingerprint helpers. Rollback restores the accepted deterministic policy. No
stored codex32 string changes; only newly generated identifiers differ.

### Option 2: Fail or regenerate on collision

The attractive part of this option is its apparent simplicity: keep the legacy
identifier and reject the rare collision. What gives us pause is that the
predicate is applied to the secret-generation result. Automatic regeneration
and manual rerun both select which default attempts are returned. A prompt also
keeps secret material alive across an unbounded human delay and creates
interrupt/crash paths. We reject this option.

The [Option 2 after diagram](../diagrams/generation-boundary-regenerate-on-collision-after.mmd)
makes the problematic feedback edge explicit: public metadata can send an
already accepted basis back to entropy.

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Collision handling | Undefined | Discard/retry or user rerun | Conditions returned default attempts | Extra entropy/work and interrupted ceremonies |
| TTY behavior | Existing monolithic create | Potential prompt/continuation | Adds retained-secret and crash paths | More CLI state and test surface |

This option could be rolled out quickly, which is its strongest case, but the
distributional defect is intrinsic. Rollback would remove the retry branch; no
additional evidence is likely to make it preferable.

### Option 3: Retain basis and replace metadata

The selected option derives the default only after accepting the basis. If the
five-symbol target header is excluded, it samples a new four-symbol identifier,
leaving all S/share payloads untouched, and recreates only headers and outer
checksums. The [after diagram](../diagrams/generation-boundary-metadata-fallback-after.mmd)
shows that collision handling cannot flow back to basis entropy.

This preserves the accepted deterministic default in the normal case and does
not condition masks in the collision case. It costs a small reheader helper and
a bounded metadata retry loop. Its residual risk is the fingerprint disclosure
it intentionally retains.

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Generation ownership | CLI-owned helpers | `generation.py` | One auditable entropy boundary | Foundational move and API migration |
| Mask sampling | One choice per character | One OS byte batch per attempted basis | Simple unbiased byte-to-u5 mapping | Holds one complete batch temporarily |
| Collision handling | Undefined | Randomize four metadata symbols only | Preserves every accepted payload | Reheader/rechecksum helper |
| Exclusions | No bounded contract | Stable, non-text, maximum 1,024 | Prevents exhaustion/near-saturation DoS | Rejects oversized API collections |
| Output selection | Canonical prefix | Explicit order or ordered random sample | Selection cannot affect S | New CLI options |

## Comparison

| Dimension | Random identifiers | Fail/regenerate | Metadata fallback |
|---|---|---|---|
| Seed disclosure | None from identifier | Retains ~20-bit predicate | Retains ~20-bit predicate |
| Basis distribution | Unconditioned | Conditioned on default success | Unconditioned |
| User continuation | None | Possible | None |
| Legacy default | No | Yes on success | Yes when noncolliding |
| Audit surface | Smallest | Retry/prompt policy | Small bounded reheader policy |

## Recommendation

Use Option 3 under the accepted usability decision. Option 1 becomes preferable
if the project withdraws acceptance of deterministic fingerprint leakage.
Option 2 should not be shipped.

## Evidence Coverage And Residual Risk

| Evidence | Coverage | Residual risk |
|---|---|---|
| G-E03 — Gate 2 domain boundary | Reused for authenticated construction and interpolation | Python private names are convention, not access control |
| G-E05 — CLI-owned generation | Addressed by one generation owner | Gate 6 still owns the broader CLI-size reduction |
| G-E07 — BIP93 generation | Implements both specified basis shapes | Electronic random output indices are a deliberate divergence |
| G-E09 — CPython sampling | Direct audited `SystemRandom.sample` path | Other Python implementations/versions are not covered |
| G-T01 — threat model | Metadata-only fallback and bounded exclusions | Accepted fingerprint disclosure and OS-CSPRNG trust remain |

## Migration And Rollout

Gate 3 lands as one API/CLI unit after Gate 3A acceptance. Old CLI generation
helpers are removed rather than retained as compatibility paths. Existing
valid codex32 strings continue to parse; raw CLI seed input newly requires an
explicit identifier and explicit electronic indices preserve their requested
order. Rollback reverts the whole Gate 3 unit without restoring unsafe share
byte factories.

## Validation Plan

- Exercise all `ms` byte lengths, thresholds 2–9, CL, explicit selectors, and
  all-31 sampling.
- Verify CRC/zero-padding and exact-threshold recovery for returned outputs.
- Freeze full-20 and legacy 10+10 fixtures.
- Force a derived collision without replacing entropy and compare payloads.
- Inspect every entropy call, rare BIP32 exception edge, and CLI routing in a
  separate Gate 3C diff audit.
- Run ordinary and optimized Python, mypy, Ruff, the full suite, public-export
  smoke checks, and `git diff --check`.

## Implementation Work Packages

The exact ownership, validation order, entropy call sites, rare BIP32 behavior,
and audit checks are in
[implementation/metadata-fallback.md](../implementation/metadata-fallback.md).
The implementation must be reviewed as a diff; this proposal is not remediation
evidence.

Work is divided into the generation module, thin CLI routing, invariant tests,
documentation/traceability, verification, and the independent Gate 3C audit.

## Open Questions

No blocking design question remains. Future research may revisit independent
random identifiers or compare CRC behavior under measured human error models;
neither changes the Gate 3 contract.
