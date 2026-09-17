"""Test-only Core descriptor oracle backed by the independent bip32 package.

Never use this adapter with real wallet material. Runtime code delegates public
derivation to Bitcoin Core; this oracle keeps offline vectors reproducible.
"""

import re
from typing import Literal

from bip32 import BIP32

from codex32._bitcoin_core import BitcoinCore
from codex32.profiles.ms32 import MasterSeed
from codex32.wallet import _with_checksum, core_descriptors


def fingerprint_seed(seed: bytes) -> bytes:
    return BIP32.from_seed(seed).get_fingerprint()


def descriptor_info(descriptor: str) -> dict[str, object]:
    descriptor = descriptor.strip().split("#", 1)[0]

    def public(match: re.Match[str]) -> str:
        root = BIP32.from_xpriv(match.group(1))
        path = match.group(2)
        return f"[{root.get_fingerprint().hex()}{path}]{root.get_xpub_from_path('m' + path)}"

    normalized = re.sub(r"([xt]prv[1-9A-HJ-NP-Za-km-z]+)((?:/\d+h)*)", public, descriptor)
    return {
        "descriptor": _with_checksum(normalized),
        "multipath_expansion": [
            _with_checksum(normalized.replace("<0;1>", str(branch))) for branch in (0, 1)
        ],
    }


class ReferenceCore(BitcoinCore):
    def __init__(self, *, testnet: bool = False) -> None:
        super().__init__("test-only", "test" if testnet else "main", 320000)

    def fingerprint(self, secret: MasterSeed) -> bytes:
        return fingerprint_seed(secret.seed_bytes)

    def public_descriptors(
        self,
        secret: MasterSeed,
        *,
        wallet: str,
        account: int = 0,
        timestamp: int | Literal["now"] = 0,
    ) -> tuple[dict[str, object], ...]:
        del wallet
        private = core_descriptors(
            secret,
            account=account,
            testnet=self.chain != "main",
            private=True,
            timestamp=timestamp,
        )
        return tuple(
            {
                "desc": descriptor_info(str(record["desc"]))["descriptor"],
                "active": True,
                "timestamp": timestamp,
            }
            for record in private
        )

    def _rpc(self, *arguments: str, wallet: str | None = None, stdin: str | None = None) -> object:
        assert arguments == ("getdescriptorinfo",) and wallet is None and stdin is not None
        return descriptor_info(stdin)
