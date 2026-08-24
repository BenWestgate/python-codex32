"""Smoke-test BIP32 and wallet vectors using an installed wheel only."""

from __future__ import annotations

from codex32 import (
    MasterSeed,
    core_descriptors,
    master_xprv,
    multisig_account_xpub,
    parse_codex32,
)

_SECRET = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"
_XPRV = (
    "xprv9s21ZrQH143K3taPNekMd9oV5K6szJ8ND7vVh6fxicRUMDcChr3bFFzuxY8qP3"
    "xFFBL6DWc2uEYCfBFZ2nFWbAqKPhtCLRjgv78EZJDEfpL"
)


def main() -> None:
    secret = parse_codex32(_SECRET)
    assert isinstance(secret, MasterSeed)
    assert master_xprv(secret) == _XPRV
    assert multisig_account_xpub(secret).startswith("[3f3521a6/48h/0h/0h/2h]xpub")
    public = core_descriptors(secret, private=False)
    private = core_descriptors(secret, private=True)
    assert len(public) == len(private) == 4
    assert all("xprv" not in record["desc"] for record in public)
    assert all("xprv" in record["desc"] for record in private)


if __name__ == "__main__":
    main()
