"""Public error taxonomy for codex32 parsing and safe domain construction."""


class CodexError(Exception):
    """Base class for codex32 errors."""


class InvalidCharacter(CodexError):
    """Input contains a character that is invalid in its context."""


class MissingSeparator(CodexError):
    """Input does not contain a Bech32 separator."""


class InvalidCase(CodexError):
    """Input mixes upper- and lowercase characters."""


class InvalidLength(CodexError):
    """Input has a length not permitted by its registered profile."""


class UnknownProfile(CodexError):
    """The HRP is not one of the fixed registered codex32 profiles."""


class UnsupportedOperation(CodexError):
    """A registered profile deliberately does not provide this operation."""


class InvalidChecksum(CodexError):
    """The outer codex32 checksum does not validate."""


class InvalidHeader(CodexError):
    """The six-symbol codex32 header is invalid."""


class InvalidThreshold(InvalidHeader):
    """The threshold is not 0 or in the inclusive range 2 through 9."""


class InvalidIdentifier(InvalidHeader):
    """The identifier is not exactly four Bech32 symbols."""


class InvalidShareIndex(InvalidHeader):
    """The share index is inconsistent with the header."""


class InvalidPayload(CodexError):
    """The payload cannot represent data permitted by its profile."""


class InvalidPadding(InvalidPayload):
    """The otherwise-discarded payload padding is not permitted."""


class InvalidBip39Checksum(InvalidPayload):
    """A BIP39 migration secret has an invalid embedded checksum."""


class InvalidShareSet(CodexError):
    """A set of validated artifacts cannot be used for interpolation."""


class WrongShareCount(InvalidShareSet):
    """A share set does not contain exactly its declared threshold."""


class MismatchedProfile(InvalidShareSet):
    """Interpolation inputs belong to different registered profiles."""


class MismatchedThreshold(InvalidShareSet):
    """Interpolation inputs do not have one valid common threshold."""


class MismatchedIdentifier(InvalidShareSet):
    """Interpolation inputs do not have one common identifier."""


class MismatchedPayloadLength(InvalidShareSet):
    """Interpolation inputs do not have one common encoded payload shape."""


class DuplicateShareIndex(InvalidShareSet):
    """Interpolation inputs repeat an index."""


class SecretInRecoverySet(InvalidShareSet):
    """Recovery was given S rather than only ordinary shares."""


class InvalidTargetIndex(InvalidShareSet):
    """A derivation target is not an ordinary share index."""


class ExistingTargetIndex(InvalidTargetIndex):
    """A derivation target repeats an interpolation input index."""


class InvalidShareSelection(CodexError):
    """Generation output indices or their requested count are invalid."""


class HeaderCollision(InvalidShareSelection):
    """A new share set reuses its source set header."""


class InvalidCorrectionInput(CodexError):
    """Correction input cannot describe a supported checksum problem."""
