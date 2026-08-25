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
timestamp defaults to `0` so recovery scans from genesis. A nonnegative Unix
time or the literal `now` may be supplied; `now` intentionally skips historical
discovery. There is no account database, descriptor parser, policy language,
RPC, or network access.

The CLI makes the public/private choice a mandatory goal rather than a default:

```text
codex32 wallet bitcoin-core watch-only
codex32 wallet bitcoin-core restore
```

Both commands print exactly one compact JSON line suitable for Bitcoin Core's
`-stdin importdescriptors` input. Prompts stay on stderr. `watch-only` is safe to
pipe into a blank wallet created with `disable_private_keys=true`. `restore`
must be used only with a loaded, blank, encrypted descriptor wallet; it warns
before emitting root-xprv descriptors. Bitcoin Core remains responsible for
wallet creation, encryption, unlocking, locking, and storage.

`codex32 wallet multisig-xpub` emits only this seed's origin-qualified BIP48
coordinator key. It does not define cosigners, threshold, descriptor, address,
or complete multisig policy. The direct `codex32 xprv` primitive remains
top-level and carries an explicit secret-root warning.

`tools/bitcoin_core_regtest.py` is the repeatable integration check. It starts
an isolated Bitcoin Core regtest, imports watch-only, `now`, and encrypted
private records, proves matching address and balance discovery, refuses a
watch-only spend, signs and broadcasts from the unlocked private wallet, and
relocks it. It also checks mainnet/testnet key separation and the narrow BIP48
coordinator export. The tool never connects the codex32 package to a node; it
tests the JSON boundary as an external consumer.
