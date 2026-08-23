"""Fixed application profiles layered over validated codex32 strings."""

from dataclasses import dataclass
from enum import StrEnum

from codex32.errors import InvalidLength, UnknownProfile, UnsupportedOperation


class Profile(StrEnum):
    """Registered codex32 application profiles supported by this package."""

    MS = "ms"
    CL = "cl"
    BIP39_12W = "bip39_12w"
    BIP39_24W = "bip39_24w"


@dataclass(frozen=True, slots=True)
class _ProfileSpec:
    profile: Profile
    payload_lengths: tuple[int, ...]
    completion_enabled: bool

    def validate_payload_length(self, payload_length: int) -> None:
        """Apply only this application's exact payload-length rule."""
        if payload_length in self.payload_lengths:
            return
        if self.profile is Profile.MS:
            if payload_length < self.payload_lengths[0]:
                message = (
                    "This input is too short for a Bitcoin master-seed backup; "
                    "expected 48 characters or more."
                )
            elif payload_length > self.payload_lengths[-1]:
                message = (
                    "This input is too long for a Bitcoin master-seed backup; "
                    "expected 127 characters or fewer."
                )
            else:
                message = (
                    "This input does not encode a whole number of Bitcoin "
                    "master-seed bytes."
                )
        elif self.profile is Profile.CL:
            message = (
                "This input has the wrong length for a Core Lightning HSM-secret "
                "backup; expected a 74-character codex32 string."
            )
        elif self.profile is Profile.BIP39_12W:
            message = (
                "This input has the wrong length for a 12-word BIP39 worksheet "
                "backup; expected a 56-character codex32 string."
            )
        else:
            message = (
                "This input has the wrong length for a 24-word BIP39 worksheet "
                "backup; expected an 82-character codex32 string."
            )
        raise InvalidLength(message)

    def require_completion(self) -> None:
        if not self.completion_enabled:
            raise UnsupportedOperation(
                f"checksum completion is not available for {self.profile}"
            )


_MS_PAYLOAD_LENGTHS = tuple(
    sorted({(byte_length * 8 + 4) // 5 for byte_length in range(16, 65)})
)

_SPECS = {
    Profile.MS: _ProfileSpec(Profile.MS, _MS_PAYLOAD_LENGTHS, True),
    Profile.CL: _ProfileSpec(Profile.CL, (52,), True),
    Profile.BIP39_12W: _ProfileSpec(Profile.BIP39_12W, (27,), False),
    Profile.BIP39_24W: _ProfileSpec(Profile.BIP39_24W, (53,), False),
}


def _profile_spec(hrp: str | Profile) -> _ProfileSpec:
    try:
        profile = hrp if isinstance(hrp, Profile) else Profile(hrp.lower())
    except (ValueError, AttributeError) as error:
        raise UnknownProfile(f"unknown codex32 HRP {hrp!r}") from error
    return _SPECS[profile]


def _profile_label(profile: Profile) -> str:
    return {
        Profile.MS: "Bitcoin master seed",
        Profile.CL: "Core Lightning HSM secret",
        Profile.BIP39_12W: "12-word BIP39 worksheet",
        Profile.BIP39_24W: "24-word BIP39 worksheet",
    }[profile]
