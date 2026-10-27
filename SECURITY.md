# Security

codex32 handles wallet backup and recovery secrets. Have the software and
recovery plan reviewed before using real funds.

## Trusted computer

A **trusted computer** is one you control, believe is free of malware, and whose
operating system and other software you trust. Use one for backup creation,
recovery, wallet setup, and signing.

Follow [Bitcoin Core's wallet-encryption guidance][core-wallet]. Encryption
cannot fully protect your bitcoins from malware, as [Core's encryption dialog
warns][core-dialog]. Keep your wallet passphrase safe.

For stronger isolation, use an offline signing computer that never connects to
any network, as in [Bitcoin Core's offline-signing tutorial][core-offline].

A valid checksum detects many copying mistakes. It does not prove that a backup
belongs to your wallet. A correction is only a suggestion; compare it with the
physical backup and wallet information kept elsewhere.

codex32 is designed to avoid accidental disclosure. Commands may display recovery
material when that is their purpose. Python and the operating system may retain
copies in memory, terminal scrollback, or disk. Tails and shutdown reduce this
risk but do not guarantee erasure.

[core-wallet]: https://github.com/bitcoin/bitcoin/blob/v32.0/doc/managing-wallets.md#12-encrypting-the-wallet
[core-dialog]: https://github.com/bitcoin/bitcoin/blob/v32.0/src/qt/askpassphrasedialog.cpp
[core-offline]: https://github.com/bitcoin/bitcoin/blob/v32.0/doc/offline-signing-tutorial.md

## Report a security problem

Send vulnerability reports privately to the maintainer address in
`pyproject.toml`; do not open a public issue. Include the affected revision or
release, reachable attack path, security impact, and a minimal reproducer using
synthetic, unfunded test material. Do not include real seeds, shares, private
keys, wallet descriptors, or funded-wallet data.

Examples of reportable security failures include:

- accepting damaged or unchecked text as a valid backup;
- combining the wrong number or an incompatible set of shares;
- using a correction without clear operator confirmation;
- sending secret material to the wrong output stream; or
- selecting a nonempty or otherwise unsafe Bitcoin Core destination;
- placing private descriptors or a Core passphrase in command arguments; or
- performing unbounded work on damaged input.

## Project boundary

codex32 has no graphical interface, wallet database, secret storage, direct RPC
socket, or general network client. Bitcoin master-seed creation and restoration
invoke a reviewed `bitcoin-cli` from `PATH`, restricted to `127.0.0.1`, to
initialize a wallet the user created in Bitcoin Core. Bitcoin Core, its
configuration, and that executable are part of the trusted destination.
codex32 never handles the Core wallet passphrase.

Security researchers and API developers should read the detailed
[security model](docs/security/model.md), which records the threat boundaries,
required properties, known platform limitations, and correction analysis.
