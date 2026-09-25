"""Bitcoin Core-derived public wallet fixtures used by tests and integration checks.

Everything in ``tests/data/wallet_fingerprints.json`` is a BIP32 master fingerprint,
which is a wallet property and not a codex32 one. Some seeds there also appear as
BIP93 test vectors, but only as convenient public seed material: BIP93 assigns those
vectors identifiers of its own (``test``, ``name``, ``cash``) that have nothing to do
with these fingerprints. An identifier derived from a fingerprint is therefore never
a BIP93-specified value, so assert such identifiers against ``FIXTURE_SEED`` rather
than against vector material.

``tools/bitcoin_core_regtest.py`` verifies every frozen fingerprint against real Core.
"""

import hashlib
import json
from pathlib import Path

_DATA = json.loads(
    (Path(__file__).resolve().parents[1] / "tests" / "data" / "wallet_fingerprints.json").read_text()
)


def _fingerprints(group: str) -> dict[bytes, bytes]:
    return {bytes.fromhex(seed): bytes.fromhex(fingerprint) for seed, fingerprint in _DATA[group].items()}


# BIP93 vector seeds, reused here only as wallet fixtures.
_VECTOR_FINGERPRINTS = _fingerprints("bip93_vector_seeds")

# Arbitrary fixtures, one per BIP93 seed length, carrying no test-vector meaning.
_FIXTURE_FINGERPRINTS = _fingerprints("fixture_seeds")

CORE_FINGERPRINTS = _VECTOR_FINGERPRINTS | _FIXTURE_FINGERPRINTS

# Arbitrary fixture seed by byte length; excludes vector material by construction.
FIXTURE_SEED = {len(seed): seed for seed in _FIXTURE_FINGERPRINTS}

# Stands in where the fingerprint value itself is irrelevant to the test.
STUB_FINGERPRINT = b"\x00\x00\x00\x01"


def core_fingerprint(seed: bytes) -> bytes:
    """Return a frozen fingerprint that the real-Core regtest verifies."""
    try:
        return CORE_FINGERPRINTS[seed]
    except KeyError as error:
        raise AssertionError("missing Bitcoin Core fingerprint fixture") from error


def stub_fingerprint(seed: bytes) -> bytes:
    """Return real fixture data when known, otherwise a seed-sensitive test double."""
    fixture = CORE_FINGERPRINTS.get(seed)
    if fixture is not None:
        return fixture
    return hashlib.sha256(b"codex32 test fingerprint\0" + seed).digest()[:4]
