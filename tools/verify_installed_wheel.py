"""Smoke-test backup/recovery and root-wallet primitives from an installed wheel."""

from __future__ import annotations

import importlib.util
import sys

from codex32 import (
    CorrectionContext,
    CreationCeremony,
    MasterSeed,
    Profile,
    core_descriptors,
    correct,
    derive_share,
    master_xprv,
    parse_codex32,
    recover_secret,
)

_SECRET = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"
_XPRV = (
    "xprv9s21ZrQH143K3taPNekMd9oV5K6szJ8ND7vVh6fxicRUMDcChr3bFFzuxY8qP3"
    "xFFBL6DWc2uEYCfBFZ2nFWbAqKPhtCLRjgv78EZJDEfpL"
)


def main() -> None:
    assert importlib.util.find_spec("bip32") is None
    assert importlib.util.find_spec("coincurve") is None

    ceremony = CreationCeremony.master_seed(threshold=2, indices="ac", identifier="test")
    shares = []
    for _ in range(2):
        share = ceremony.next_share()
        assert ceremony.confirm(share.text).accepted
        shares.append(share)
    generated = ceremony.finish()
    assert parse_codex32(generated.text) == generated
    assert recover_secret(shares) == generated
    assert derive_share(shares, "d").header.index == "d"
    damaged = shares[0].text[:-1] + "?"
    assert correct(CorrectionContext(Profile.MS), damaged)

    secret = parse_codex32(_SECRET)
    assert isinstance(secret, MasterSeed)
    assert master_xprv(secret) == _XPRV
    private = core_descriptors(secret, private=True)
    assert len(private) == 4
    assert all("xprv" in record["desc"] for record in private)
    assert "bip32" not in sys.modules
    assert "coincurve" not in sys.modules


if __name__ == "__main__":
    main()
