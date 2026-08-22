# Gate 3A independent design-review record

## Review identity

- Date: 2026-08-09
- Target: Gate 3 generation design before production implementation
- Base revision: `6b02914047c2eb3771f61faa41ba5241faeac6d2` plus the documented Gate 1–2 working tree
- Reviewer: independent Codex sub-agent `/root/gate3_design_audit`
- Implementing agent: `/root` (not the reviewer)
- Decision: **Accepted after revision**

This was an independent agent review, not an external human audit. The
post-implementation Gate 3C review is separately recorded in `audit-record.md`.

## Findings and disposition

| Severity | Finding | Disposition |
|---|---|---|
| Medium | Unbounded exclusions could exhaust the identifier space or cause attacker-controlled fallback work. | Resolved in design: non-text stable Collection, maximum 1,024 entries, snapshotted and validated before entropy. |
| Medium | `split_secret(..., threshold=0)` had no coherent 10+10 or source-collision rule. | Resolved in design: `split_secret` accepts only thresholds 2–9; `generate_*` owns threshold zero. |
| Medium | Fingerprint defaults disclose about 20 seed-derived bits; `k-1` shares plus a guessed S can evaluate the full 10+10 predicate. | Accepted divergence. It is prominent in the threat/risk ledger and must never be described as security-enhancing. |
| Low | Raw provenance is enforceable only at the immediate raw-byte API; a typed `MasterSeed` cannot prove how it was created. | Accepted limitation and documented trust assumption. |
| Low | CRC polynomial names alone do not reproduce the bit convention. | Required complete convention documentation in Gate 3B. |
| Low | Rare BIP32 invalid-master-key failures need branch-specific behavior. | Required implementation/audit check: fresh secret may restart; supplied input fails; post-basis tag failure never resamples masks. |

## Accepted reasoning

The reviewer confirmed that `SystemRandom.sample` is a uniform ordered sample
without replacement on the inspected CPython 3.12–3.14 chain, batched
`byte & 31` mapping is unbiased, unique-padding rejection preserves every
sub-threshold share projection, metadata-only fallback does not bias masks, and
partial-basis completion should remain unsupported.

No medium-or-higher unaccepted design finding remains. Gate 3B may begin.
