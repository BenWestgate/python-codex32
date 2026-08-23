"""Small command-line adapter for codex32-native workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import cast

from codex32 import (
    Header,
    MasterSeed,
    Profile,
    Secret,
    Share,
    complete_checksum,
    core_descriptors,
    derive_share,
    generate_master_seed,
    master_xprv,
    multisig_account_xpub,
    parse_codex32,
    recover_secret,
    split_secret,
)
from codex32._bip32 import fingerprint_from_seed
from codex32._cli_input import InputError as _UsageError
from codex32._cli_input import read_artifacts as _artifacts
from codex32._cli_input import read_text as _text
from codex32._cli_parser import parser as _parser
from codex32.correction import (
    _correct_fixed,
    _FixedCorrectionSuccess,
    correct_worksheet_residue,
)
from codex32.errors import CodexError, HeaderCollision, InvalidCorrectionInput
from codex32.profiles import _profile_label

Artifact = Share | Secret


class _CommandError(Exception):
    pass


def _print(text: str, *, err: bool = False) -> None:
    print(text, file=sys.stderr if err else sys.stdout)


def _secret(artifacts: list[Artifact]) -> Secret:
    if len(artifacts) == 1 and isinstance(artifacts[0], Secret):
        return artifacts[0]
    if not all(isinstance(artifact, Share) for artifact in artifacts):
        raise _UsageError("Recovery accepts ordinary shares or one complete secret.")
    try:
        return recover_secret(
            [artifact for artifact in artifacts if isinstance(artifact, Share)]
        )
    except CodexError as error:
        raise _UsageError(str(error)) from error


def _master_seed() -> MasterSeed:
    value = _secret(_artifacts(profiles=(Profile.MS,)))
    if not isinstance(value, MasterSeed):
        raise _UsageError("Wallet commands accept only Bitcoin master-seed secrets.")
    return value


def _render(artifact: Artifact, pretty: bool) -> str:
    if not pretty:
        return artifact.text
    header = artifact.header
    if isinstance(artifact, Share):
        heading = f"Share with index {header.index.upper()}."
    elif header.threshold == 0:
        heading = "Unshared secret."
    else:
        heading = "Shared secret."
    lines = [
        heading,
        f"Type: {_profile_label(artifact.profile)}",
        f"Identifier: {header.identifier.upper()}",
    ]
    if header.threshold:
        lines.append(f"Shares needed for recovery: {header.threshold}")
    if isinstance(artifact, MasterSeed):
        fingerprint = fingerprint_from_seed(artifact.seed_bytes).hex()
        lines.append(f"Master fingerprint: {fingerprint.upper()}")
    upper = artifact.text.upper()
    grouped = " ".join(upper[start : start + 4] for start in range(0, len(upper), 4))
    lines.extend(("", grouped))
    return "\n".join(lines)


def _emit(artifact: Artifact, pretty: bool | None, *, err: bool = False) -> None:
    pretty = (sys.stderr if err else sys.stdout).isatty() if pretty is None else pretty
    _print(_render(artifact, pretty), err=err)


def _check(artifacts: list[Artifact]) -> int:
    blocks: list[str] = []
    for artifact in artifacts:
        header = artifact.header
        if isinstance(artifact, Share):
            heading = f"Valid share with index {header.index.upper()}."
        elif header.threshold == 0:
            heading = "Valid unshared secret."
        else:
            heading = "Valid shared secret."
        lines = [
            heading,
            f"Type: {_profile_label(artifact.profile)}",
            f"Identifier: {header.identifier.upper()}",
        ]
        if header.threshold:
            lines.append(f"Shares needed for recovery: {header.threshold}")
        blocks.append("\n".join(lines))
    _print("\n\n".join(blocks))
    return 0


def _share_command(index: str, pretty: bool | None) -> int:
    artifacts = _artifacts(basis=True, profiles=(Profile.MS, Profile.CL))
    try:
        derived = derive_share(artifacts, index)
    except CodexError as error:
        raise _CommandError(str(error)) from error
    _emit(derived, pretty)
    return 0


def _creation_header(value: str | None) -> tuple[Profile, Header | None]:
    if value is None:
        return Profile.MS, None
    lowered = value.lower()
    if lowered != value and value.upper() != value:
        raise _UsageError("The set header must use either uppercase or lowercase.")
    if "1" in lowered:
        hrp, header = lowered.rsplit("1", 1)
        try:
            profile = Profile(hrp)
        except ValueError as error:
            raise _UsageError("The set header begins with an unknown prefix.") from error
    else:
        profile, header = Profile.MS, lowered
    if len(header) != 5 or header[0] not in "023456789":
        raise _UsageError(
            "The set header must contain a threshold followed by a "
            "four-character identifier."
        )
    try:
        return profile, Header(int(header[0]), header[1:], "s")
    except CodexError as error:
        raise _UsageError(f"Invalid set header: {error}") from error


def _creation_source() -> bytes | Artifact | None:
    prompt = (
        "Press Enter to generate a new seed, or enter an existing codex32 "
        "secret or hexadecimal seed"
    )
    value = _text(prompt, optional=True)
    if not value:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        try:
            return parse_codex32(value)
        except CodexError as error:
            raise _UsageError(str(error)) from error


def _create(
    header: str | None,
    byte_length: int | None,
    shares: int | None,
    indices: str | None,
    pretty: bool | None,
) -> int:
    profile, parsed_header = _creation_header(header)
    if profile is not Profile.MS:
        raise _UsageError("This command creates only Bitcoin master-seed backups.")
    if shares is not None and indices is not None:
        raise _UsageError("Choose either --shares or --indices, not both.")
    source = _creation_source()
    if source is not None and byte_length is not None:
        raise _UsageError("--bytes applies only when generating a new random seed.")
    if isinstance(source, (Share, Secret)) and not isinstance(source, MasterSeed):
        raise _UsageError(
            "Enter one Bitcoin master-seed secret, not a share or another "
            "backup type."
        )
    if isinstance(source, bytes) and parsed_header is None:
        raise _UsageError("A hexadecimal seed requires an explicit set header.")
    if isinstance(source, MasterSeed) and parsed_header is None:
        raise _UsageError("Splitting an existing secret requires a new set header.")

    threshold = 0 if parsed_header is None else parsed_header.threshold
    identifier = None if parsed_header is None else parsed_header.identifier
    if threshold and shares is None and indices is None:
        shares = threshold + 2
    try:
        if isinstance(source, MasterSeed):
            if threshold == 0:
                raise _UsageError(
                    "The supplied secret is already complete; choose a sharing "
                    "threshold from 2 through 9."
                )
            assert identifier is not None
            secret, outputs = split_secret(
                source,
                threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
        else:
            secret, outputs = generate_master_seed(
                source,
                byte_length=byte_length,
                threshold=threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
    except HeaderCollision as error:
        raise _CommandError(f"{error}; choose another set header") from error
    except CodexError as error:
        raise _CommandError(str(error)) from error
    for artifact in (secret,) if threshold == 0 else outputs:
        _emit(artifact, pretty)
    return 0


def _unchecksummed(header: str | None, payload: str) -> str:
    value = (header or "") + payload
    lowered = value.lower()
    if "1" in lowered:
        hrp = lowered.rsplit("1", 1)[0]
        try:
            profile = Profile(hrp)
        except ValueError as error:
            raise _UsageError("The worksheet header has an unknown prefix.") from error
        text = value
    else:
        profile, text = Profile.MS, "ms1" + value
    if profile not in (Profile.MS, Profile.CL):
        raise _UsageError(
            "Checksum completion supports Bitcoin master-seed and Core Lightning "
            "worksheets only."
        )
    body = text[text.rfind("1") + 1 :]
    allowed = (26, 52) if profile is Profile.MS else (52,)
    if len(body) < 6 or len(body) - 6 not in allowed:
        lengths = "a 128- or 256-bit seed" if profile is Profile.MS else "32 bytes"
        raise _UsageError(f"The worksheet must encode {lengths}.")
    return text


def _checksum(header: str | None, pretty: bool | None) -> int:
    text = _unchecksummed(header, _text("Enter the worksheet text before its checksum"))
    warning = (
        "Warning: This command only adds a checksum. Use the Codex32 Book "
        "worksheet to create the preceding characters safely."
    )
    _print(warning, err=True)
    try:
        artifact = complete_checksum(text)
    except CodexError as error:
        raise _CommandError(str(error)) from error
    _emit(artifact, pretty)
    return 0


def _correct(
    residue: bool,
    erasures: tuple[int, ...],
    pretty: bool | None,
) -> int:
    prompt = "Enter the worksheet residue" if residue else "Enter the damaged codex32 string"
    value = _text(prompt)
    if residue:
        try:
            result = correct_worksheet_residue(
                value, erasure_indices=tuple(position - 1 for position in erasures)
            )
        except InvalidCorrectionInput as error:
            raise _UsageError(str(error)) from error
        if result is None:
            raise _CommandError("No unique correction could be found.")
        if not result:
            _print("The worksheet residue is already correct.")
        for correction in result:
            _print(
                f"Add {correction.addend} at position "
                f"{correction.reverse_index + 1}, counting backward from the end."
            )
        return 0
    if erasures:
        raise _UsageError("--erasure can be used only with --residue.")
    lowered = value.lower()
    profile = next(
        (item for item in (Profile.MS, Profile.CL) if lowered.startswith(f"{item}1")),
        None,
    )
    if profile is None:
        bip39_profiles = (Profile.BIP39_12W, Profile.BIP39_24W)
        if any(lowered.startswith(f"{item}1") for item in bip39_profiles):
            raise _UsageError(
                "Full-string correction is not available for BIP39 worksheet backups."
            )
        raise _UsageError(
            "The string must begin with an undamaged ms1 or cl1 prefix; "
            "prefix correction is not attempted."
        )
    fixed = _correct_fixed(value, suspected_profile=profile)
    if not isinstance(fixed, _FixedCorrectionSuccess):
        messages = {
            "algebra": "No correction was found within the checksum's correction limit.",
            "body": "The proposed correction falls outside the supplied string.",
            "reparse": f"The corrected string is not valid for this backup type: {fixed.detail}",
        }
        raise _CommandError(messages.get(fixed.stage, fixed.detail))
    if not fixed.addends:
        _print("The codex32 string is already valid.")
        return 0
    warning = (
        "Warning: This is only a correction suggestion. Compare it with the "
        "original backup before using it."
    )
    _print(warning, err=True)
    _emit(fixed.artifact, pretty, err=True)
    return 1


def _xpub(account: int, testnet: bool) -> int:
    value = multisig_account_xpub(_master_seed(), account=account, testnet=testnet)
    _print(value)
    return 0


def _bitcoin_core(account: int, timestamp: int, testnet: bool, private: bool) -> int:
    secret = _master_seed()
    if private:
        warning = (
            "Warning: The following Bitcoin Core data contains the root private "
            "key and can spend funds. Import it only into the intended encrypted "
            "wallet."
        )
        _print(warning, err=True)
    records = core_descriptors(
        secret,
        account=account,
        testnet=testnet,
        private=private,
        timestamp=timestamp,
    )
    _print(json.dumps(records, separators=(",", ":")))
    return 0


def _dispatch(arguments: argparse.Namespace) -> int:
    command = cast(str, arguments.command)
    pretty = cast(bool | None, getattr(arguments, "pretty", None))
    if command == "check":
        return _check(_artifacts(one=True))
    if command == "secret":
        _emit(_secret(_artifacts()), pretty)
        return 0
    if command == "share":
        return _share_command(cast(str, arguments.index), pretty)
    if command == "create":
        return _create(
            cast(str | None, arguments.header),
            cast(int | None, arguments.byte_length),
            cast(int | None, arguments.shares),
            cast(str | None, arguments.indices),
            pretty,
        )
    if command == "checksum":
        return _checksum(cast(str | None, arguments.header), pretty)
    if command == "correct":
        return _correct(
            bool(arguments.residue),
            tuple(cast(list[int], arguments.erasures)),
            pretty,
        )
    if command == "xprv":
        secret = _master_seed()
        _print(
            "Warning: The following root private key can spend funds from every "
            "wallet derived from this seed. Keep it secret.",
            err=True,
        )
        _print(master_xprv(secret, testnet=bool(arguments.testnet)))
        return 0
    if command == "wallet" and arguments.wallet_command == "multisig-xpub":
        return _xpub(int(arguments.account), bool(arguments.testnet))
    if command == "wallet" and arguments.wallet_command == "bitcoin-core":
        return _bitcoin_core(
            int(arguments.account),
            int(arguments.timestamp),
            bool(arguments.testnet),
            arguments.core_mode == "restore",
        )
    raise AssertionError(f"unhandled command {command!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments_list = sys.argv[1:] if argv is None else argv
    if not arguments_list:
        arguments_list = ("--help",)
    try:
        arguments = parser.parse_args(arguments_list)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    try:
        return _dispatch(arguments)
    except _UsageError as error:
        _print(f"codex32: error: {error}", err=True)
        return 2
    except (_CommandError, CodexError) as error:
        _print(f"codex32: {error}", err=True)
        return 1
    except EOFError:
        _print("codex32: error: input ended before recovery completed", err=True)
        return 2
    except KeyboardInterrupt:
        _print("codex32: interrupted", err=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
