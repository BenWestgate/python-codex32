# Security policy and model

Do not report vulnerabilities by opening a public issue. Contact the maintainer
at the address in `pyproject.toml` and include the affected revision, observed
behavior, security impact, and a minimal reproducer. Do not include a real seed
or wallet.

## Security properties

- Unchecked text cannot enter sharing, generation, correction output, or wallet
  operations as a validated artifact.
- The common codex32 checksum is verified before an HRP selects application
  payload semantics.
- Artifacts and headers are immutable. Shares have symbol semantics only and
  cannot be constructed from or converted to bytes.
- Recovery requires exactly the declared threshold of compatible, distinct
  ordinary shares. Derivation requires a fresh ordinary index.
- Generation draws complete masks from the operating-system CSPRNG and exposes
  no entropy injection, padding control, or partial-basis interface.
- Wallet operations accept only `MasterSeed`.
- Correction produces untrusted suggestions, never authenticated input to a
  wallet operation.

## Accepted release risks

The durable dispositions, controls, and review triggers are recorded in the
[accepted-risk register](docs/accepted-risks.md). In particular, this version
intentionally follows the frozen checksum-boundary behavior of pending BIP93
PR #2258. That creates a known compatibility risk for 44--46-byte `ms` strings;
there is no dual decoder. Fresh CLI generation is limited to 16 or 32 bytes,
while the API and imported existing seeds retain every BIP93 size from 16
through 64 bytes.

## Accepted limitations

- Python cannot guarantee secret zeroization, constant-time execution, locked
  memory, or absence of copies in the runtime, operating system, terminal, or
  caller.
- On supported terminals, a rejected entry is temporarily retained for editing.
  Automatic Readline history is disabled and this project never writes a history
  file, but terminal scrollback and Python or native editor memory may retain it.
- `bip32>=5,<6` is a security-sensitive dependency. This project wraps it
  narrowly and verifies BIP93 BIP32 vectors, but does not independently audit
  its cryptographic implementation.
- Fresh unshared `ms` identifiers expose 20 bits of the BIP32 fingerprint.
  Shared sets, supplied raw seeds, re-sharing, and CL generation use random or
  explicit identifiers.
- Generation-only CRC padding is a small recovery hint, not authentication or
  a codex32 validity requirement.
- BCH correction detects/corrects bounded symbol errors but cannot establish
  that a candidate was intended. The HRP and separator are never corrected.
- Private descriptors contain the root xprv by design (like Bitcoin Core).

## Out of scope

The project has no GUI, network access, RPC, secret storage, wallet database,
arbitrary descriptor parser, plugin/profile registry, structural correction
search, partial-basis completion, or BIP39 mnemonic conversion. Adding one of
these requires a separate threat model and explicit scope decision.
