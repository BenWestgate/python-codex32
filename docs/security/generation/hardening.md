# Security Hardening Review: Electronic Generation

## Evidence Basis

We reviewed the frozen BIP93 and supporting sources, the Gate 2 artifact and
interpolation boundary, the existing CLI-owned generation code, and CPython's
`SystemRandom.sample` implementation chain. The complete inventory and source
identities are in [evidence.md](evidence.md). This analysis precedes the Gate 3
implementation and does not claim the selected controls are already present.

## Constraints

Generation is a security-critical reference path. We cannot add an injectable
entropy seam, partial-basis mode, or share byte semantics for test convenience.
We must preserve explicit and sampled output order. Derived metadata collisions
must not condition which accepted secret polynomial is returned.

The deterministic identifier policy is an accepted medium disclosure, not a
security control. If the project later prioritizes information-theoretic
privacy over deterministic disambiguation, independent random identifiers are
the cleaner design.

## Opportunity Portfolio

| Opportunity | Evidence | Options | Recommendation | Proposal |
|---|---|---|---|---|
| Centralize and bound electronic generation | BIP93 basis rules, current CLI ownership, CPython sampling chain, identifier threat analysis | Independent random identifiers; regenerate/fail; retained-basis metadata fallback | Retained-basis fallback under the accepted usability policy | [Generation boundary](proposals/generation-boundary.md) |

## Recommendation Summary

I recommend one `generation.py` owner for validation, entropy, basis acceptance,
identifier policy, and output selection. What makes the selected option
proportionate is that a collision changes only public metadata: it neither
throws away an accepted basis nor creates interactive secret continuation
state. The important caveat is equally clear—the fingerprint default continues
to disclose a seed predicate. Independent random identifiers should replace it
if that disclosure is no longer an accepted product tradeoff.

## Next Decisions

The revised design passed the independent Gate 3A review. Gate 3B may proceed,
followed by a separate diff-based implementation audit. Gate 3 is not complete
until the latter records no unresolved medium-or-higher finding.
