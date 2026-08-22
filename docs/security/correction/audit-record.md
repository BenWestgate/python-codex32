# Gate 4 correction review record

Status: accepted; no unresolved medium-or-higher finding.

## Review identity and scope

- Date: 2026-08-10
- Independent reviewer: Codex sub-agent `gate4_correction_review`
  (`gpt-5.6-sol`, high reasoning), separate from the implementing agent
- Assessed base: `6b02914047c2eb3771f61faa41ba5241faeac6d2`
- Reviewed scoped-file aggregate SHA-256:
  `359db3175caac24715ff643cec2a4eeda43147ac8eb767181ace95bb26d6eddb`
- Method: read-only full-file and diff review plus focused defensive tests

The review covered P70 correspondence, shared GF(32) ownership, imported
lexical/checksum/profile rules, explicit target constants, reverse coordinates
and periods, residue information minimization, immutable HRP/separator handling,
all-profile semantic reparse, failure-stage diagnostics, source/corpus
provenance, transitional structural isolation, public exports, and size.

## Findings and disposition

### G4-01 — incomplete short-period locator mapping (Medium, remediated)

The initial port checked the locator degree and number of GF(1024) roots but did
not require every root to lie in the regular checksum's order-93 position
subgroup. It could therefore drop an unmappable root and return the remaining
partial addends. The worksheet adapter could misreport an invalid residue as
already correct, while the fixed adapter rejected only later during reparse and
misclassified the decoder failure.

Remediation:

- reject repeated/overlapping roots;
- require every wanted root to map to one legal reverse position in the selected
  93- or 1023-symbol period;
- independently apply every proposed BCH or linear addend in the quotient ring
  and require the exact checksum target before returning success;
- freeze worksheet and full-string regressions, including algebra-stage
  diagnostics.

The reviewer reran the reproducer and confirmed residue `t9cxwv58l0sgd` now
returns `None`, and the corresponding fixed-string input returns an algebra
failure with both BCH and linear details.

This guard is intentional local hardening beyond the literal P70 routine. P70
checked the number of field roots but did not check that every short-code root
mapped into the order-93 shortened-code position subgroup. Recording this
distinction keeps the provenance claim precise.

### G4-02 — eager large erasure-sequence copy (Low, remediated)

The residue adapter copied an ordered sequence before enforcing its 13/15-item
maximum. It now checks the sequence length before copying and rechecks the
stable copy. A large `range` regression confirms bounded allocation.

### Provenance limitation (Informational, accepted)

The frozen corpus and PR patch hashes match the manifest. The local environment
had no GHC, Cabal, Nix, or Docker, so no Haskell execution is claimed. The
offline verifier now checks the corpus digest and P70 head before checking all
57 cases. Official checksum vectors, target-constant checks, property tests, and
normal-parser revalidation provide the remaining evidence without a duplicate
polymod implementation.

## Final verification observed by the reviewer

- focused correction/structural/CLI suite: 117 passed;
- optimized profile/correction suite: 127 passed;
- full suite: 361 passed;
- frozen P70-derived corpus: 57 cases verified;
- Ruff and mypy: passed;
- `correction.py`: 645 physical lines, within the 650-line limit;
- removed correction exports: absent.

Final verdict: the initial medium finding and low hardening note are remediated.
No unresolved medium-or-higher correction finding blocks Gate 4.
