"""Fixed selection of the supported codex32 application profiles."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from codex32.errors import UnknownProfile

if TYPE_CHECKING:
    from codex32.profiles.bip39 import _Bip39Rules
    from codex32.profiles.cl32 import _Cl32Rules
    from codex32.profiles.ms32 import _Ms32Rules
type _ProfileRules = _Ms32Rules | _Cl32Rules | _Bip39Rules


class Profile(StrEnum):
    MS = "ms"
    CL = "cl"
    BIP39_12W = "bip39_12w"
    BIP39_24W = "bip39_24w"


def _profile_rules(hrp: str | Profile) -> _ProfileRules:
    try:
        profile = hrp if isinstance(hrp, Profile) else Profile(hrp.lower())
    except (ValueError, AttributeError) as error:
        raise UnknownProfile(f"The application prefix {hrp!r} is not supported.") from error
    if profile is Profile.MS:
        from codex32.profiles.ms32 import RULES as ms32_rules

        return ms32_rules
    elif profile is Profile.CL:
        from codex32.profiles.cl32 import RULES as cl32_rules

        return cl32_rules
    from codex32.profiles.bip39 import BIP39_12W_RULES, BIP39_24W_RULES

    return BIP39_12W_RULES if profile is Profile.BIP39_12W else BIP39_24W_RULES
