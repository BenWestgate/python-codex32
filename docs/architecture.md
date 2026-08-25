# Architecture and review order

The package uses one narrow dependency direction:

```text
text -> bounded format/checksum -> fixed profile -> immutable artifact
                                                   |-> BIP93 sharing
                                                   |-> ms/cl generation
                                                   |-> bounded correction
                                                   `-> MasterSeed wallet adapter

CLI -> public APIs above
```

The format layer first validates ASCII, case, separator, characters, and the
absolute size bound. The application parser uses the literal registered HRP
only to reject impossible total and payload lengths before checking the outer
checksum. It then validates the common header, checksum, and S-only application
semantics. No artifact crosses the parsing boundary until every stage passes.

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
| structural alignment | `indel.py` | `test_correction_indel.py` |
| typed BIP32 dependency boundary | `_bip32.py` | BIP32 and wallet vectors |
| fixed wallet derivation and descriptors | `wallet.py` | `test_wallet.py` |
| bounded stdin and fixed-prefix TTY entry | `_cli_input.py` | `test_cli.py` |
| command grammar, dispatch, and presentation | `_cli_parser.py`, `cli.py` | `test_cli.py` |

## Boundaries

- Only parsing and profile-specific factories construct artifacts.
- Headers and artifacts are immutable; shares expose symbols, not bytes.
- Sharing interpolates payload and checksum together, explicitly constructs the
  target header, and reparses the result.
- `generation.py` is the only entropy owner and generates only `ms` and `cl`.
- Correction never edits the HRP or separator and reparses every candidate.
- `wallet.py` accepts only `MasterSeed` and has no state or generic parser.
- `_cli_input.py` retains at most nine artifacts and delegates partial-set
  compatibility to `bip93.py`. Its optional Readline hook restores only the
  latest rejected entry, disables automatic history, and is removed after each
  attempt. While reading, stdout's file descriptor is synchronously redirected
  to the stderr terminal and restored in `finally`, keeping piped results clean.
  There is no persistent history or raw-terminal layer.
- `_cli_parser.py` owns the complete non-abbreviating command grammar.
- `cli.py` contains presentation and dispatch, with no domain algorithm or
  hidden state.

Private Python names are convention rather than access control. The supported
surface is the 25-name package `__all__`; direct use of private helpers is
unsupported but remains in the review scope.

## Size budget

V1 keeps the installed package below 3,000 physical Python lines. Exceeding the
budget requires removing or splitting scope, not merely updating the number.
