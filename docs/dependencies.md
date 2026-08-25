# Runtime dependency review

The package retains one direct runtime dependency: `bip32>=5,<6`. Only
`src/codex32/_bip32.py` imports it. That 49-line typed adapter exposes the three
operations this project needs and converts an invalid master scalar to
`CodexError`. Bitcoin Core cannot replace it because Core has no interface that
derives this project's root key or wallet records from raw seed bytes.

Python 3.12 and 3.13 are supported. Python 3.14 is an explicitly non-blocking
CI probe until the selected Coincurve release publishes 3.14 wheels and the
required platform matrix passes. It is not a v1 support claim.

## Reviewed Coincurve 21 resolution

The published `bip32` 5.0.0 metadata says `coincurve>=15,<21`. Upstream owner
Antoine Poinsot's open [PR #53](https://github.com/darosior/python-bip32/pull/53)
changes only that range to `<22` and adds Coincurve 21 to upstream CI. The CLI
constraint carries its exact commit
`45db547bdf5a5bc19a8c55ef447dbf9169928792`; the archive SHA-256 is
`a25be30641b381eed9a5249bbc4a73124905223c9c50f93140f519bcf259e415`.
The compatible library dependency remains unchanged, so this is not a local
BIP32 fork or a change to the installed implementation.

The resolution is:

| Package | Version | License | Purpose |
|---|---:|---|---|
| `bip32` | 5.0.0 plus PR #53 metadata | BSD-3-Clause | BIP32 private-tree derivation |
| `coincurve` | 21.0.0 | MIT or Apache-2.0 | libsecp256k1 binding |

The installed dependency license-file SHA-256 values are:

- BIP32 `LICENCE`: `ba32f1ce36d4b107164ff3b70f145eca686e6e5e74f9080f628545ebe9209dcc`;
- Coincurve `LICENSE-MIT`: `d502748a33db7ade1318e37f0b5f219f478330ed74a673e387756e53fb516715`;
- Coincurve `LICENSE-APACHE`: `cebfb5eab4eff50df87c3c5e7eb11a634d0fa32bb4b6380800f82fae606599ae`;
- Coincurve's retained `LICENSE-cffi` notice:
  `04b80f5b077bbed68808cfebadeb5e3523f2a8c9a96495c587bd96df1eac2a33`.

