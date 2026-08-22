"""Typed boundary around the untyped ``bip32`` dependency."""

from typing import Protocol, Self, cast

from bip32 import BIP32, InvalidInputError  # type: ignore[import-untyped]

from codex32.errors import CodexError


class _Backend(Protocol):
    def get_fingerprint(self) -> bytes: ...

    def get_xpriv(self) -> str: ...

    def get_xpub_from_path(self, path: str) -> str: ...


class Bip32Node:
    """Only the BIP32 operations used by codex32."""

    __slots__ = ("_backend",)

    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    @classmethod
    def from_seed(cls, seed: bytes, *, testnet: bool = False) -> Self:
        try:
            backend = cast(
                _Backend,
                BIP32.from_seed(seed, "test" if testnet else "main"),
            )
        except InvalidInputError as error:
            raise CodexError("master seed does not form a valid BIP32 root") from error
        return cls(backend)

    def fingerprint(self) -> bytes:
        return self._backend.get_fingerprint()

    def xpriv(self) -> str:
        return self._backend.get_xpriv()

    def xpub_from_path(self, path: str) -> str:
        return self._backend.get_xpub_from_path(path)


def fingerprint_from_seed(seed: bytes) -> bytes:
    """Return the four-byte BIP32 master fingerprint."""
    return Bip32Node.from_seed(seed).fingerprint()
