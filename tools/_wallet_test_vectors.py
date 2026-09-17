"""Bitcoin Core-derived public wallet fixtures used by tests and integration checks."""

CORE_FINGERPRINTS = {
    bytes.fromhex("318c6318c6318c6318c6318c6318c631"): bytes.fromhex("3f3521a6"),
    bytes.fromhex("d1808e096b35b209ca12132b264662a5"): bytes.fromhex("fab6868a"),
    bytes.fromhex("ffeeddccbbaa99887766554433221100"): bytes.fromhex("1e50c111"),
}


def core_fingerprint(seed: bytes) -> bytes:
    """Return a frozen fingerprint that the real-Core regtest verifies."""
    try:
        return CORE_FINGERPRINTS[seed]
    except KeyError as error:
        raise AssertionError("missing Bitcoin Core fingerprint fixture") from error


def stub_fingerprint(seed: bytes) -> bytes:
    """Return real fixture data when known, otherwise a stable test-double value."""
    return CORE_FINGERPRINTS.get(seed, b"\x00\x00\x00\x01")
