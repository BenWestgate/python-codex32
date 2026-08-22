# Deliberate divergences and unresolved decisions

This ledger prevents implementation choices from being mistaken for BIP93
requirements. “Accepted” means accepted for the planned v1 contract, not
implemented by the Gate 0 codebase.

| ID | Decision | Source relationship | State | Owning gate / required evidence |
|---|---|---|---|---|
| D01 | Support every byte-aligned `ms` seed length from 16 through 64 bytes. Do not impose a 32-bit multiple restriction. | Matches BIP93; rejects closed/unmerged PR #2077 as authority. | Implemented | Gate 1 exhaustive length/padding and checksum-boundary tests |
| D02 | Do not adopt the `wallets.md` weighted-distance ranking without evidence. Gate 5 will evaluate estimated search-space bits, filled erasures, and a composition using each known substitution addend's set-bit count and number of plausible source characters. | Deliberate divergence from optional/recommended wallet guidance, not from BIP93's correction capacity. Bech32 ordering motivates—but does not by itself prove—a lower-bit-error preference. | Research requirement; formula not selected | Gate 5 must justify units, sum/product composition, precedence, and tie semantics with deterministic tests |
| D03 | Electronically generated shared sets use random distinct output indices by default; `--indices` requests an exact ordered set. Neither path is sorted. | Deliberate divergence from BIP93/Book canonical initial index ordering for electronic generation. | Accepted and implemented | Gate 3 audited `SystemRandom.sample` path, ordering tests, and privacy rationale |
| D04 | `bip39_12w` and `bip39_24w` are migration-only profiles. The API may verify, recover, and derive an additional share; CLI/GUI expose only `verify` and `secret`. | The website marks the schemes not recommended; BIP93 advises fresh migration rather than BIP39 interconversion. | API sharing implemented; final installed CLI pending | Gate 2 validates implied S and denies CLI derivation; Gate 6 freezes installed command contract |
| D05 | Machine-generated `ms` secrets use the compact private CRC1–CRC4 table in otherwise arbitrary pad bits. Parsed BIP93 secrets accept every legal pad value. Shares never have CRC or byte semantics. | CRC is a local recovery hint, not BIP93 validity. Koopman catalogue rankings do not prove human-transcription optimality. | Accepted and implemented | Gate 3 exact bit convention, behavioral vectors, rejection-sampling proof, and no polynomial-selection claim |
| D06 | Fresh unshared `ms` uses 20 public BIP32-fingerprint bits; fresh shared sets use random identifiers; raw seeds and re-sharing require explicit identifiers. | BIP93 leaves identifier selection open. This confines the fingerprint predicate to threshold-zero generation and avoids seed-derived shared-set metadata. | Accepted metadata tradeoff | Gate 3; frozen threshold-zero fixtures and shared-generation invariants |
| D07 | Private Bitcoin Core descriptors retain the root xprv plus path; coordinator output uses an account xpub with origin. | Matches documented Bitcoin Core design rather than minimizing private-key authority. | Accepted | Gate 7; Core citation, golden fixtures, and explicit root-authority warning |
| D08 | The complete API is untimed and returns every best-rank tie. The CLI has a default ten-second deadline and may display a clearly provisional best candidate on stderr with nonzero status. | BIP93 treats corrections as suggestions; wallet guidance supplies the UI timeout. | Accepted | Gates 5–6; proof-state and timeout contract tests |
| D09 | Unknown HRPs are rejected by all public parsing and domain operations. No unknown profile inherits `ms` checksum, length, or interpolation rules. | Narrower than generic codex32 experimentation and the unmerged generalized-HRP draft. | Implemented | Gate 1 fixed registry and valid-generic-checksum rejection test |
| D10 | Deriving an additional share rejects the secret index and an existing index. | Enforces BIP93's “fresh share index” wording even though the current/Rust reference returns an existing share unchanged. | Implemented | Gate 2 target tests |
| D11 | Computer recovery validates every input but does not impose the Book's separate hand-computation verification ceremony. | Treats the Book's critical verification step as protection against manual arithmetic errors. | Accepted | Gate 6; CLI guidance review |
| D12 | Partial-basis completion is not a v1 feature and has no public or CLI entry point. `split_secret` accepts S only. | Discussed/speculated functionality has no authoritative contract and risks same-header split-brain sets and nonuniform CRC-constrained completion. | Deliberately deferred | Research backlog after release |
| D13 | Structural correction initially targets complete bounded searches through four arbitrary insertions/deletions, plus small auditable fast paths. | Beyond BIP93's normative substitution/erasure capacity; no published indel ECWs exist. | Accepted envelope, performance unproven | Gate 5; benchmarks and under-1,000-line budget |

## Explicit ambiguities still requiring evidence

- The practical damaged-string recovery benefit of the compact CRC table is
  not established. Gate 3 freezes its convention as a small hint without
  claiming optimality; future ECW research may compare human error models.
- Fingerprint-derived identifiers are an accepted medium disclosure, not an
  unresolved benignity assumption. Independent random identifiers remain the
  preferred alternative if the usability tradeoff is later rejected.
- The BIP39 worksheet profiles are intentionally isolated. Their embedded
  BIP39 checksum is semantic validation for a recovered `S`, not permission to
  expose mnemonic, entropy, creation, checksum-completion, correction, or
  wallet-derivation APIs.
- Correction search bounds are product behavior, not checksum guarantees. A
  timeout or incomplete search must never be represented as an exhaustive API
  result.
- Worksheet residue correction is intentionally application-agnostic. A
  reverse position may lie outside the undisclosed shortened string; the human
  or application holding that string decides whether it applies.
