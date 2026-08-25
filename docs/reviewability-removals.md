# Reviewability removal candidates

These are release-boundary decisions, not approved changes. Gate 6 preserved the
documented CLI and public API, so none was implemented.

## Remove BIP39 migration profiles

- **Surface:** `bip39.py`, two profile specifications, fixed correction support,
  sharing tests, worksheet fixtures, and migration documentation.
- **Approximate reduction:** one complete profile concept and roughly 70--100
  installed lines, plus a substantial test and documentation corpus.
- **Review benefit:** removes an embedded SHA-256 checksum, two fixed lengths,
  and the distinction between share validation and semantically valid S.
- **Compatibility cost:** existing codex32 BIP39 worksheet shares would no longer
  be recoverable. A separate migration utility would be required.
- **Security effect:** narrows accepted formats and removes mnemonic-migration
  ambiguity; it does not strengthen `ms` recovery.
- **Boundary:** major release with deprecation and an archived standalone tool.

## Remove the Core Lightning profile

- **Surface:** `Profile.CL`, `CoreLightningSecret`, CL generation and CLI paths,
  vectors, correction cases, and recovery documentation.
- **Approximate reduction:** roughly 80--120 installed lines and one application
  branch across parsing, generation, correction, and presentation.
- **Review benefit:** leaves only Bitcoin master seeds and optional migration
  material, reducing cross-profile length and padding reasoning.
- **Compatibility cost:** breaks existing codex32 HSM-secret backups and removes
  a documented Core Lightning recovery route.
- **Security effect:** narrows the artifact domain but strands a distinct secret
  type if no replacement tool is retained.
- **Boundary:** major release only; deprecation and a maintained recovery utility
  are required.

## Remove direct private-authority exports

- **Surface:** `master_xprv`, the `xprv` command, and possibly `wallet bitcoin-core
  restore`; corresponding warning, parser, wallet, and integration paths.
- **Approximate reduction:** 30--60 installed lines depending on whether private
  descriptor restoration remains.
- **Review benefit:** removes root-authority presentation and one class of secret
  stdout output.
- **Compatibility cost:** users would need wallet-specific offline tooling for
  restoration and could no longer verify the official xprv boundary directly.
- **Security effect:** reduces accidental key disclosure, but may push users to
  less-reviewed conversion tools.
- **Boundary:** major release with a documented replacement workflow.

## Move structural correction to a dedicated recovery package

- **Surface:** `indel.py`, correction-context structural integration, structural
  benchmarks/capture tools, CLI search policy, and the large associated corpus.
- **Approximate reduction:** about 400 installed lines here, while moving rather
  than eliminating most of the review burden.
- **Review benefit:** the base codec becomes smaller and fixed BCH correction is
  easier to audit independently.
- **Compatibility cost:** the advertised missing/extra-character and group
  recovery promise would require another installed package or executable.
- **Security effect:** a clean package boundary could isolate resource-intensive
  untrusted search, but version skew between codec and recovery tool becomes a
  new risk.
- **Boundary:** major release only. Do not split the code until the receiving
  package has the same capture bound, immutable-prefix rules, and audit coverage.

## CLI module consolidation considered and rejected

The parser, protected-input adapter, and command/presentation adapter total
roughly 770 lines. Combining them would remove a few import and module-header
lines, but would couple argparse grammar, file-descriptor redirection, secret
entry policy, correction confirmation, and domain dispatch in one large file.
The current three modules each enforce a recognizable boundary, so consolidation
would make security review slower rather than easier. This is not recommended
without a broader CLI redesign.
