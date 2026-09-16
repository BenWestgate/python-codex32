"""Minimal stdlib-only BIP32 root handling.

This module deliberately stops at root-key validation and xprv serialization.
Public-key derivation belongs to the Bitcoin Core integration boundary.
"""

from __future__ import annotations

import hashlib
import hmac

from codex32.errors import CodexError

_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_MAIN_XPRV_VERSION = bytes.fromhex("0488ade4")
_TEST_XPRV_VERSION = bytes.fromhex("04358394")
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _root_material(seed: bytes) -> tuple[bytes, bytes]:
    if not isinstance(seed, bytes):
        raise TypeError("seed must be bytes")
    digest = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    private_key, chain_code = digest[:32], digest[32:]
    scalar = int.from_bytes(private_key, "big")
    if scalar == 0 or scalar >= _SECP256K1_ORDER:
        raise CodexError("master seed does not form a valid BIP32 root")
    return private_key, chain_code


def _valid_root(seed: bytes) -> bool:
    try:
        _root_material(seed)
    except CodexError:
        return False
    return True


def _base58check(payload: bytes) -> str:
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    encoded = payload + checksum
    value = int.from_bytes(encoded, "big")
    result = ""
    while value:
        value, digit = divmod(value, 58)
        result = _BASE58[digit] + result
    zeros = len(encoded) - len(encoded.lstrip(b"\x00"))
    return "1" * zeros + result


def _master_xprv_from_seed(seed: bytes, *, testnet: bool = False) -> str:
    if not isinstance(testnet, bool):
        raise TypeError("testnet must be bool")
    private_key, chain_code = _root_material(seed)
    version = _TEST_XPRV_VERSION if testnet else _MAIN_XPRV_VERSION
    payload = version + b"\x00" + b"\x00" * 4 + b"\x00" * 4 + chain_code + b"\x00" + private_key
    return _base58check(payload)
