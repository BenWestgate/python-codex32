# Architecture and review order

The package uses one narrow dependency direction:

```text
text -> bounded format/checksum -> fixed profile -> immutable artifact
                                                   |-> BIP93 sharing
                                                   |-> ms generation
                                                   |-> fixed BCH correction
                                                   `-> MasterSeed wallet adapter

CLI -> public APIs above
```

The format layer validates ASCII, case, separator, common header shape, total
length, and the checksum selected from total string length plus HRP length. Only
then does the HRP select one of four fixed application profiles. A profile adds
exact payload length and S-only semantics; it does not replace format validity.

## Specification-to-code map

| Concept | Single owner | Evidence |
|---|---|---|
| lexical/u5 codec and checksum boundary | `bech32.py` | `test_bech32.py`, `test_profiles.py` |
| checksum and CRC arithmetic | `checksums.py` | official vectors, `test_crc.py` |
| fixed application rules | `profiles.py`, isolated `bip39.py` | `test_profiles.py`, `test_bip39.py` |
| immutable header/artifacts and interpolation | `bip93.py` | BIP93 vectors, `test_sharing.py` |
| entropy, masks, identifiers, output indices | `generation.py` | `test_generation.py` |
| shared GF(32) arithmetic | `gf32.py` | sharing vectors and correction corpus |
| fixed BCH and worksheet correction | `correction.py` | `test_correction_bch.py` |
| typed BIP32 dependency boundary | `_bip32.py` | BIP32 and wallet vectors |
| fixed wallet derivation and descriptors | `wallet.py` | `test_wallet.py` |
| bounded stdin and fixed-prefix TTY entry | `_cli_input.py` | `test_cli.py` |
| options, commands, and presentation | `cli.py` | `test_cli.py` |

## Boundaries

- Only parsing and profile-specific factories construct artifacts.
- Headers and artifacts are immutable; shares expose symbols, not bytes.
- Sharing interpolates payload and checksum together, explicitly constructs the
  target header, and reparses the result.
- `generation.py` is the only entropy owner and accepts only `ms`.
- Correction never edits the HRP or separator and reparses every candidate.
- `wallet.py` accepts only `MasterSeed` and has no state or generic parser.
- `_cli_input.py` retains at most nine artifacts and delegates partial-set
  compatibility to `bip93.py`. Its optional Readline hook restores only the
  latest rejected entry, disables automatic history, and is removed after each
  attempt. While reading, stdout's file descriptor is synchronously redirected
  to the stderr terminal and restored in `finally`, keeping piped results clean.
  There is no persistent history or raw-terminal layer.
- `cli.py` contains no domain algorithm or hidden state.

Private Python names are convention rather than access control. The supported
surface is the 19-name package `__all__`; direct use of private helpers is
unsupported but remains in the review scope.

## Size budget

V1 keeps production Python below 3,000 physical lines. No module may exceed 650
lines; the generation, CLI, and wallet owners stay below 350, 500, and 250
lines respectively. Exceeding a budget requires removing or splitting scope,
not merely updating the number.
