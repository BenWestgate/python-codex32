# Security

codex32 handles wallet recovery material. A **trusted computer** is under your
exclusive control, is not known or suspected to be compromised, and runs an
operating system and other software you trust for the operation. For wallet
work, that trusted software includes Python, codex32, the terminal,
`bitcoin-cli`, Bitcoin Core, and their relevant configuration. Wallet encryption,
application permissions, and RPC authentication do not make a compromised
computer trusted. Have the
software and recovery plan reviewed before relying on it with funds. For
stronger isolation, keep the trusted computer disconnected from every network
before, while, and after it handles private recovery or signing material.

A valid checksum detects many copying mistakes. It does not prove that a backup
belongs to your wallet. A correction is only a suggestion; compare it with the
physical backup and wallet information kept elsewhere.

Python, your terminal, and your operating system may retain secret text in
memory or scrollback. codex32 does not intentionally save secrets and keeps
them out of command arguments, logs, and unrelated output. Commands that create,
recover, derive, correct, or explicitly export recovery material intentionally
display it when that is their purpose. codex32 cannot guarantee that every copy
is erased from swap, hibernation data, or crash dumps. Using Tails and shutting
down when finished helps mitigate this Python limitation.

Run a command first and enter recovery material at its prompt, or redirect its
standard input from a separately protected source. Do not embed recovery text in
shell command text: shell history, terminal logging, wrappers, and process
tooling may retain it even though codex32 never receives it as an argument.

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