Coincurve 21 removes the former runtime CFFI and ASN.1 dependencies. Its
[release notes](https://github.com/ofek/coincurve/releases/tag/v21.0.0) record
Python 3.13 support and libsecp256k1 0.6.0. Its CPython 3.12 and 3.13 release has
binary wheels for Intel and ARM macOS, x86-64/ARM/i686 glibc and musl Linux,
and AMD64/ARM64 Windows. `requirements/cli-dependencies.txt` pins every one of
those wheel hashes and prohibits a Coincurve source build.

The BIP32 patch archive is pure Python. `requirements/cli-build-dependencies.txt`
pins the universal Setuptools 80.9.0 wheel used to build it, and the dependency
installation disables build isolation. A clean Python 3.13 install completed
without a compiler and `pip check` reported no broken requirements.
Setting `SOURCE_DATE_EPOCH=1763060600`, the upstream patch commit time, produced
the same BIP32 wheel twice: SHA-256
`637e98a3fc3318d29a6bf69025abe0dbe4a02f5911fabd8443b16ef4f5088176`.
Without that environment variable, ZIP timestamps make the wheel hash vary even
though its files are identical. CI sets it explicitly.

## Reproducible project archives

The project build uses the reviewed Setuptools 80.9.0 pin and a thin backend in
`build_backend.py`. The backend delegates every standard hook to
`setuptools.build_meta`; when
`SOURCE_DATE_EPOCH` is set, its only additional operation is to normalize the
sdist gzip and tar timestamps and ownership metadata. Content-related PAX
headers remain intact. Without the variable, ordinary Setuptools behavior is
unchanged.

Two complete builds from the same working tree with
`SOURCE_DATE_EPOCH=1763060600` produced byte-identical wheels and sdists. The
wheel SHA-256 in both runs was
`5e65b332739e239de63ee91fac673b086c8aae6f82d11d0cdf4b2975378008b2`;
the sdist equality was checked byte for byte rather than recording its digest
inside the archive itself. Twine accepted all four artifacts. The sdist includes
the backend, tests, tools, Markdown evidence, printable recovery card, and
separate verification record. `tests/test_build_backend.py` independently
regresses removal of variable archive metadata while preserving file content
and non-metadata PAX fields.

## Compatibility evidence

The Coincurve APIs used by `bip32` were inspected at tags v20.0.0 and v21.0.0:
`PrivateKey`, its `secret` property and `add` method, plus `PublicKey`,
`from_secret`, `combine_keys`, and `format`. Their signatures, libsecp256k1
operations, and `ValueError` failure behavior are unchanged at this boundary.

On 2026-08-24 under Python 3.13.12:

- all seven upstream `bip32` tests passed with Coincurve 21, including the four
  official private-tree BIP32 vectors and invalid extended-key cases;
- all 499 repository tests passed with the carried patch and Coincurve 21;
- a deterministic corpus covered all seed lengths 16--64, 64 cases per length,
  both networks, root xprvs, BIP48 account xpubs, and all public/private Core
  descriptors;
- all 6,272 records matched Coincurve 20 and 21 byte for byte, with SHA-256
  `a51c9833408bd02d8fbafc339a7d4b48ada02af655e268e0bd165040c45b0249`.

`python tools/differential_wallet.py --verify` reproduces the last check. A
resolved dependency, adapter, or vector change requires the upstream and local
suites plus this corpus before publication.

GitHub Actions
[run 32729045916](https://github.com/BenWestgate/python-codex32/actions/runs/32729045916)
passed on 2026-08-24 at revision
`aa10d59b60c375f4abbf4df241a8bf3c6ae46507`. All tests, strict mypy, Ruff,
formatting, correction and wallet differential checks, and package builds
passed under Python 3.12 and 3.13 on Ubuntu, macOS, and Windows. The allowed
Python 3.14 experimental job stopped while resolving Coincurve 21 because no
compatible wheel is published; it did not affect the successful required
matrix conclusion.

Pip-audit 2.10.1, using its PyPI advisory service on 2026-08-24, reported no
known vulnerability for exact versions BIP32 5.0.0 and Coincurve 21.0.0. The
local unpublished codex32 release candidate is necessarily outside that service,
and this result is a known-advisory check rather than a cryptographic audit.

## Bounded `cryptography` prototype

A private-seed-only prototype using `cryptography` 50.0.0 was evaluated before
this decision. It matched all 17 official vector path outputs and the complete
6,272-record corpus. Five forced HMAC cases explicitly checked zero or
out-of-range master scalars, out-of-range child tweaks, zero child scalars, and
the valid zero-tweak case.

It did not meet the replacement cut conditions:

- 167 implementation lines would replace the 49-line adapter, taking the
  installed project from 2,999 to about 3,117 physical Python lines;
- the corpus took about 90 seconds rather than 27 seconds in this diagnostic
  run;
- the installed cryptography/CFFI surface was about 17 MB, compared with a
  2.6 MB Coincurve install, and introduced CFFI plus a general OpenSSL binding;
- cryptography 50.0.0 publishes no Intel macOS or Windows ARM wheel, while
  Coincurve 21 covers both.

The prototype proved feasibility, not a security or performance benchmark.
Because it is neither materially smaller nor easier to audit and violates the
line and wheel criteria, the roadmap retains `bip32` behind its narrow adapter.

## Development-tool baseline

Most development tools remain compatible ranges or unpinned extras rather than
a reproducible release environment. Ruff is pinned to 0.16.2 because it defines
the formatting baseline. On 2026-08-24 the existing Python 3.13.12 environment
also contained pytest 8.4.2, Hypothesis 6.165.2, mypy 2.3.0, build
1.2.2.post1, and Twine 6.2.0. A mechanical 110-column Ruff baseline reconciles
the inherited formatting at 2,970 production lines; a 100-column probe produced
3,021 and was rejected. New code still prefers lines under 100 characters when
that preserves readability.
