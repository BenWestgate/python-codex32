"""Public error taxonomy for codex32 parsing and safe domain construction."""


class CodexError(Exception):
    """Base class for codex32 errors."""


def _error(name: str, base: type[CodexError], doc: str) -> type[CodexError]:
    """Declare a named empty exception while keeping the hierarchy visible."""
    return type(name, (base,), {"__doc__": doc, "__module__": __name__})


InvalidCharacter = _error("InvalidCharacter", CodexError, "Input contains an invalid character.")
MissingSeparator = _error("MissingSeparator", CodexError, "Input lacks a Bech32 separator.")
InvalidCase = _error("InvalidCase", CodexError, "Input mixes upper- and lowercase characters.")
InvalidLength = _error("InvalidLength", CodexError, "Input length is not permitted by its profile.")
UnknownProfile = _error("UnknownProfile", CodexError, "The HRP is not a registered profile.")
UnsupportedOperation = _error("UnsupportedOperation", CodexError, "The profile omits this operation.")
InvalidChecksum = _error("InvalidChecksum", CodexError, "The outer checksum does not validate.")

InvalidHeader = _error("InvalidHeader", CodexError, "The six-symbol header is invalid.")
InvalidThreshold = _error("InvalidThreshold", InvalidHeader, "The threshold is not 0 or 2 through 9.")
InvalidIdentifier = _error("InvalidIdentifier", InvalidHeader, "The identifier is not four symbols.")
InvalidShareIndex = _error("InvalidShareIndex", InvalidHeader, "The share index conflicts with its header.")

InvalidPayload = _error("InvalidPayload", CodexError, "The payload is not permitted by its profile.")
InvalidPadding = _error("InvalidPadding", InvalidPayload, "The discarded payload padding is invalid.")
InvalidBip39Checksum = _error("InvalidBip39Checksum", InvalidPayload, "The BIP39 checksum is invalid.")

InvalidShareSet = _error("InvalidShareSet", CodexError, "Artifacts cannot form an interpolation set.")
WrongShareCount = _error("WrongShareCount", InvalidShareSet, "The share count differs from its threshold.")
MismatchedProfile = _error("MismatchedProfile", InvalidShareSet, "Profiles differ.")
MismatchedThreshold = _error("MismatchedThreshold", InvalidShareSet, "Thresholds differ.")
MismatchedIdentifier = _error("MismatchedIdentifier", InvalidShareSet, "Identifiers differ.")
MismatchedPayloadLength = _error("MismatchedPayloadLength", InvalidShareSet, "Payload shapes differ.")
DuplicateShareIndex = _error("DuplicateShareIndex", InvalidShareSet, "Share indices repeat.")
SecretInRecoverySet = _error("SecretInRecoverySet", InvalidShareSet, "Recovery received S.")
InvalidTargetIndex = _error("InvalidTargetIndex", InvalidShareSet, "The target is not an ordinary index.")
ExistingTargetIndex = _error("ExistingTargetIndex", InvalidTargetIndex, "The target repeats an input index.")

InvalidShareSelection = _error("InvalidShareSelection", CodexError, "Output share selection is invalid.")
HeaderCollision = _error("HeaderCollision", InvalidShareSelection, "A new set reuses its source header.")
CeremonyStateError = _error("CeremonyStateError", CodexError, "A creation ceremony is out of sequence.")
InvalidCorrectionInput = _error("InvalidCorrectionInput", CodexError, "Correction input is unsupported.")
