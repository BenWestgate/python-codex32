# Wallet interoperability

Wallet operations accept only a validated `MasterSeed`. They are stateless and
never accept shares, Core Lightning secrets, BIP39 migration artifacts, or raw
bytes.

The public adapter has three functions:

- `master_xprv(secret, testnet=False)` returns the BIP32 root extended private
  key.
- `multisig_account_xpub(secret, account=0, testnet=False)` returns a native
  SegWit BIP48 account xpub with origin information at
  `m/48h/coin_typeh/accounth/2h`.
- `core_descriptors(...)` returns fixed BIP44, BIP49, BIP84, and BIP86 Bitcoin
  Core `importdescriptors` records.

Public descriptors contain account xpubs. Private descriptors intentionally
follow Bitcoin Core's root-key form: they contain the root xprv followed by the
complete derivation path. They therefore grant authority over the entire root,
not only the selected account. The CLI warns before printing them.

Account, network, private/public mode, and timestamp are explicit inputs. The
timestamp defaults to `0` so recovery scans from genesis. There is no account
database, descriptor parser, policy language, RPC, or network access.
