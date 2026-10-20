"""Bitcoin wallet interoperability for validated master seeds."""

from codex32._bip32 import _master_xprv_from_seed
from codex32.profiles.ms32 import MasterSeed


def master_xprv(secret: MasterSeed, *, testnet: bool = False) -> str:
    """Return the root BIP32 extended private key with authority over all children."""
    if not isinstance(secret, MasterSeed):
        raise TypeError("wallet operations accept only MasterSeed")
    return _master_xprv_from_seed(secret.seed_bytes, testnet=testnet)
