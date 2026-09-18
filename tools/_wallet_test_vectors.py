"""Bitcoin Core-derived public wallet fixtures used by tests and integration checks.

Everything here is a BIP32 master fingerprint, which is a wallet property and not a
codex32 one. Some seeds below also appear as BIP93 test vectors, but only as convenient
public seed material: BIP93 assigns those vectors identifiers of its own (``test``,
``name``, ``cash``) that have nothing to do with these fingerprints. An identifier
derived from a fingerprint is therefore never a BIP93-specified value, so assert such
identifiers against ``FIXTURE_SEED`` rather than against vector material.

``tools/bitcoin_core_regtest.py`` verifies every fingerprint below against real Core.
"""

# BIP93 vector seeds, reused here only as wallet fixtures.
_VECTOR_FINGERPRINTS = {
    bytes.fromhex("318c6318c6318c6318c6318c6318c631"): bytes.fromhex("3f3521a6"),
    bytes.fromhex("d1808e096b35b209ca12132b264662a5"): bytes.fromhex("fab6868a"),
    bytes.fromhex("ffeeddccbbaa99887766554433221100"): bytes.fromhex("1e50c111"),
}

# Arbitrary fixtures, one per BIP93 seed length, carrying no test-vector meaning.
_FIXTURE_FINGERPRINTS = {
    bytes.fromhex("107dea57c4319e0b78e552bf2c990673"): bytes.fromhex("8ed1dab8"),
    bytes.fromhex("1481ee5bc835a20f7ce956c3309d0a77e451be2b"): bytes.fromhex("c9a9f9c8"),
    bytes.fromhex("1885f25fcc39a61380ed5ac734a10e7be855c22f9c0976e3"): bytes.fromhex("4dc66f0e"),
    bytes.fromhex("1c89f663d03daa1784f15ecb38a5127fec59c633a00d7ae754c12e9b"): bytes.fromhex("a5f9e972"),
    bytes.fromhex("208dfa67d441ae1b88f562cf3ca91683f05dca37a4117eeb58c5329f0c79e653"): bytes.fromhex(
        "9653e4ec"
    ),
    bytes.fromhex(
        "40ad1a87f461ce3ba81582ef5cc936a3107dea57c4319e0b78e552bf2c990673"
        "e04dba2794016edb48b5228ffc69d643b01d8af764d13eab1885f25fcc39a613"
    ): bytes.fromhex("a9da6294"),
}

CORE_FINGERPRINTS = _VECTOR_FINGERPRINTS | _FIXTURE_FINGERPRINTS

# Arbitrary fixture seed by byte length; excludes vector material by construction.
FIXTURE_SEED = {len(seed): seed for seed in _FIXTURE_FINGERPRINTS}

# Stands in for seeds with no frozen fixture. Deliberately not seed-derived, so a test
# cannot pass on a coincidental seed-to-identifier relationship that real Core would break.
STUB_FINGERPRINT = b"\x00\x00\x00\x01"


def core_fingerprint(seed: bytes) -> bytes:
    """Return a frozen fingerprint that the real-Core regtest verifies."""
    try:
        return CORE_FINGERPRINTS[seed]
    except KeyError as error:
        raise AssertionError("missing Bitcoin Core fingerprint fixture") from error


def stub_fingerprint(seed: bytes) -> bytes:
    """Return real fixture data when known, otherwise a stable test-double value."""
    return CORE_FINGERPRINTS.get(seed, STUB_FINGERPRINT)
