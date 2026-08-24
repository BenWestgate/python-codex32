# Restoring an inherited backup

An heir may have the backup without knowing how its owner built the wallet.
codex32 can validate and combine the backup, but the backup alone does not say
which wallet software, accounts, or multisig policy the owner used.

Work on a reviewed offline computer. Do not enter a secret or share into a
website, online QR generator, chat service, or network-connected wallet. A
successful checksum proves that the text is internally valid; it does not prove
that it belongs to the intended wallet.

## Identify the material

`codex32 check` reports whether one secret or share is intact. Its backup
identifier, recovery threshold, and share index can help organize several
pieces. Matching labels suggest that shares form one set, but they are public
metadata rather than authentication.

It is not necessary to run `check` before a recovery command. `secret`, `share`,
and the wallet commands validate each entry as it is supplied.

For a Bitcoin master-seed backup, prefer creating a watch-only wallet before
displaying or exporting private material:

```bash
codex32 wallet bitcoin-core watch-only
```

The command accepts a complete secret or the required shares and recovers the
seed internally. Its output contains public descriptors, not the recovered
secret. Run codex32 offline and transfer only those public descriptors to the
online Bitcoin Core system. See [Air-gap transfer](cli.md#air-gap-transfer).

Compare the resulting wallet with an independently recorded master fingerprint,
receiving address, or transaction history before restoring signing ability.
Checksums detect accidental damage; they do not prevent deliberate replacement.

The Bitcoin Core export covers the standard single-key purposes supported by
this project. A multisig or nonstandard wallet also requires its original
descriptor or policy, cosigner information, derivation paths, and signature
threshold. `wallet multisig-xpub` exports this seed's public cosigner key; it
does not reconstruct a multisig wallet by itself. Verify the completed policy
and first receiving address on independent devices before relying on it.

## Information the owner should leave

Keep recovery instructions separate from every secret and share. They should
identify:

- mainnet or testnet;
- wallet software and whether the wallet is single-signature or multisig;
- account numbers, derivation policy, and approximate wallet creation date;
- an expected master fingerprint or known receiving address;
- the share threshold and the locations of the shares;
- for multisig, the complete policy, coordinator, cosigners, and where their
  backups are held; and
- a trusted person who can review the recovery.

Do not put a seed, share, xprv, private descriptor, wallet passphrase, or device
PIN on this information sheet. Public wallet metadata cannot spend funds, but
it can reveal balances and transaction history and should still be kept private.

Private Bitcoin Core restoration should be attempted only after the watch-only
wallet is confirmed. Follow [Private Bitcoin Core
restoration](cli.md#private-bitcoin-core-restoration).
