"""Small command-line adapter for codex32-native workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from importlib.metadata import version
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
        raise _UsageError("stdin: recovery accepts ordinary shares only")
    try:
        return recover_secret(
            [artifact for artifact in artifacts if isinstance(artifact, Share)]
        )
    except CodexError as error:
        raise _UsageError(f"stdin: {error}") from error


def _master_seed() -> MasterSeed:
    value = _secret(_artifacts(profiles=(Profile.MS,)))
    if not isinstance(value, MasterSeed):
        raise _UsageError("wallet commands accept only ms secrets")
    return value


def _render(artifact: Artifact, pretty: bool) -> str:
    if not pretty:
        return artifact.text
    header = artifact.header
    lines = [
        f"Profile: {artifact.profile.value}",
        f"Threshold: {header.threshold}",
        f"Identifier: {header.identifier.upper()}",
        f"Index: {header.index.upper()}",
    ]
    if isinstance(artifact, MasterSeed):
        fingerprint = fingerprint_from_seed(artifact.seed_bytes).hex()
        lines.append(f"Master fingerprint: {fingerprint.upper()}")
    upper = artifact.text.upper()
    grouped = " ".join(upper[start : start + 4] for start in range(0, len(upper), 4))
    lines.extend(("", grouped))
    return "\n".join(lines)


def _emit(artifact: Artifact, pretty: bool, *, err: bool = False) -> None:
    _print(_render(artifact, pretty), err=err)


def _check(artifacts: list[Artifact]) -> int:
    blocks: list[str] = []
    for artifact in artifacts:
        header = artifact.header
        threshold = "0 (unshared)" if header.threshold == 0 else str(header.threshold)
        lines = [
            f"Valid codex32 {'secret' if isinstance(artifact, Secret) else 'share'}.",
            f"Application: {_profile_label(artifact.profile)}",
            f"Threshold: {threshold}",
            f"Identifier: {header.identifier.upper()}",
        ]
        if isinstance(artifact, Share):
            lines.append(f"Share index: {header.index.upper()}")
        blocks.append("\n".join(lines))
    _print("\n\n".join(blocks))
    return 0


def _share_command(index: str, pretty: bool) -> int:
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
        raise _UsageError("HEADER must use one case")
    if "1" in lowered:
        hrp, header = lowered.rsplit("1", 1)
        try:
            profile = Profile(hrp)
        except ValueError as error:
            raise _UsageError("HEADER has an unknown prefix") from error
    else:
        profile, header = Profile.MS, lowered
    if len(header) != 5 or header[0] not in "023456789":
        raise _UsageError("HEADER must be threshold plus four identifier symbols")
    try:
        return profile, Header(int(header[0]), header[1:], "s")
    except CodexError as error:
        raise _UsageError(f"HEADER: {error}") from error


def _creation_source() -> bytes | Artifact | None:
    value = _text("raw hexadecimal seed or existing S", optional=True)
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
    pretty: bool,
) -> int:
    profile, parsed_header = _creation_header(header)
    if profile is not Profile.MS:
        message = "fresh cl and BIP39 secrets are not generated by this reference CLI"
        raise _UsageError(message)
    if shares is not None and indices is not None:
        raise _UsageError("--shares and --indices are mutually exclusive")
    source = _creation_source()
    if source is not None and byte_length is not None:
        raise _UsageError("--bytes applies only to fresh generation")
    if isinstance(source, (Share, Secret)) and not isinstance(source, MasterSeed):
        raise _UsageError("create accepts only raw bytes or one ms secret S")
    if isinstance(source, bytes) and parsed_header is None:
        raise _UsageError("raw seeds require an explicit HEADER")
    if isinstance(source, MasterSeed) and parsed_header is None:
        raise _UsageError("re-sharing requires a new explicit HEADER")

    threshold = 0 if parsed_header is None else parsed_header.threshold
    identifier = None if parsed_header is None else parsed_header.identifier
    if threshold and shares is None and indices is None:
        shares = max(5, threshold)
    try:
        if isinstance(source, MasterSeed):
            if threshold == 0:
                raise _UsageError("an existing secret is already complete")
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
        raise _CommandError(f"{error}; choose another HEADER") from error
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
            raise _UsageError("HEADER has an unknown prefix") from error
        text = value
    else:
        profile, text = Profile.MS, "ms1" + value
    if profile not in (Profile.MS, Profile.CL):
        raise _UsageError("checksum completion is limited to ms and cl")
    body = text[text.rfind("1") + 1 :]
    allowed = (26, 52) if profile is Profile.MS else (52,)
    if len(body) < 6 or len(body) - 6 not in allowed:
        lengths = "128 or 256 bits" if profile is Profile.MS else "32 bytes"
        raise _UsageError(f"{profile.value} checksum input must encode {lengths}")
    return text


def _checksum(header: str | None, pretty: bool) -> int:
    text = _unchecksummed(header, _text("worksheet payload"))
    _print("DANGER: checksum completion does not create entropy.", err=True)
    try:
        artifact = complete_checksum(text)
    except CodexError as error:
        raise _CommandError(str(error)) from error
    _emit(artifact, pretty)
    return 0


def _correct(
    residue: bool,
    erasures: tuple[int, ...],
    prefix: str,
    pretty: bool,
) -> int:
    value = _text("damaged string or residue")
    if residue:
        try:
            result = correct_worksheet_residue(
                value, erasure_indices=tuple(position - 1 for position in erasures)
            )
        except InvalidCorrectionInput as error:
            raise _UsageError(str(error)) from error
        if result is None:
            raise _CommandError("unable to determine a unique correction")
        if not result:
            _print("No errors found. Residue is correct.")
        for correction in result:
            _print(
                f"Add {correction.addend} to reverse position "
                f"{correction.reverse_index + 1}."
            )
        return 0
    if erasures:
        raise _UsageError("--erasure requires --residue")
    fixed = _correct_fixed(value, suspected_profile=Profile(prefix))
    if not isinstance(fixed, _FixedCorrectionSuccess):
        raise _CommandError(fixed.detail)
    if not fixed.addends:
        _print("No errors found. String is valid.")
        return 0
    warning = (
        "Warning: checksum-valid correction suggestion; verify against the backup."
    )
    _print(warning, err=True)
    _emit(fixed.artifact, pretty, err=True)
    return 1


def _xpub(account: int, testnet: bool) -> int:
    value = multisig_account_xpub(_master_seed(), account=account, testnet=testnet)
    _print(value)
    return 0


def _bitcoin_core(account: int, timestamp: int, testnet: bool, private: bool) -> int:
    if private:
        warning = (
            "Warning: private descriptors contain the root xprv and grant "
            "root authority."
        )
        _print(warning, err=True)
    records = core_descriptors(
        _master_seed(),
        account=account,
        testnet=testnet,
        private=private,
        timestamp=timestamp,
    )
    _print(json.dumps(records, separators=(",", ":")))
    return 0


def _integer(
    label: str, minimum: int, maximum: int | None = None
) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
        if parsed < minimum or (maximum is not None and parsed > maximum):
            bound = f" through {maximum}" if maximum is not None else " or greater"
            raise argparse.ArgumentTypeError(f"{label} must be {minimum}{bound}")
        return parsed

    return parse


def _command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    return subparsers.add_parser(
        name, help=help_text, description=help_text, allow_abbrev=False
    )


def _wallet_options(parser: argparse.ArgumentParser, *, timestamp: bool) -> None:
    parser.add_argument("--account", type=_integer("account", 0, 2**31 - 1), default=0)
    if timestamp:
        parser.add_argument("--timestamp", type=_integer("timestamp", 0), default=0)
    parser.add_argument("--testnet", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex32",
        description="Create, check, recover, and use codex32 Bitcoin seed backups.",
        epilog=(
            "Never type or paste a seed or share into the command itself.\n"
            "Enter it when prompted or provide it through stdin."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('codex32')}",
        help="Show the installed version and exit.",
    )
    commands = parser.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    check = _command(commands, "check", "Check whether a backup or share is valid.")
    check.description = (
        "Checks format, checksum, and application rules; it does not authenticate the intended wallet."
    )

    secret = _command(commands, "secret", "Recover the secret from enough shares.")
    secret.add_argument("--pretty", action="store_true", help="group for writing")

    share = _command(commands, "share", "Derive an additional share.")
    share.add_argument("index", help="fresh ordinary share index")
    share.add_argument("--pretty", action="store_true", help="group for writing")

    correct = _command(commands, "correct", "Suggest repairs for damaged backup text.")
    correct.add_argument("--residue", action="store_true")
    correct.add_argument(
        "--erasure",
        dest="erasures",
        action="append",
        default=[],
        type=_integer("erasure", 1),
    )
    correct.add_argument(
        "--prefix",
        choices=("ms", "cl"),
        default="ms",
        type=str.lower,
    )
    correct.add_argument("--pretty", action="store_true", help="group for writing")

    checksum = _command(
        commands, "checksum", "Finish a Codex32 Book checksum worksheet."
    )
    checksum.add_argument("header", nargs="?", help="optional prefixed header")
    checksum.add_argument("--pretty", action="store_true", help="group for writing")

    create = _command(commands, "create", "Create a backup or split one into shares.")
    create.add_argument("header", nargs="?", help="threshold plus identifier")
    create.add_argument("--bytes", dest="byte_length", type=_integer("bytes", 16, 64))
    create.add_argument("--shares", type=_integer("shares", 2, 31))
    create.add_argument("--indices")
    create.add_argument("--pretty", action="store_true", help="group for writing")

    wallet = _command(commands, "wallet", "Export data for Bitcoin wallet software.")
    wallet_commands = wallet.add_subparsers(dest="wallet_command", required=True)
    multisig = _command(
        wallet_commands, "multisig-xpub", "Print a BIP48 coordinator xpub."
    )
    _wallet_options(multisig, timestamp=False)

    bitcoin_core = _command(
        wallet_commands, "bitcoin-core", "Emit Bitcoin Core descriptor JSON."
    )
    core_modes = bitcoin_core.add_subparsers(dest="core_mode", required=True)
    for name, help_text in (
        ("restore", "Emit private descriptors with signing capability."),
        ("watch-only", "Emit public descriptors without private keys."),
    ):
        mode = _command(core_modes, name, help_text)
        _wallet_options(mode, timestamp=True)

    xprv = _command(commands, "xprv", "Export the root private key (advanced).")
    xprv.add_argument("--testnet", action="store_true")
    return parser


def _dispatch(arguments: argparse.Namespace) -> int:
    command = cast(str, arguments.command)
    if command == "check":
        return _check(_artifacts(one=True))
    if command == "secret":
        _emit(_secret(_artifacts()), bool(arguments.pretty))
        return 0
    if command == "share":
        return _share_command(cast(str, arguments.index), bool(arguments.pretty))
    if command == "create":
        return _create(
            cast(str | None, arguments.header),
            cast(int | None, arguments.byte_length),
            cast(int | None, arguments.shares),
            cast(str | None, arguments.indices),
            bool(arguments.pretty),
        )
    if command == "checksum":
        return _checksum(cast(str | None, arguments.header), bool(arguments.pretty))
    if command == "correct":
        return _correct(
            bool(arguments.residue),
            tuple(cast(list[int], arguments.erasures)),
            cast(str, arguments.prefix),
            bool(arguments.pretty),
        )
    if command == "xprv":
        _print("Warning: xprv grants secret root signing authority.", err=True)
        _print(master_xprv(_master_seed(), testnet=bool(arguments.testnet)))
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
