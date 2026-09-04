# Security invariants

These rules are mandatory. The [security model](model.md) defines their limits
and evidence.

1. Only parsers and profile factories validate text. Headers precede checksums;
   application rules follow.
2. APIs accept only immutable validated artifacts. Outputs are reparsed;
   recovery and derivation reject incompatible shares.
3. Shared creation uses a separate OS-CSPRNG call for each random initial share,
   gated by confirmation. Input cannot replace entropy or the original secret.
4. Wallet setup uses the original ceremony result or a validated recovered seed.
5. Correction is bounded and fail-closed. Ambiguous or incomplete work gives no
   suggestion; suggestions are untrusted and require confirmation.
6. Secrets stay out of arguments, logs, ordinary output, and public transfers.
   Private descriptors exist only in Python memory and child stdin.
7. Bitcoin Core chains are discovered before entropy or recovery input. The
   operator confirms an eligible descriptor wallet by exact name.
8. Wallet state is revalidated before import. Every import must succeed and the
   exact accepted public descriptor set must match.
9. codex32 has no passphrase channel. An unlocked encrypted signer is relocked
   and verified on every exit path.
10. External text, Core output, public wallet data, and PSBTs are untrusted.
11. Only Bitcoin Core descriptor wallets sign with codex32-derived keys.
    Sensitive operations use only codex32 or Core on malware-free computers
    with trusted software.
12. Offline hosts disable every network path, including Ethernet, internet,
    Tor, Wi-Fi, Bluetooth, and cellular. Online Core nodes synchronize before
    their balances or history are trusted.

Changes require matching model, tests, and security-review evidence.
