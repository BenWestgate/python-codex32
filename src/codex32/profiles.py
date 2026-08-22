"""Fixed codex32 application registry and profile-owned length rules."""

from dataclasses import dataclass
from enum import StrEnum

from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
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
    linear_sharing_enabled: bool

    def checksum_for_data_length(self, data_length: int) -> _Checksum:
        """Select solely from the unchecksummed data-part length."""
        payload_length = data_length - 6
        if payload_length not in self.payload_lengths:
            expected = f"{min(self.payload_lengths)}..{max(self.payload_lengths)}"
            if len(self.payload_lengths) == 1:
                expected = str(self.payload_lengths[0])
            raise InvalidLength(
                f"{self.profile} payload has {payload_length} symbols; expected {expected}"
            )
        if self.profile is Profile.MS and data_length > 80:
            return _CODEX32_LONG
        return _CODEX32

    def checksum_for_encoded_length(self, encoded_data_length: int) -> _Checksum:
        """Determine the unique checksum from total data symbols."""
        matches = []
        for checksum in (_CODEX32, _CODEX32_LONG):
            data_length = encoded_data_length - checksum.length
            try:
                selected = self.checksum_for_data_length(data_length)
            except InvalidLength:
                continue
            if selected is checksum:
                matches.append(checksum)
        if len(matches) != 1:
            raise InvalidLength(
                f"encoded {self.profile} data has no permitted payload/checksum length"
            )
        return matches[0]

    def require_completion(self) -> None:
        if not self.completion_enabled:
            raise UnsupportedOperation(
                f"checksum completion is not available for {self.profile}"
            )

    def require_linear_sharing(self) -> None:
        """Reject profiles whose checksum/payload is not approved for sharing."""
        if not self.linear_sharing_enabled:
            raise UnsupportedOperation(
                f"linear sharing is not available for {self.profile}"
            )


_MS_PAYLOAD_LENGTHS = tuple(sorted({(byte_length * 8 + 4) // 5 for byte_length in range(16, 65)}))

_SPECS = {
    Profile.MS: _ProfileSpec(Profile.MS, _MS_PAYLOAD_LENGTHS, True, True),
    Profile.CL: _ProfileSpec(Profile.CL, (52,), True, True),
    Profile.BIP39_12W: _ProfileSpec(Profile.BIP39_12W, (27,), False, True),
    Profile.BIP39_24W: _ProfileSpec(Profile.BIP39_24W, (53,), False, True),
}


def _profile_spec(hrp: str | Profile) -> _ProfileSpec:
    try:
        profile = hrp if isinstance(hrp, Profile) else Profile(hrp.lower())
    except (ValueError, AttributeError) as error:
        raise UnknownProfile(f"unknown codex32 HRP {hrp!r}") from error
    return _SPECS[profile]
