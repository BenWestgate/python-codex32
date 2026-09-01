# fmt: off
"""Small command-line adapter for codex32-native workflows."""
# ruff: noqa: I001

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Callable, Sequence
from typing import Literal, cast

from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError
from codex32._cli_input import InputError as _UsageError
from codex32._cli_input import _correction_candidates
from codex32._cli_input import read_artifacts as _artifacts
from codex32._cli_input import read_text as _text
from codex32._cli_parser import parser as _parser
from codex32.bip93 import IDX_SORT, Header, Secret, Share
from codex32.bip93 import _normalize_target, complete_checksum, derive_share, parse_codex32, recover_secret
from codex32.correction import correct_worksheet_residue
from codex32.errors import CodexError, HeaderCollision, InvalidCorrectionInput
from codex32.generation import ConfirmationResult, CreationCeremony, generate_core_lightning_secret, generate_master_seed
from codex32.profiles import Profile, _profile_rules
from codex32.profiles.cl32 import CoreLightningSecret
from codex32.profiles.ms32 import MasterSeed, _fingerprint_from_seed, _text_length as _ms_text_length
from codex32.wallet import core_descriptors, master_xprv, multisig_account_xpub
Artifact = Share | Secret
class _CommandError(Exception): pass
class _WalletSetupInterrupted(Exception): pass
def _print(text: str, *, err: bool = False, danger: bool = False) -> None:
    if danger and sys.stderr.isatty():
        label = text.split(maxsplit=1)[0]
        text = text.replace(label, f"\x1b[1;31m{label}\x1b[0m", 1)
    print(text, file=sys.stderr if err else sys.stdout)
def _secret(artifacts: list[Artifact]) -> Secret:
    if len(artifacts) == 1 and isinstance(artifacts[0], Secret): return artifacts[0]
    if not all(isinstance(artifact, Share) for artifact in artifacts):
        raise _UsageError("Recovery accepts ordinary shares or one complete secret.")
    try:
        return recover_secret([artifact for artifact in artifacts if isinstance(artifact, Share)])
    except CodexError as error:
        raise _UsageError(str(error)) from error
def _master_seed() -> MasterSeed:
    value = _secret(_artifacts(profiles=(Profile.MS,)))
    if not isinstance(value, MasterSeed):
        raise _UsageError("Wallet commands accept only Bitcoin master-seed secrets.")
    return value
def _summary(artifact: Artifact, *, valid: bool = False) -> list[str]:
    header = artifact.header
    name = _profile_rules(artifact.profile).label
    if isinstance(artifact, Share):
        name = name.replace("master seed", "master-seed").replace("HSM secret", "HSM-secret")
        heading = f"{name} share {header.index.upper()}"
    else:
        heading = f"{'Unshared' if header.threshold == 0 else 'Shared'} {name}"
    if valid and isinstance(artifact, Secret): heading = heading[0].lower() + heading[1:]
    lines = [f"{'Valid ' if valid else ''}{heading}.", f"Backup identifier: {header.identifier.upper()}"]
    if header.threshold: lines.append(f"Shares needed for recovery: {header.threshold}")
    return lines
def _group(text: str, mismatched: tuple[int, ...] = ()) -> str:
    groups = [text[start : start + 4].upper() for start in range(0, len(text), 4)]
    for index, group in enumerate(groups):
        style = "\x1b[1;31m" if index + 1 in mismatched else ("\x1b[1m" if index % 2 == 0 else "\x1b[22m")
        gap = " " if (index + 1) % 4 == 0 and index + 1 < len(groups) else ""
        groups[index] = style + group + gap
    return " ".join(groups) + "\x1b[0m"
def _render(artifact: Artifact, pretty: bool) -> str:
    if not pretty: return artifact.text
    lines = _summary(artifact)
    if isinstance(artifact, MasterSeed):
        fingerprint = _fingerprint_from_seed(artifact.seed_bytes).hex()
        lines.append(f"Master fingerprint: {fingerprint.upper()}")
    lines.extend(("", _group(artifact.text)))
    return "\n".join(lines)
