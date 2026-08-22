# Registered profile capabilities through Gate 4

There is no unknown-profile fallback and no runtime profile registration.

| Capability | `ms` | `cl` | `bip39_12w` | `bip39_24w` |
|---|---:|---:|---:|---:|
| Parse and verify S/share | Yes | Yes | Yes | Yes |
| Payload symbols | Yes | Yes | Yes | Yes |
| Semantic bytes on S | 16–64 | Exactly 32 | No | No |
| Checksum completion API | Yes | Yes | No | No |
| Secret byte factory | S only | No | No | No |
| Public exact-threshold recovery | Yes | Yes | Yes | Yes |
| Public fresh-share derivation | Yes | Yes | Yes | Yes |
| CLI recovery | Yes | Yes | Yes | Yes |
| CLI share derivation | Yes | Yes | No | No |
| Fresh generation API/CLI | Yes | No | No | No |
| Typed-S splitting API/CLI | Yes | No | No | No |
| Fixed BCH correction API | Yes | Yes | Yes | Yes |
| Full-string correction CLI | Transitional `ms` only | No | No | No |
| Default identifier | Fingerprint for k=0; random for shared | Never | No | No |
| Generation padding | Private CRC hint | No generation | No | No |
| Wallet-key boundary | `MasterSeed` only | No | No | No |

## Payload and checksum rules

| Profile | Payload | Outer checksum | S-only semantic validation |
|---|---|---|---|
| `ms` | `ceil(8*n/5)` symbols for every `n=16..64` | common expanded-codeword rule | decode to `n` bytes; any legal trailing partial bits |
| `cl` | 52 symbols | common expanded-codeword rule | exactly 32 bytes; trailing partial bits are application data |
| `bip39_12w` | 27 symbols / 132 semantic bits | short | zero outer pad and valid 4-bit embedded SHA-256 checksum |
| `bip39_24w` | 53 symbols / 264 semantic bits | short | zero outer pad and valid 8-bit embedded SHA-256 checksum |

Ordinary BIP39 shares are uniform symbol masks. Their payloads must have the
profile's exact length but must not be interpreted as BIP39 entropy or checked
against the embedded S checksum.

All four fixed profiles support linear sharing in the API. BIP39 recovery and
derivation validate the implied S; BIP39 derivation remains API-only as a
migration aid. No profile gains generation, checksum completion, or wallet
features merely by enabling linear sharing.

The internal fixed BCH adapter accepts every registered profile. The common
format layer selects its checksum, and reparsing the candidate means BIP39
S semantics still apply. The Gate 4 CLI keeps its pre-Gate-6 full-string policy;
generic worksheet-residue mode has no profile to prohibit or expose.

Generation permission is deliberately separate from linear-sharing permission.
Only `ms` enters `generation.py`; CL and BIP39 artifacts cannot be split even
though callers may recover or derive an additional share through the API.
