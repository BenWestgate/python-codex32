"""Emit a deterministic digest of the wallet interoperability boundary."""

from __future__ import annotations

import argparse
import hashlib
import json

from _wallet_reference import ReferenceCore

from codex32 import MasterSeed, core_descriptors, master_xprv

_DOMAIN = b"python-codex32 differential wallet corpus v2"
_SEED_LENGTHS = (16, 20, 24, 28, 32, 64)
_EXPECTED_CASES = 64
_EXPECTED_DIGEST = "9b3342af401765e4ec73acb3d17142060c1844fc70fda4d87e77f1191f6aec40"


def _seed(case: int, length: int) -> bytes:
    material = _DOMAIN + case.to_bytes(4, "big") + bytes([length])
    return hashlib.sha512(material).digest()[:length]


def _record(case: int, length: int, testnet: bool) -> dict[str, object]:
    seed = _seed(case, length)
    account = int.from_bytes(hashlib.sha256(seed).digest()[:4], "big") % 2**31
    secret = MasterSeed.from_seed(seed, identifier="test")
    core = ReferenceCore(testnet=testnet)
    return {
        "case": case,
        "length": length,
        "testnet": testnet,
        "account": account,
        "xprv": master_xprv(secret, testnet=testnet),
        "public": core_descriptors(
            secret,
            integration=core,
            wallet="test-only",
            account=account,
            testnet=testnet,
            timestamp=case,
        ),
        "private": core_descriptors(
            secret,
            account=account,
            testnet=testnet,
            private=True,
            timestamp=case,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=_EXPECTED_CASES)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    if arguments.cases < 1:
        raise SystemExit("--cases must be positive")

    digest = hashlib.sha256()
    records = 0
    for case in range(arguments.cases):
        for length in _SEED_LENGTHS:
            for testnet in (False, True):
                encoded = json.dumps(
                    _record(case, length, testnet),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                digest.update(len(encoded).to_bytes(4, "big"))
                digest.update(encoded)
                records += 1

    actual = digest.hexdigest()
    print(json.dumps({"records": records, "sha256": actual}))
    if arguments.verify:
        if arguments.cases != _EXPECTED_CASES:
            raise SystemExit(f"--verify requires --cases {_EXPECTED_CASES}")
        if not _EXPECTED_DIGEST or actual != _EXPECTED_DIGEST:
            raise SystemExit("wallet differential digest mismatch")


if __name__ == "__main__":
    main()