def _emit(artifact: Artifact, plain: bool, *, err: bool = False, gap: bool = False) -> None:
    pretty = (sys.stderr if err else sys.stdout).isatty() and not plain
    _print(("\n" if gap and pretty else "") + _render(artifact, pretty), err=err)
def _share_command(index: str, plain: bool) -> int:
    try:
        index = _normalize_target(index, label="share index")
    except CodexError as error:
        raise _UsageError(f"Choose one share index from {IDX_SORT[1:].upper()}.") from error
    artifacts = _artifacts(basis=True, excluded_index=index, profiles=(Profile.MS, Profile.CL))
    try:
        derived = derive_share(artifacts, index)
    except CodexError as error:
        raise _CommandError(str(error)) from error
    _emit(derived, plain)
    return 0
def _creation_header(value: str | None) -> tuple[Profile, int | None, str | None]:
    if value is None: return Profile.MS, None, None
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
    if len(header) not in (1, 5) or header[0] not in "023456789":
        raise _UsageError(
            "Enter a threshold alone or a complete backup header containing "
            "a threshold and four-character identifier."
        )
    threshold = int(header[0])
    if len(header) == 1: return profile, threshold, None
    try:
        identifier = Header(threshold, header[1:], "s").identifier
    except CodexError as error:
        raise _UsageError(f"Invalid backup header: {error}") from error
    return profile, threshold, identifier
def _creation_source() -> bytes | Artifact:
    value = _text("Enter an existing codex32 secret or hexadecimal seed")
    try:
        return bytes.fromhex(value)
    except ValueError:
        try:
            return parse_codex32(value)
        except CodexError as error:
            raise _UsageError(str(error)) from error
