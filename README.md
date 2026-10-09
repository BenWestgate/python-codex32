![python-codex32: Create, repair, and recover bitcoin backups](https://raw.githubusercontent.com/BenWestgate/python-codex32/master/docs/images/python-codex32-banner.jpg)

# python-codex32

Reference implementation of BIP-0093 (codex32): checksummed, SSSS-aware BIP32 seed strings.

This repository implements the codex32 string format described by BIP-0093.
It provides parsing and validation, regular/long codex32 checksums, and Shamir secret sharing
scheme (SSSS) recovery and share derivation.

## Features
- Parse and validate codex32 strings with `parse_codex32`.
- Regular checksum (13 chars) and long checksum (15 chars) support.
- Recover a secret from `k` shares with `recover_secret`.
- Derive a share at a fresh index with `derive_share`.
- Typed, immutable `Header`, `Share` and `Secret` values.
- Profiles for BIP32 master seeds (`ms`), Core Lightning secrets (`cl`) and
  BIP39 entropy (`bip39_12w`, `bip39_24w`).
- No third-party runtime dependencies.

## Security
Caution: This is reference code. Verify carefully before using with real funds.

## Installation
**Compatibility:** Python 3.10–3.15

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
from codex32 import derive_share, parse_codex32, recover_secret

a = parse_codex32("MS12NAMEA320ZYXWVUTSRQPNMLKJHGFEDCAXRPP870HKKQRM")
c = parse_codex32("MS12NAMECACDEFGHJKLMNPQRSTUVWXYZ023FTR2GDZMPY6PN")
print(a.header)  # Header(threshold=2, identifier='name', index='a')

secret = recover_secret([a, c])
print(secret.text)  # MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW
print(secret.seed_bytes.hex())  # d1808e096b35b209ca12132b264662a5

print(derive_share([a, c], "d").text)  # a new share at index d
```

## Tests
```bash
pip install -e '.[dev]'
python -m pytest
```
