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

## Accepted limitations

- Python cannot guarantee secret zeroization, constant-time execution, locked
  memory, or absence of copies in the runtime, operating system, terminal, or
  caller.
- `bip32>=5,<6` is a security-sensitive dependency. This project wraps it
  narrowly and verifies BIP93 BIP32 vectors, but does not independently audit
  its cryptographic implementation.
- Fresh unshared `ms` identifiers expose 20 bits of the BIP32 fingerprint.
  Shared sets use random or explicit identifiers; raw seeds and re-sharing
  require an explicit identifier.
- Generation-only CRC padding is a small recovery hint, not authentication or
  a codex32 validity requirement.
- BCH correction detects/corrects bounded symbol errors but cannot establish
  that a candidate was intended. The HRP and separator are never corrected.
- Private descriptors contain the root xprv by design (like Bitcoin Core).

## Out of scope

The project has no GUI, network access, RPC, secret storage, wallet database,
arbitrary descriptor parser, plugin/profile registry, structural correction
search, partial-basis completion, BIP39 mnemonic conversion, or fresh Core
Lightning secret generation. Adding one of these requires a separate threat
model and explicit scope decision.