def _confirm_card(artifact: Artifact, confirm: Callable[[str], ConfirmationResult] | None = None) -> None:
    while True:
        entered = _text("Re-enter this card from the paper")
        observed, expected = "".join(entered.split()).lower(), artifact.text.lower()
        groups = tuple(group + 1 for group in range((max(len(observed), len(expected)) + 3) // 4)
            if observed[group * 4 : group * 4 + 4] != expected[group * 4 : group * 4 + 4])
        result = confirm(entered) if confirm is not None else ConfirmationResult(not groups, groups)
        if result.accepted: return
        labels = ", ".join(str(group) for group in result.mismatched_groups)
        _print(f"The re-entry differs in four-character group(s): {labels}.", err=True)
        _print("No correction was applied. Check what you typed and try again.", err=True)
        if sys.stderr.isatty(): _print(_group(artifact.text, result.mismatched_groups), err=True)
def _generated_secret(profile: Profile, source: bytes | None, byte_length: int | None,
                      identifier: str | None) -> MasterSeed | CoreLightningSecret:
    return (generate_master_seed(source, byte_length=byte_length, identifier=identifier)
        if profile is Profile.MS else generate_core_lightning_secret(source, identifier=identifier)
    )
def _initialize_wallet(core: BitcoinCore, secret: MasterSeed | CoreLightningSecret) -> int:
    assert isinstance(secret, MasterSeed)
    try:
        _print("\nEvery recovery card was confirmed from its re-entered text.", err=True)
        name = core.initialize(
            secret, lambda prompt: _text(prompt, optional=True), lambda message: _print(message, err=True)
        )
        version = f"{core.version // 10000}.{core.version // 100 % 100}.{core.version % 100}"
        _print("\nBitcoin Core wallet initialized and verified.", err=True)
        _print(f"Wallet name: {json.dumps(name)}; Bitcoin Core version: {version}", err=True)
        _print(f"Master fingerprint: {_fingerprint_from_seed(secret.seed_bytes).hex().upper()}", err=True)
        _print("Account 0 policies: BIP44, BIP49, BIP84, and BIP86", err=True)
        _print("Complete the fresh-wallet section of the separately stored wallet record.", err=True)
        wallet_option = shlex.quote(f"-rpcwallet={name}")
        command = (f"bitcoin-cli -rpcconnect=127.0.0.1 {wallet_option} listdescriptors | "
                   "jq -c '[.descriptors[] | {desc,timestamp,active,internal,range,next_index}]' | qr")
        _print(f"Optional public-descriptor QR export:\n{command}", err=True)
        return 0
    except (EOFError, KeyboardInterrupt) as error:
        raise _WalletSetupInterrupted from error
    except BitcoinCoreError as error:
        message = f"{error} The confirmed cards remain valid, but wallet initialization did not complete."
        raise _CommandError(message) from error
def _create(header: str | None, byte_length: int | None, shares: int | None,
            indices: str | None, existing: bool, plain: bool) -> int:
    profile, selected_threshold, identifier = _creation_header(header)
    threshold = 0 if selected_threshold is None else selected_threshold
    if profile not in (Profile.MS, Profile.CL): raise _UsageError("Only Bitcoin and Core Lightning can be created.")
    if shares is not None and indices is not None: raise _UsageError("Choose either --shares or --indices, not both.")
    if byte_length is not None and profile is Profile.CL:
        raise _UsageError("--bytes is only for Bitcoin master seeds; Core Lightning secrets are always 32 bytes.")
    if byte_length is not None and existing: raise _UsageError(
        "--bytes applies only when generating a new random seed."
    )
    fresh_bitcoin = profile is Profile.MS and not existing
    if fresh_bitcoin and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise _UsageError("Fresh Bitcoin backup creation requires an interactive terminal.")
    if threshold and not sys.stdin.isatty(): raise _UsageError(
        "Shared backup creation requires an interactive terminal."
    )
    try:
        core = BitcoinCore.connect() if fresh_bitcoin else None
    except BitcoinCoreError as error:
        raise _CommandError(str(error)) from error
    source = _creation_source() if existing else None
    if not existing and not sys.stdin.isatty() and _text("", optional=True):
        raise _UsageError("Use --existing when supplying a seed or secret.")
    expected_type = MasterSeed if profile is Profile.MS else CoreLightningSecret
    if isinstance(source, (Share, Secret)) and not isinstance(source, expected_type):
        raise _UsageError(
            f"Enter one {_profile_rules(profile).label}, not a share or another backup type."
        )
    if threshold and shares is None and indices is None: shares = threshold + 2
    try:
        if threshold == 0:
            if isinstance(source, (MasterSeed, CoreLightningSecret)):
                raise _UsageError(
                    "The supplied secret is already complete; choose a sharing threshold from 2 through 9."
                )
            secret = _generated_secret(profile, source, byte_length, identifier)
            _emit(secret, plain)
            if sys.stdin.isatty(): _confirm_card(secret)
            return _initialize_wallet(core, secret) if core is not None else 0
        if isinstance(source, (MasterSeed, CoreLightningSecret)):
            ceremony = CreationCeremony.from_secret(
                source, threshold=threshold, identifier=identifier,
                share_count=shares, indices=indices,
            )
        elif source is not None:
            source_secret = _generated_secret(profile, source, None, identifier)
            ceremony = CreationCeremony.from_secret(
                source_secret, threshold=threshold, identifier=identifier,
                share_count=shares, indices=indices,
            )
        elif profile is Profile.MS:
            ceremony = CreationCeremony.master_seed(
                threshold=threshold, byte_length=16 if byte_length is None else byte_length,
                identifier=identifier, share_count=shares, indices=indices,
            )
        else:
            ceremony = CreationCeremony.core_lightning(
                threshold=threshold, identifier=identifier, share_count=shares, indices=indices,
            )
    except HeaderCollision as error:
        raise _CommandError(f"{error}; choose another set header") from error
    except CodexError as error:
        raise _CommandError(str(error)) from error
    output_count = shares if shares is not None else len(indices or "")
    for position in range(output_count):
        artifact = ceremony.next_share()
        _emit(artifact, plain, gap=position > 0)
        _confirm_card(artifact, ceremony.confirm)
    secret = ceremony.finish()
    if core is not None: return _initialize_wallet(core, secret)
    _print("\nEvery recovery card was confirmed from its re-entered text.", err=True)
    return 0
def _checksum(header: str | None, plain: bool) -> int:
    instruction = "Enter the header first, then only" if header is None else "Enter only"
    warning = (
        "DANGER: Incorrect input can make the wallet predictable and cause "
        f"permanent loss of funds. {instruction} characters generated by following "
        "the Codex32 Book dice-debiasing worksheet exactly. Do not enter raw dice "
        "rolls, seed words, hexadecimal seeds, passwords, or anything else."
    )
    _print(warning, err=True, danger=True)
    prompt = (
        "Checksum worksheet non-pink bold squares" if header is None else "Remaining non-pink bold squares"
    )
    try:
        value = (header or "") + _text(prompt)
        text = value if "1" in value else "ms1" + value
        if Profile(text[: text.rfind("1")].lower()) not in (Profile.MS, Profile.CL): raise ValueError
        artifact = complete_checksum(text)
    except (CodexError, ValueError) as error:
        raise _UsageError(
            "The input does not match the expected format of the filled-out "
            "non-pink bold squares.\nConsult the Codex32 Book and check the worksheet."
        ) from error
    _emit(artifact, plain)
    return 0
def _correct(residue: bool, erasures: tuple[int, ...],
             byte_length: int | Literal["?"] | None, plain: bool) -> int:
    prompt = "Enter the worksheet residue" if residue else "Enter the damaged codex32 string"
    value = _text(prompt, preserve_groups=not residue)
    if residue:
        if byte_length is not None:
            raise _UsageError("--bytes cannot be used with --residue.")
        try:
            result = correct_worksheet_residue(
                value, erasure_indices=tuple(position - 1 for position in erasures)
            )
        except InvalidCorrectionInput as error:
            raise _UsageError(str(error)) from error
        if result is None: raise _CommandError("No unique correction could be found.")
        if not result: _print("The worksheet residue is already correct.")
        for correction in result:
            _print(
                f"Add {correction.addend} at position "
                f"{correction.reverse_index + 1}, counting backward from the end."
            )
        return 0
    if erasures: raise _UsageError("--erasure can be used only with --residue.")
    normalized = "".join(value.split())
    lowered = normalized.lower()
    profile = next((item for item in (Profile.MS, Profile.CL) if lowered.startswith(f"{item}1")), None)
    if profile is None:
        bip39_profiles = (Profile.BIP39_12W, Profile.BIP39_24W)
        if any(lowered.startswith(f"{item}1") for item in bip39_profiles):
            raise _UsageError("Full-string correction is not available for BIP39 worksheet backups.")
        raise _UsageError(
            "The string must begin with an undamaged ms1 or cl1 prefix; prefix correction is not attempted."
        )
    if byte_length is not None and profile is not Profile.MS:
        raise _UsageError("--bytes can be used only with an ms1 master-seed backup.")
    try:
        parse_codex32(normalized)
    except CodexError:
        pass
    else:
        if isinstance(byte_length, int) and len(normalized) != _ms_text_length(byte_length):
            raise _UsageError("--bytes does not match the valid master-seed backup length.")
        _print("The codex32 string is already valid.")
        return 0
    candidates, complete, _deadline, ambiguous = _correction_candidates(
        value, profile, byte_length, value[:3],
    )
    if not complete:
        raise _CommandError(
            "The bounded search did not complete within ten seconds; no correction accepted."
        )
    if ambiguous:
        raise _CommandError("More than one correction is possible; none was selected.")
    if not candidates:
        raise _CommandError("No valid correction found. Check the original backup.")
    if len(candidates) != 1:
        raise _CommandError(
        "More than one equally ranked correction was found; none was selected."
        )
    fixed = candidates[0]
    warning = (
        "Warning: This is only a correction suggestion. Compare it with the original backup before using it."
    )
    _print(warning, err=True)
    _emit(fixed.artifact, plain, err=True)
    return 1
def _bitcoin_core(account: int, timestamp: int | Literal["now"],
                  testnet: bool, private: bool) -> int:
    warning = (
        (
            "Warning: The following Bitcoin Core data contains the root private "
            "key and can spend funds. Import it only into the intended encrypted wallet."
        )
        if private else (
            "Warning: Do not enter codex32 shares on a network-connected computer merely to create "
            "a watch-only wallet. Prefer exporting public descriptors from the offline signing wallet."
        )
    )
    _print(warning, err=True, danger=private)
    secret = _master_seed()
    records = core_descriptors(secret, account=account, testnet=testnet, private=private, timestamp=timestamp)
    _print(json.dumps(records, separators=(",", ":")))
    return 0

def _dispatch(arguments: argparse.Namespace) -> int:
    command = cast(str, arguments.command)
    plain = bool(getattr(arguments, "plain", False))
    if command == "check":
        _print("\n\n".join("\n".join(_summary(item, valid=True)) for item in _artifacts(one=True)))
        return 0
    if command == "secret": _emit(_secret(_artifacts()), plain); return 0
    if command == "share": return _share_command(cast(str, arguments.index), plain)
    if command == "create":
        return _create(
            cast(str | None, arguments.header),
            cast(int | None, arguments.byte_length),
            cast(int | None, arguments.shares),
            cast(str | None, arguments.indices),
            bool(arguments.existing),
            plain,
        )
    if command == "checksum": return _checksum(cast(str | None, arguments.header), plain)
    if command == "correct":
        return _correct(
            bool(arguments.residue),
            tuple(cast(list[int], arguments.erasures)),
            cast(int | Literal["?"] | None, arguments.byte_length),
            plain,
        )
    if command == "xprv":
        secret = _master_seed()
        _print(
            "Warning: The following root private key can spend funds from every wallet derived "
            "from this seed. Keep it secret.",
            err=True,
            danger=True,
        )
        _print(master_xprv(secret, testnet=bool(arguments.testnet)))
        return 0
    if command == "wallet" and arguments.wallet_command == "multisig-xpub":
        _print(multisig_account_xpub(
            _master_seed(), account=int(arguments.account), testnet=bool(arguments.testnet)))
        return 0
    if command == "wallet" and arguments.wallet_command == "bitcoin-core":
        return _bitcoin_core(
            int(arguments.account),
            cast(int | Literal["now"], arguments.timestamp),
            bool(arguments.testnet),
            arguments.core_mode == "restore",
        )
    raise AssertionError(f"unhandled command {command!r}")

def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments_list = sys.argv[1:] if argv is None else argv
    if not arguments_list: arguments_list = ("--help",)
    try:
        arguments = parser.parse_args(arguments_list)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    scope = f"codex32 {arguments.command}"
    try:
        return _dispatch(arguments)
    except _UsageError as error:
        _print(f"{scope}: {error}", err=True)
        return 2
    except (_CommandError, CodexError) as error:
        _print(f"{scope}: {error}", err=True)
        return 1
    except EOFError:
        _print(f"{scope}: Input ended before recovery completed.", err=True)
        return 2
    except _WalletSetupInterrupted:
        _print(
            f"{scope}: Interrupted. The recovery cards are valid, but Bitcoin Core wallet "
            "initialization was not completed.", err=True,
        )
        return 130
    except KeyboardInterrupt:
        message = "Interrupted. Mark every card from this incomplete creation void."
        _print(f"{scope}: {message if arguments.command == 'create' else 'Interrupted.'}", err=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
