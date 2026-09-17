"""Provide the command-line adapter for codex32-native workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Literal, NamedTuple, cast

from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError
from codex32._cli_input import (
    CorrectionDeclined,
    InteractiveConfirmationRequired,
    _card_text,
    _confirm_correction,
    _correction_candidates,
    _entered_groups,
    _fingerprint_matcher,
    _render_groups,
    _require_correction_confirmation,
    _suggestions,
)
from codex32._cli_input import InputError as _UsageError
from codex32._cli_input import read_artifacts as _artifacts
from codex32._cli_input import read_text as _text
from codex32._cli_parser import parser as _parser
from codex32.bip93 import (
    IDX_SORT,
    Header,
    Secret,
    Share,
    _normalize_target,
    derive_share,
    parse_codex32,
    recover_secret,
)
from codex32.correction import _best, _residue_low_discrimination, correct_worksheet_residue
from codex32.errors import CodexError, HeaderCollision, InvalidCorrectionInput
from codex32.generation import (
    ConfirmationResult,
    CreationCeremony,
    generate_master_seed,
)
from codex32.profiles import Profile, _profile_rules
from codex32.profiles.ms32 import MasterSeed
from codex32.profiles.ms32 import (
    _text_length as _ms_text_length,
)
from codex32.wallet import master_xprv

Artifact = Share | Secret


class _CliContext(NamedTuple):
    prog: str
    master_seed: bool
    profiles: tuple[Profile, ...] | None
    initial_prefix: str


_GENERIC = _CliContext("codex32", False, None, "")
_MASTER_SEED = _CliContext("ms32", True, (Profile.MS,), "MS1")


class _CommandError(Exception):
    pass


class _WalletSetupInterrupted(Exception):
    pass


class _CoreSelectionInterrupted(Exception):
    pass


def _print(text: str, *, err: bool = False, danger: bool = False) -> None:
    if danger and sys.stderr.isatty():
        label = text.split(maxsplit=1)[0]
        text = text.replace(label, f"\x1b[1;31m{label}\x1b[0m", 1)
    print(text, file=sys.stderr if err else sys.stdout)


def _secret(artifacts: list[Artifact]) -> Secret:
    if len(artifacts) == 1 and isinstance(artifacts[0], Secret):
        return artifacts[0]
    if not all(isinstance(artifact, Share) for artifact in artifacts):
        raise _UsageError("Recovery accepts ordinary shares or one complete secret.")
    try:
        return recover_secret([artifact for artifact in artifacts if isinstance(artifact, Share)])
    except CodexError as error:
        raise _UsageError(str(error)) from error


def _master_seed(fingerprint: Callable[[MasterSeed], bytes] | None = None) -> MasterSeed:
    if isinstance(
        value := _secret(_artifacts(profiles=(Profile.MS,), initial_prefix="MS1", fingerprint=fingerprint)),
        MasterSeed,
    ):
        return value
    raise _UsageError("Wallet commands accept only Bitcoin master-seed secrets.")


def _summary(artifact: Artifact, *, valid: bool = False) -> list[str]:
    header = artifact.header
    if artifact.profile is None:
        heading = (
            f"codex32 share {header.index.upper()}"
            if isinstance(artifact, Share)
            else f"{'Unshared' if header.threshold == 0 else 'Shared'} codex32 secret"
        )
        if valid and isinstance(artifact, Secret):
            heading = heading[0].lower() + heading[1:]
        lines = [f"{'Valid ' if valid else ''}{heading}.", f"HRP: {artifact.hrp.upper()}"]
    else:
        name = _profile_rules(artifact.profile).label
        if isinstance(artifact, Share):
            name = name.replace("master seed", "master-seed").replace("HSM secret", "HSM-secret")
            heading = f"{name} share {header.index.upper()}"
        else:
            heading = f"{'Unshared' if header.threshold == 0 else 'Shared'} {name}"
        if valid and isinstance(artifact, Secret):
            heading = heading[0].lower() + heading[1:]
        lines = [f"{'Valid ' if valid else ''}{heading}."]
    lines.append(f"Backup identifier: {header.identifier.upper()}")
    if header.threshold:
        lines.append(f"Shares needed for recovery: {header.threshold}")
    return lines


def _render(
    artifact: Artifact,
    pretty: bool,
    observed: str = "",
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> str:
    if not pretty:
        return artifact.text
    lines = _summary(artifact)
    if isinstance(artifact, MasterSeed) and fingerprint is not None:
        lines.append(f"Master fingerprint: {fingerprint(artifact).hex().upper()}")
    return "\n".join((*lines, "", _card_text(artifact.text, observed=observed)))


def _emit(
    artifact: Artifact,
    plain: bool,
    *,
    err: bool = False,
    gap: bool = False,
    observed: str = "",
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> None:
    pretty = (sys.stderr if err else sys.stdout).isatty() and not plain
    _print(
        ("\n" if gap and pretty else "") + _render(artifact, pretty, observed, fingerprint),
        err=err,
    )


def _share_command(index: str, plain: bool, context: _CliContext, core: BitcoinCore | None = None) -> int:
    try:
        index = _normalize_target(index, label="share index")
    except CodexError as error:
        raise _UsageError(f"Choose one share index from {IDX_SORT[1:].upper()}.") from error
    artifacts = _artifacts(
        basis=True,
        excluded_index=index,
        profiles=context.profiles,
        initial_prefix=context.initial_prefix,
        fingerprint=core.fingerprint if core is not None else None,
    )
    try:
        derived = derive_share(artifacts, index)
    except CodexError as error:
        raise _CommandError(str(error)) from error
    _emit(derived, plain)
    if sys.stdin.isatty() and sys.stdout.isatty() and not plain:
        try:
            _confirm_card(derived)
        except (EOFError, KeyboardInterrupt) as error:
            _print("Recovery card not confirmed.", err=True)
            return 130 if isinstance(error, KeyboardInterrupt) else 2
        _print("Recovery card confirmed.", err=True)
    return 0


def _creation_header(value: str | None) -> tuple[Profile, int | None, str | None]:
    if value is None:
        return Profile.MS, None, None
    lowered = value.lower()
    if lowered != value and value.upper() != value:
        raise _UsageError("The set header must use either uppercase or lowercase.")
    if "1" in lowered:
        hrp, header = lowered.rsplit("1", 1)
        if hrp != Profile.MS.value:
            raise _UsageError("The set header must begin with ms1.")
        profile = Profile.MS
    else:
        profile, header = Profile.MS, lowered
    if len(header) not in (1, 5) or header[0] not in "023456789":
        raise _UsageError(
            "Enter a threshold alone or a complete backup header containing "
            "a threshold and four-character identifier."
        )
    threshold = int(header[0])
    if len(header) == 1:
        return profile, threshold, None
    try:
        identifier = Header(threshold, header[1:], "s").identifier
    except CodexError as error:
        raise _UsageError(f"Invalid backup header: {error}") from error
    return profile, threshold, identifier


def _creation_source(
    profile: Profile,
    fingerprint: Callable[[MasterSeed], bytes] | None = None,
) -> bytes | Artifact:
    prefill = ""
    while True:
        value = _text(
            "Enter an existing Bitcoin codex32 secret or hexadecimal seed",
            optional=True,
            prefill=prefill,
            prompt_end=":\n> ",
        )
        prefill = ""
        try:
            if value:
                return bytes.fromhex(value)
        except ValueError:
            pass
        try:
            return parse_codex32(value)
        except CodexError as error:
            if not sys.stdin.isatty():
                raise _UsageError(str(error)) from error
            candidates = _suggestions(
                value,
                "",
                (profile,),
                [],
                allowed=lambda item: isinstance(item.artifact, Secret) and item.artifact.profile is profile,
                fingerprint=fingerprint,
            )
            if (
                len(candidates) == 1
                and isinstance(candidate := candidates[0].artifact, Secret)
                and candidate.profile is profile
            ):
                confirmation = _confirm_correction(candidates[0], [], False, fingerprint)
                if confirmation is True:
                    return candidate
                if confirmation is False:
                    _print("", err=True)
                    prefill = value
                    continue
            _print(
                f"Rejected: {error} Re-enter the existing secret or hexadecimal seed.",
                err=True,
            )


def _confirm_card(artifact: Artifact, confirm: Callable[[str], ConfirmationResult] | None = None) -> None:
    kind = "share" if isinstance(artifact, Share) else "secret"
    _print("", err=True)
    _text(
        f"Write this {kind} on a new recovery card, then press Enter",
        optional=True,
        prompt_end=". ",
    )
    clear = "\x1b[3J\x1b[2J\x1b[H" if sys.stderr.isatty() else ""
    entered = _text(
        clear + f"Re-enter the {kind} from the recovery card",
        prompt_end=":\n> ",
        preserve_groups=True,
    )
    expected = artifact.text
    groups, changed = _entered_groups(entered, expected)
    while changed:
        start = min(changed)
        end = start + 1
        while end in changed:
            end += 1
        _print(_render_groups(groups, changed, len(expected), range(start, end)), err=True)
        prefill = "".join(groups[start:end]).strip()
        if len(prefill.split()) < 2:
            prefill = " ".join(groups[start:end]).strip()
        replacement = _text(
            "Review the marked text on your recovery card",
            prompt_end=":\n> ",
            preserve_groups=True,
            optional=True,
            prefill=prefill,
        )
        compact = "".join(replacement.split())
        if compact.lower() == expected.lower():
            groups = [replacement]
            break
        if len(compact) > len(expected[start * 4 : end * 4]) and compact.lower().startswith(
            (expected.split("1", 1)[0] + "1").lower()
        ):
            _print(
                "Please re-enter only the highlighted region that remains incorrect.",
                err=True,
            )
            continue
        if not compact:
            continue
        groups[start:end], remaining = _entered_groups(replacement, expected[start * 4 : end * 4])
        changed.difference_update(range(start, end))
        changed.update(start + i for i in remaining)
    entered = "".join(groups)
    if "".join(entered.split()).lower() != expected.lower():
        raise RuntimeError("Confirmation mismatch.")
    if confirm is not None and not confirm(entered).accepted:
        raise RuntimeError("Confirmation rejected.")


def _generated_secret(
    source: bytes | None,
    byte_length: int | None,
    identifier: str | None,
    fingerprint: Callable[[bytes], bytes] | None = None,
) -> MasterSeed:
    return generate_master_seed(
        source,
        byte_length=byte_length,
        identifier=identifier,
        fingerprint=fingerprint,
    )


def _initialize_wallet(
    core: BitcoinCore,
    secret: MasterSeed,
    *,
    account: int = 0,
    timestamp: int | Literal["now"] = "now",
    fresh: bool = True,
    confirmed: bool = True,
) -> int:
    assert isinstance(secret, MasterSeed)
    try:
        if confirmed:
            _print("Master-seed backup confirmed.\n", err=True)
        name = core.initialize(
            secret,
            lambda prompt: _text(prompt, optional=True),
            lambda message: _print(message, err=True),
            account=account,
            timestamp=timestamp,
        )
        version = f"{core.version // 10000}.{core.version // 100 % 100}.{core.version % 100}"
        _print("Bitcoin Core spending wallet initialized.", err=True)
        _print(
            f"\n{'Record these wallet details' if fresh else 'Wallet details'}:",
            err=True,
        )
        _print(f"Backup identifier: {secret.header.identifier.upper()}", err=True)
        _print(
            f"Wallet name: {json.dumps(name)}; Bitcoin Core version: {version}",
            err=True,
        )
        _print(
            f"Master fingerprint: {core.fingerprint(secret).hex().upper()}",
            err=True,
        )
        _print("Derivation standards: BIP44, BIP49, BIP84, and BIP86", err=True)
        _print(f"Account number: {account}", err=True)
        if fresh:
            _print(
                "\nComplete the Fresh initialization section of the wallet record.",
                err=True,
            )
        return 0
    except (EOFError, KeyboardInterrupt) as error:
        raise _WalletSetupInterrupted from error
    except BitcoinCoreError as error:
        raise _CommandError(
            f"{error} The recovery material remains valid, but wallet initialization did not complete."
        ) from error


def _connected_core(fallback: str | None = None) -> BitcoinCore:
    try:
        core = BitcoinCore.connect(
            lambda prompt: _text(prompt, optional=True),
            lambda message: _print(message, err=True),
        )
        _print("", err=True)
        return core
    except KeyboardInterrupt as error:
        raise _CoreSelectionInterrupted from error
    except BitcoinCoreError as error:
        suggestion = (
            f" Run 'codex32 {fallback}' instead for a Core-independent operation."
            if fallback is not None
            else ""
        )
        raise _CommandError(str(error) + suggestion) from error


def _create(
    header: str | None,
    byte_length: int | None,
    shares: int | None,
    indices: str | None,
    existing: bool,
) -> int:
    profile, selected_threshold, identifier = _creation_header(header)
    threshold = 0 if selected_threshold is None else selected_threshold
    if profile is not Profile.MS:
        raise _UsageError("Only Bitcoin master-seed backups can be created.")
    if shares is not None and indices is not None:
        raise _UsageError("Choose either --shares or --indices, not both.")
    if byte_length is not None and existing:
        raise _UsageError("--bytes applies only to a new random seed.")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise _UsageError("Bitcoin backup creation requires an interactive terminal.")
    if threshold and not sys.stdin.isatty():
        raise _UsageError("Shared creation requires an interactive terminal.")
    if threshold and shares is None and indices is None:
        if threshold in (2, 3):
            shares = {2: 3, 3: 5}[threshold]
        else:
            raise _UsageError("For thresholds 4 through 9, choose --shares or --indices.")
    core = _connected_core()
    source = _creation_source(profile, core.fingerprint) if existing else None
    if not existing and not sys.stdin.isatty() and _text("", optional=True):
        raise _UsageError("Use --existing when supplying a seed or secret.")
    if isinstance(source, (Share, Secret)) and not isinstance(source, MasterSeed):
        raise _UsageError(f"Enter one {_profile_rules(profile).label}, not a share or another backup type.")
    try:
        if threshold == 0:
            if isinstance(source, MasterSeed):
                if identifier is not None and identifier != source.header.identifier:
                    raise _UsageError(
                        "To change the existing secret's identifier, choose a sharing threshold from 2 through 9."
                    )
                secret = source
            else:
                secret = _generated_secret(source, byte_length, identifier, core.fingerprint_seed)
            _emit(secret, False, fingerprint=core.fingerprint)
            if sys.stdin.isatty():
                _confirm_card(secret)
            return (
                _initialize_wallet(core, secret, timestamp=0 if existing else "now", fresh=not existing)
                if core is not None
                else 0
            )
        if isinstance(source, MasterSeed):
            ceremony = CreationCeremony.from_secret(
                source,
                threshold=threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
        elif source is not None:
            source_secret = _generated_secret(source, None, identifier, core.fingerprint_seed)
            ceremony = CreationCeremony.from_secret(
                source_secret,
                threshold=threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
        else:
            ceremony = CreationCeremony.master_seed(
                threshold=threshold,
                byte_length=16 if byte_length is None else byte_length,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
    except HeaderCollision as error:
        raise _CommandError(f"{error}; choose another set header") from error
    except CodexError as error:
        raise _CommandError(str(error)) from error
    output_count = shares if shares is not None else len(indices or "")
    for position in range(output_count):
        artifact = ceremony.next_share()
        _emit(artifact, False, gap=position > 0)
        _confirm_card(artifact, ceremony.confirm)
        _print(f"Recovery card {position + 1} of {output_count} confirmed.", err=True)
    finished = ceremony.finish()
    assert isinstance(finished, MasterSeed)
    if core is not None:
        return _initialize_wallet(core, finished, timestamp=0 if existing else "now", fresh=not existing)
    _print("\nEvery recovery card was confirmed from its re-entered text.", err=True)
    return 0


def _correct(
    residue: bool,
    erasures: tuple[int, ...],
    byte_length: int | Literal["?"] | None,
    plain: bool,
    context: _CliContext,
    core: BitcoinCore | None = None,
) -> int:
    prompt = "Enter the worksheet residue" if residue else "Enter the damaged codex32 string"
    value = _text(
        prompt,
        preserve_groups=not residue,
        prefill=context.initial_prefix if not residue else "",
        prompt_end=":\n> ",
    )
    if residue:
        if byte_length is not None:
            raise _UsageError("--bytes cannot be used with --residue.")
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
        else:
            _require_correction_confirmation(
                _residue_low_discrimination(value, tuple(p - 1 for p in erasures), result)
            )
        for correction in result:
            _print(
                f"Add {correction.addend} at position "
                f"{correction.reverse_index + 1}, counting backward from the end."
            )
        return 0
    if erasures:
        raise _UsageError("--erasure can be used only with --residue.")
    normalized = "".join(value.split())
    separator = normalized.lower().rfind("1")
    if separator <= 0:
        raise _UsageError("Enter a complete application prefix followed by the separator 1.")
    hrp = normalized[:separator].lower()
    if context.master_seed and hrp != Profile.MS.value:
        raise _UsageError("This command accepts only Bitcoin master-seed input beginning with ms1.")
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
        value,
        hrp,
        byte_length,
        value[: separator + 1],
    )
    if not complete and not candidates:
        raise _CommandError("The correction search did not complete within ten seconds.")
    if ambiguous:
        raise _CommandError("More than one correction is possible; none was selected.")
    if not candidates:
        raise _CommandError("No valid correction found. Check the original backup.")
    if context.master_seed and len(candidates) > 1:
        core = core or _connected_core("correct")
        candidates = _best(candidates, fingerprint_match=_fingerprint_matcher(core.fingerprint))
    if len(candidates) != 1:
        raise _CommandError("Several corrections are possible. Check the original backup.")
    fixed = candidates[0]
    _require_correction_confirmation(fixed.low_checksum_discrimination)
    if context.master_seed:
        core = core or _connected_core("correct")
    warning = (
        "Warning: This is only a correction suggestion. Compare it with the original backup before using it."
    )
    _print(warning, err=True)
    _emit(
        fixed.artifact,
        plain,
        err=True,
        observed=value,
        fingerprint=core.fingerprint if core is not None else None,
    )
    return 1


def _bitcoin_core(account: int, timestamp: int | Literal["now"]) -> int:
    if not sys.stdin.isatty():
        raise _UsageError("Bitcoin Core wallet initialization requires an interactive terminal.")
    _print("Warning: This imports private descriptors that can spend funds.", err=True, danger=True)
    core = _connected_core()
    secret = _master_seed(core.fingerprint)
    return _initialize_wallet(
        core,
        secret,
        account=account,
        timestamp=timestamp,
        fresh=False,
        confirmed=False,
    )


def _dispatch(arguments: argparse.Namespace, context: _CliContext) -> int:
    command = cast(str, arguments.command)
    plain = bool(getattr(arguments, "plain", False)) or (command == "correct" and not sys.stdin.isatty())
    fingerprint_core: BitcoinCore | None = None
    if context.master_seed and command in ("secret", "share"):
        fingerprint_core = _connected_core(command)
    if command == "check":
        artifacts = _artifacts(
            one=True,
            profiles=context.profiles,
            initial_prefix=context.initial_prefix,
        )
        _print("\n\n".join("\n".join(_summary(item, valid=True)) for item in artifacts))
        return 0
    if command == "secret":
        _emit(
            _secret(
                _artifacts(
                    profiles=context.profiles,
                    initial_prefix=context.initial_prefix,
                    fingerprint=fingerprint_core.fingerprint if fingerprint_core is not None else None,
                )
            ),
            plain,
            fingerprint=fingerprint_core.fingerprint if fingerprint_core is not None else None,
        )
        return 0
    if command == "share":
        return _share_command(cast(str, arguments.index), plain, context, fingerprint_core)
    if command == "create":
        return _create(
            cast(str | None, arguments.header),
            cast(int | None, arguments.byte_length),
            cast(int | None, arguments.shares),
            cast(str | None, arguments.indices),
            bool(arguments.existing),
        )
    if command == "correct":
        return _correct(
            bool(arguments.residue),
            tuple(cast(list[int], arguments.erasures)),
            cast(int | Literal["?"] | None, getattr(arguments, "byte_length", None)),
            plain,
            context,
            fingerprint_core,
        )
    if command == "xprv":
        secret = _master_seed()
        _print(
            "Warning: The following root private key can spend funds from every wallet derived "
            "from this seed. Keep it secret.\n",
            err=True,
            danger=True,
        )
        _print(master_xprv(secret, testnet=bool(arguments.testnet)))
        return 0
    if command == "wallet":
        return _bitcoin_core(
            int(arguments.account),
            cast(int | Literal["now"], arguments.timestamp),
        )
    raise AssertionError(f"unhandled command {command!r}")


def _main(context: _CliContext, argv: Sequence[str] | None = None) -> int:
    parser = _parser(context.prog, master_seed=context.master_seed)
    arguments_list = sys.argv[1:] if argv is None else argv
    if not arguments_list:
        arguments_list = ("--help",)
    try:
        arguments = parser.parse_args(arguments_list)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    scope = f"{context.prog} {arguments.command}"
    try:
        return _dispatch(arguments, context)
    except CorrectionDeclined:
        return 1
    except InteractiveConfirmationRequired:
        _print(f"{context.prog}: interactive confirmation required", err=True)
        return 1
    except _UsageError as error:
        _print(f"{scope}: {error}", err=True)
        return 2
    except (_CommandError, CodexError) as error:
        _print(f"{scope}: {error}", err=True)
        return 1
    except BitcoinCoreError as error:
        _print(f"{scope}: {error}", err=True)
        return 1
    except EOFError:
        _print(f"{scope}: Input ended before recovery completed.", err=True)
        return 2
    except _WalletSetupInterrupted:
        _print(
            f"{scope}: Interrupted. The recovery cards are valid, but Bitcoin Core wallet "
            "initialization was not completed.",
            err=True,
        )
        return 130
    except _CoreSelectionInterrupted:
        _print(f"{scope}: Interrupted.", err=True)
        return 130
    except KeyboardInterrupt:
        message = "Interrupted. Mark every card from this incomplete creation void."
        _print(
            f"{scope}: {message if arguments.command == 'create' else 'Interrupted.'}",
            err=True,
        )
        return 130


def main(argv: Sequence[str] | None = None) -> int:
    """Run the generic codex32 command-line façade."""
    return _main(_GENERIC, argv)


def ms_main(argv: Sequence[str] | None = None) -> int:
    """Run the Bitcoin master-seed command-line façade."""
    return _main(_MASTER_SEED, argv)


if __name__ == "__main__":
    raise SystemExit(main())
