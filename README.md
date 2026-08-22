# python-codex32

Reference implementation of BIP-0093 (codex32): checksummed, SSSS-aware BIP32 seed strings.

This repository implements the codex32 string format described by BIP-0093.
It provides encoding/decoding, regular/long codex32 checksums, CRC padding for base conversions,
Shamir secret sharing scheme (SSSS) interpolation helpers and helpers to build codex32 strings from seed bytes.

## Features
- Encode/decode codex32 data via `from_string` and `from_unchecksummed_string`.
- Regular and long codex32 checksum support.
- Construct codex32 strings from raw seed bytes via `from_seed`.
- `from_seed` uses default bech32-encoded BIP32 fingerprint identifier and CRC padding.
- Interpolate shares recover secrets via `interpolate_at`.
- Correct checksum errors and marked erasures.
- Parse codex32 strings and access parts via properties.
- Mutate codex32 strings by reassigning `is_upper`, `hrp`, `k`, `ident`, `share_idx`, `data`, and `pad_val`.
- Supports Bech32/Bech32m and segwit address format aswell.

## Security
Caution: This is reference code. Verify carefully before using with real funds.

## Installation
**Compatibility:** Python 3.10–3.14

**Recommended:** use a virtual environment
### Linux / macOS
```bash
python -m venv .venv
source .venv/bin/activate
pip install codex32
```
### Windows
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install codex32
```


## Quick usage
```python
from codex32 import Codex32String

# Create from seed bytes
s = Codex32String.from_seed(
    bytes.fromhex('ffeeddccbbaa99887766554433221100'),
    "ms13cashs",        # prefix string, (HRP + '1' + header)
    0                   # padding value (default "CRC", otherwise integer)
)
print(s.s)              # codex32 string

# Parse an existing codex32 string and inspect parts
a = Codex32String("ms13casha320zyxwvutsrqpnmlkjhgfedca2a8d0zehn8a0t")
print(a.hrp)            # human-readable part
print(a.k)              # threshold parameter
print(a.ident)          # 4 character identifier
print(a.share_idx)      # share index character
print(a.payload)        # payload part
print(a.checksum)       # checksum part
print(len(a))           # length of the codex32 string
print(a.is_upper)       # case is upper True/False
print(s.data.hex())     # raw seed bytes as hex
print(a.pad_val)        # padding value integer, (MSB first)



# Create from unchecksummed string (will append checksum)
c = Codex32String.from_unchecksummed_string("ms13cashcacdefghjklmnpqrstuvwxyz023")
print(str(c))           # equivalent to print(c.s)

# Interpolate shares to recover or derive target share index
shares = [s, a, c]
derived_share_d = Codex32String.interpolate_at(shares, target='d')
print(derived_share_d.s)

# Create Codex32String object from existing codex32 string and validate any HRP
e = Codex32String.from_string("cl", "cl10lueasd35kw6r5de5kueedxyesqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqanvrktzhlhusz")
print(e.ident)
print(e.s)

# Relabel a Codex32String object
e.ident = "cln2"
print(e.ident)
print(e.s)

# Uppercase a Codex32String object (for encoding in QR codes or handwriting)
e.is_upper = True
print(e.s)
```

## Tests
``` bash
pip install -e .[dev]
pytest
```

## Command-line interface (CLI)

Treat Codex32 shares, unchecksummed payloads, and debiased dice output as secret
material. The CLI never accepts them as command-line arguments or environment
variables. This keeps them out of process listings and ordinary shell history.

When run from a terminal, the CLI prompts visibly so that long handwritten
strings can be checked during entry. When standard input is redirected, shares
may be separated by any whitespace:

```bash
python -m codex32.cli share D < protected-shares.txt
```

Recover and print the codex32 secret, or explicitly derive wallet material:

```bash
python -m codex32.cli secret < protected-shares.txt
python -m codex32.cli xprv < protected-shares.txt
python -m codex32.cli descriptors < protected-shares.txt
```

Running `python -m codex32.cli` without a command only displays help; it never
reads secret material or derives wallet keys.

Verify checksums and structure without deriving wallet material:

```bash
python -m codex32.cli verify < protected-shares.txt
```

Do not write a literal secret in a command such as `echo 'SECRET' | ...`; the
literal command may be retained in shell history. Redirect a protected file,
use a trusted secret provider, or enter the material at the CLI prompt. The CLI
disables core dumps and attempts to lock its process memory, but Python cannot
guarantee that every secret copy will remain out of swap on every platform.

Create a fresh backup, or redirect one raw hexadecimal BIP32 master seed or one
existing codex32 secret into `create`:

```bash
python -m codex32.cli create --threshold 2 --shares 5
```

Complete the Book's checksum worksheet using its non-pink bold squares:

```bash
python -m codex32.cli checksum HEADER
```

For privacy, omit the argument and prepend the header to the protected standard
input instead of placing it in shell history or a process listing.

**DANGER:** Incorrect input can make the wallet predictable and cause permanent
loss of funds. Enter only characters generated by following the codex32
dice-debiasing worksheet exactly. Do not enter raw dice rolls, seed words,
hexadecimal seeds, passwords, or anything else. The command only appends a
checksum; it does not debias dice rolls or verify randomness.

Run `checksum` separately for every initial share whose checksum you need. The
computer can read every payload processed and may keep copies, even across
separate invocations. Use only a trusted offline computer. A computer used later
with `secret`, `xprv`, or `descriptors` necessarily receives enough shares to
recover the wallet; if that computer is compromised, an attacker may recreate
the private keys and steal all funds.

Correct substitutions or unreadable characters by entering one damaged string.
Use `?` as a placeholder for every unreadable character so that all positions
remain unchanged:

```bash
python -m codex32.cli correct --pretty
```

`--pretty` is also accepted after `create` and `checksum`; it groups the output
for transcription. Without it, these commands emit an unadorned string suitable
for parsing or redirection.

The checksum corrects up to four unknown substitutions, or combinations where
twice the substitutions plus the marked erasures is at most eight. Consecutive
erasure bursts can sometimes be recovered up to the checksum length (13 regular
or 15 long characters). The command also searches insertion and deletion
alignments with multiple worker threads for at most ten seconds, applying the
fast checksum correction to each alignment. Logical search-space size determines
both which repair classes are attempted first and which candidates are shown.
The search returns once no unsearched class can produce a lower-scoring
candidate; equal-scoring alternatives are not exhaustively searched. Adjacent
character transpositions are recognized without a separate search; duplicated,
omitted, transposed, and erroneous complete four-character groups have bounded
fast paths. By default, insertion/deletion correction searches the closest
standard total length of 48, 74, or 127 characters. Use `--search-seconds` to
choose a shorter limit.

A checksum-valid correction is only a suggestion. Compare every legible
character and every reported edit against the physical backup. Do not pipe
correction output directly into recovery or wallet-import commands. Correction
is not authentication: after recovery, also confirm the identifier, wallet
fingerprint, descriptors, and expected wallet history before using the result.

For a privacy-preserving worksheet workflow, enter only the final 13- or
15-symbol residue. Optional erasure positions count backward from the end;
position 1 is the final character:

```bash
python -m codex32.cli correct --residue --erasure 17 --erasure 29
```

This mode prints the Bech32 character to add at each reverse position with the
worksheet wheel. It receives neither the codex32 string nor its application,
HRP, payload length, or complete length.
