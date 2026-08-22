# Fixed profile capabilities

There is no unknown-profile fallback or runtime registration.

| Capability | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| parse S/share | yes | yes | yes |
| semantic S bytes | 16–64 | exactly 32 | no |
| checksum completion API | yes | yes | no |
| recovery and API share derivation | yes | yes | yes |
| CLI share derivation | yes | yes | no |
| fresh generation / S splitting | yes | no | no |
| fixed BCH API | yes | yes | yes |
| fixed BCH CLI | yes | yes | no |
| wallet API | S only | no | no |

`ms` payloads encode every byte length from 16 through 64 and may have any legal
parsed trailing bits. `cl` has 52 payload symbols; parsed discarded bits remain
application data. BIP39 profiles have exactly 27/53 payload symbols; S requires
zero outer padding and a valid embedded SHA-256 checksum. Ordinary BIP39 shares
are random masks and receive structural validation only.

CL support exists to verify, recover, and extend legacy codex32 backups. Current
Core Lightning fresh recovery uses mnemonics, so this project does not generate
new CL secrets or split an S into a fresh set.
