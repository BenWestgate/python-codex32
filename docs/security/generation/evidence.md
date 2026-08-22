# Gate 3 generation evidence inventory

Frozen on 2026-08-09. Repository paths are relative to the project root.
The hashes identify the Gate 3A pre-implementation snapshot. Gate 3B changes
the same paths, so a later current-file hash mismatch is expected and is not a
retroactive change to the evidence reviewed.

| ID | Evidence | Identity / role |
|---|---|---|
| G-E01 | `docs/source-manifest.md` | SHA-256 `98f8412b842a215cf8b17374aadd17be6e9752b9114e6fea2f26d38c0d1f2ee7`; frozen BIP93, Book, CL, and supporting sources |
| G-E02 | `docs/OVERALL-PLAN.md` | SHA-256 `6e1b30c8e86edb74007b54aeb0f0600216eb7fc922aa7ae1e12305753bf95993`; accepted Gates 0–8 plan before Gate 3 revision |
| G-E03 | `src/codex32/bip93.py` | SHA-256 `42cd5260870a4636c5bc23fc640cdd43ee6123cfb9441fb9d93c618af1786d3b`; immutable artifacts and Gate 2 interpolation boundary |
| G-E04 | `src/codex32/checksums.py` | SHA-256 `26ad95779fa8722d4f6c4a7667effc154942730e28885a3ef1dbec2e2261ad99`; existing private CRC implementation |
| G-E05 | `src/codex32/cli.py` | SHA-256 `a880fd2895b436696e530237cf382616804ebd05594cc5ac988c1b8798df6be4`; pre-Gate-3 CLI-owned generation |
| G-E06 | `pyproject.toml` | SHA-256 `c3158d0e99ddc9392558a34da582477fb80a5e0e4588dc20ce72967de99f0d60`; dependency boundary before the `bip32` upper pin |
| G-E07 | [BIP93, Generating Shares](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0093.mediawiki#generating-shares) | Normative fresh- and existing-secret basis construction |
| G-E08 | [Python 3 `random`](https://docs.python.org/3/library/random.html) and [`os.urandom`](https://docs.python.org/3/library/os.html#os.urandom) | `SystemRandom` and operating-system entropy contract |
| G-E09 | CPython `random.py` at [3.12.12](https://github.com/python/cpython/blob/v3.12.12/Lib/random.py), [3.13.12](https://github.com/python/cpython/blob/v3.13.12/Lib/random.py), and [3.14.3](https://github.com/python/cpython/blob/v3.14.3/Lib/random.py) | Reviewed `SystemRandom.getrandbits`, rejection-based `_randbelow`, and ordered `sample` implementation chain |
| G-E10 | [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html), [CRC-3](https://users.ece.cmu.edu/~koopman/crc/crc3.html), and [CRC-4](https://users.ece.cmu.edu/~koopman/crc/crc4.html) | Polynomial catalogue context; not proof of optimality for human transcription damage |
| G-E11 | Gate 3 plan supplied in the implementation request | API, CLI, entropy, identifier, CRC, and audit constraints |

The CPython source tags are evidence for the supported CPython 3.12–3.14
implementations, not a promise about every Python implementation or future
stdlib revision. Operating-system RNG compromise or failure remains outside
the implementation's ability to repair; entropy exceptions must propagate.
