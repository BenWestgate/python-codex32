# Fixed profile capabilities

There is no unknown-profile fallback or runtime registration.

| Capability | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| parse S/share | yes | yes | yes |
| semantic S bytes | 16–64 | exactly 32 | no |
| checksum completion API | yes | yes | no |
| recovery and API share derivation | yes | yes | yes |
| CLI share derivation | yes | yes | no |
| fresh generation API | 16–64 bytes | exactly 32 bytes | no |
| fresh generation CLI | 16 or 32 bytes | exactly 32 bytes | no |
| existing-S splitting | yes | yes | no |
| fixed BCH API | yes | yes | yes |
| fixed BCH CLI | yes | yes | no |
| bounded structural API | yes | yes | yes |
| bounded structural CLI | yes | yes | no |
| wallet API | S only | no | no |

`ms` payloads encode every byte length from 16 through 64 and may have any legal
parsed trailing bits. The API can generate every such length, and the CLI can
import an existing hexadecimal seed at every such length. To avoid creating
unusual or pending-boundary backups by default, fresh CLI generation accepts
only the established 16- and 32-byte sizes. `cl` has 52 payload symbols; parsed
discarded bits remain application data. BIP39 profiles have exactly 27/53
payload symbols; S requires zero outer padding and a valid embedded SHA-256
checksum. Ordinary BIP39 shares are random masks and receive structural
validation only.

CL generation is explicit and uses a random identifier unless one is supplied.
Current Core Lightning defaults to mnemonic recovery, but its recovery command
retains an import path for codex32 HSM secrets. Generated CL S strings use the
zero-padding convention emitted by CLN; parsed nonzero discarded bits remain
valid and are preserved when re-sharing.
