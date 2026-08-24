"""Fixed application profiles layered over validated codex32 strings."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Never

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
    text_lengths: range | tuple[int, ...]

    def validate_text_length(self, text_length: int) -> None:
        if text_length in self.text_lengths:
            return
        name = _profile_label(self.profile).replace("master seed", "master-seed")
        if self.profile is Profile.MS:
            rule = "needs at least 48" if text_length < 48 else "can have at most 127"
        else:
            rule = f"must have exactly {self.text_lengths[0]}"
        raise InvalidLength(f"This input has {text_length} characters. A {name} backup {rule}.")

    def _raise_length(self, too_short: bool | None = None) -> Never:
        name = _profile_label(self.profile).replace("master seed", "master-seed")
        if self.profile is Profile.MS:
            assert too_short is not None
            boundary = "48 characters or more" if too_short else "127 characters or fewer"
            raise InvalidLength(
                f"This input is too {'short' if too_short else 'long'} for a "
                f"{name} backup; expected {boundary}."
            )
        expected = self.text_lengths[0]
        article = "an" if expected == 82 else "a"
        raise InvalidLength(
            f"This input has the wrong length for a {name} backup; "
            f"expected {article} {expected}-character codex32 string."
        )

    def validate_payload_length(self, payload_length: int) -> None:
        if payload_length in self.payload_lengths:
            return
        if self.profile is Profile.MS:
            if self.payload_lengths[0] < payload_length < self.payload_lengths[-1]:
                raise InvalidLength("This input does not encode a whole number of Bitcoin master-seed bytes.")
            self._raise_length(payload_length < self.payload_lengths[0])
        self._raise_length()

    def require_completion(self) -> None:
        if not self.completion_enabled:
            raise UnsupportedOperation(f"checksum completion is not available for {self.profile}")


_MS_PAYLOAD_LENGTHS = tuple(sorted({(byte_length * 8 + 4) // 5 for byte_length in range(16, 65)}))

_SPECS = {
    Profile.MS: _ProfileSpec(Profile.MS, _MS_PAYLOAD_LENGTHS, True, range(48, 128)),
    Profile.CL: _ProfileSpec(Profile.CL, (52,), True, (74,)),
    Profile.BIP39_12W: _ProfileSpec(Profile.BIP39_12W, (27,), False, (56,)),
    Profile.BIP39_24W: _ProfileSpec(Profile.BIP39_24W, (53,), False, (82,)),
}


def _profile_spec(hrp: str | Profile) -> _ProfileSpec:
    try:
        profile = hrp if isinstance(hrp, Profile) else Profile(hrp.lower())
    except (ValueError, AttributeError) as error:
        raise UnknownProfile(f"The application prefix {hrp!r} is not supported.") from error
    return _SPECS[profile]


def _profile_label(profile: Profile) -> str:
    return {
        Profile.MS: "Bitcoin master seed",
        Profile.CL: "Core Lightning HSM secret",
        Profile.BIP39_12W: "12-word BIP39 worksheet",
        Profile.BIP39_24W: "24-word BIP39 worksheet",
    }[profile]
