# Copyright (c) 2026 Ben Westgate <benwestgate@protonmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Safe, profile-aware codex32 artifacts and correction helpers."""

from .bip93 import (
    Bip39Secret,
    CoreLightningSecret,
    Header,
    MasterSeed,
    Secret,
    Share,
    complete_checksum,
    derive_share,
    parse_codex32,
    recover_secret,
)
from .correction import (
    WorksheetCorrection,
    correct_worksheet_residue,
)
from .errors import (
    CodexError,
    DuplicateShareIndex,
    ExcludedTargetIndex,
    ExistingTargetIndex,
    HeaderCollision,
    InvalidBip39Checksum,
    InvalidCase,
    InvalidCharacter,
    InvalidChecksum,
    InvalidCorrectionInput,
    InvalidHeader,
    InvalidIdentifier,
    InvalidLength,
    InvalidPadding,
    InvalidPayload,
    InvalidShareIndex,
    InvalidShareSelection,
    InvalidShareSet,
    InvalidTargetIndex,
    InvalidThreshold,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    MissingSeparator,
    SecretInRecoverySet,
    UnknownProfile,
    UnsupportedOperation,
    WrongShareCount,
)
from .generation import (
    generate_core_lightning_secret,
    generate_master_seed,
    split_secret,
)
from .profiles import Profile

__all__ = [
    "Bip39Secret",
    "CodexError",
    "CoreLightningSecret",
    "DuplicateShareIndex",
    "ExcludedTargetIndex",
    "ExistingTargetIndex",
    "Header",
    "HeaderCollision",
    "InvalidBip39Checksum",
    "InvalidCase",
    "InvalidCharacter",
    "InvalidChecksum",
    "InvalidCorrectionInput",
    "InvalidHeader",
    "InvalidIdentifier",
    "InvalidLength",
    "InvalidPadding",
    "InvalidPayload",
    "InvalidShareIndex",
    "InvalidShareSelection",
    "InvalidShareSet",
    "InvalidTargetIndex",
    "InvalidThreshold",
    "MasterSeed",
    "MismatchedIdentifier",
    "MismatchedPayloadLength",
    "MismatchedProfile",
    "MismatchedThreshold",
    "MissingSeparator",
    "Profile",
    "Secret",
    "SecretInRecoverySet",
    "Share",
    "UnknownProfile",
    "UnsupportedOperation",
    "WorksheetCorrection",
    "WrongShareCount",
    "complete_checksum",
    "correct_worksheet_residue",
    "derive_share",
    "generate_core_lightning_secret",
    "generate_master_seed",
    "parse_codex32",
    "recover_secret",
    "split_secret",
]
