"""Simple CLI for codex32."""

import ctypes
import json
import os
import sys
from pathlib import Path

import click
from bip32 import BIP32

from codex32 import (
    CoreLightningSecret,
    HeaderCollision,
    MasterSeed,
    Profile,
    Secret,
    Share,
    complete_checksum,
    derive_share,
    generate_master_seed,
    parse_codex32,
    recover_secret,
    split_secret,
)
from codex32.bech32 import CHARSET
from codex32.bip93 import IDX_SORT
from codex32.correction import correct_worksheet_residue
from codex32.descriptor import (
    DESCRIPTOR_TEMPLATES,
    descriptors_from_node,
)
from codex32.errors import CodexError, InvalidCorrectionInput
from codex32.indel import CorrectionCandidate, search_codex32_corrections

CodexArtifact = Share | Secret


def _format_groups(
    value: str,
    highlight_positions: set[int] | None = None,
    row_len: int = 4,
    base_style: str = "",
) -> str:
    """Group a string, optionally highlighting one-based character positions."""
    highlights = highlight_positions or set()
    groups = []
    for group_index, start in enumerate(range(0, len(value), 4)):
        group_end = min(start + 4, len(value))
        underline = any(
            position in highlights for position in range(start + 1, group_end + 1)
        )
        intensity = "\x1b[22m" if group_index % 2 else "\x1b[1m"
        group = base_style + intensity
        if underline:
            group += "\x1b[4m"
        group += value[start:group_end].upper()
        if underline:
            group += "\x1b[24m"
        if (group_index + 1) % row_len == 0:
            group += " "
        groups.append(group)
    return " ".join(groups) + "\x1b[0m"


def _format_transcription_string(
    string: CodexArtifact, highlight_positions: set[int] | None = None
) -> str:
    """Format codex32 metadata and visually grouped transcription text."""
    scheme = (
        "Unshared"
        if string.header.threshold == 0
        else f"{string.header.threshold}-of-N"
    )
    label = (
        "\x1b[1;31mS — SECRET:   "
        if string.header.index == "s"
        else string.header.index.upper() + ":  "
    )
    base_style = "\x1b[31m" if string.header.index == "s" else ""
    return (
        f"Threshold Scheme:    {scheme}\n"
        f"codex32 Identifier:  {string.header.identifier.upper()}\n\n"
        f"{label}"
        f"{_format_groups(string.text, highlight_positions, base_style=base_style)}"
    )


def _format_codex32_string(
    s: CodexArtifact,
    node: BIP32,
    highlight_positions: set[int] | None = None,
    fingerprint_label: str = "Master Fingerprint",
) -> str:
    """Format a string with wallet fingerprint and transcription grouping."""
    formatted = _format_transcription_string(s, highlight_positions)
    identifier_line = f"codex32 Identifier:  {s.header.identifier.upper()}\n"
    fingerprint_line = f"{fingerprint_label}:  {node.get_fingerprint().hex().upper()}\n"
    return formatted.replace(identifier_line, identifier_line + fingerprint_line, 1)


def _align_strings(source: str, target: str) -> tuple[str, str]:
    """Return a deterministic minimum-edit alignment of two short strings."""
    rows = len(source) + 1
    columns = len(target) + 1
    costs = [[0] * columns for _ in range(rows)]
    steps = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        costs[row][0] = row
        steps[row][0] = "delete"
    for column in range(1, columns):
        costs[0][column] = column
        steps[0][column] = "insert"
    for row in range(1, rows):
        for column in range(1, columns):
            same = source[row - 1].lower() == target[column - 1].lower()
            choices = (
                (costs[row - 1][column - 1] + (not same), 0, "diagonal"),
                (costs[row - 1][column] + 1, 1, "delete"),
                (costs[row][column - 1] + 1, 2, "insert"),
            )
            cost, _priority, step = min(choices)
            costs[row][column] = int(cost)
            steps[row][column] = step

    aligned_source = []
    aligned_target = []
    row = len(source)
    column = len(target)
    while row or column:
        step = steps[row][column]
        if step == "diagonal":
            aligned_source.append(source[row - 1])
            aligned_target.append(target[column - 1])
            row -= 1
            column -= 1
        elif step == "delete":
            aligned_source.append(source[row - 1])
            aligned_target.append("-")
            row -= 1
        else:
            aligned_source.append("-")
            aligned_target.append(target[column - 1])
            column -= 1
    return "".join(reversed(aligned_source)), "".join(reversed(aligned_target))


def _format_correction_alignment(source: str, target: str) -> str:
    """Show a compact wrapped input/candidate alignment."""
    aligned_source, aligned_target = _align_strings(source, target)
    lines = ["Input/candidate alignment:"]
    for start in range(0, len(aligned_source), 64):
        input_chunk = aligned_source[start : start + 64].upper()
        candidate_chunk = aligned_target[start : start + 64].upper()
        markers = "".join(
            " " if before == after else "^"
            for before, after in zip(input_chunk, candidate_chunk)
        )
        if start:
            lines.append("")
        lines.extend(
            (
                f"Input:     {input_chunk}",
                f"           {markers}",
                f"Candidate: {candidate_chunk}",
            )
        )
    return "\n".join(lines)


def _format_corrected_string(original: str, candidate: CorrectionCandidate) -> str:
    """Highlight a candidate and describe its weighted edit path."""

    def count(value: int, singular: str) -> str:
        return f"{value} {singular if value == 1 else singular + 's'}"

    group_positions = {
        position
        for group in candidate.groups
        for start in (
            (group.position,)
            if group.other_position is None
            else (group.position, group.other_position)
        )
        for position in range(start, start + 4)
    }
    erased_by_position = {
        position: (before, after) for position, before, after in candidate.erased
    }
    erased_group_starts = {
        start
        for start in range(5, len(candidate.string) - 2, 4)
        if all(position in erased_by_position for position in range(start, start + 4))
    }
    erased_group_positions = {
        position
        for start in erased_group_starts
        for position in range(start, start + 4)
    }
    duplicated_group_positions = {
        position + offset
        for position, block in candidate.duplicated
        if len(block) == 4 and (position - 1) % 4 == 0
        for offset in range(4)
    }
    duplicated_positions = {
        position + offset
        for position, block in candidate.duplicated
        for offset in range(len(block))
    }
    character_duplications = sum(
        not (len(block) == 4 and (position - 1) % 4 == 0)
        for position, block in candidate.duplicated
    )
    group_counts = {
        "substitution": sum(group.kind == "erroneous" for group in candidate.groups),
        "erasure": len(erased_group_starts),
        "insertion": sum(group.kind == "omitted" for group in candidate.groups),
        "deletion": 0,
        "duplication": len(duplicated_group_positions) // 4,
        "transposition": sum(group.kind == "transposed" for group in candidate.groups),
    }
    character_counts = {
        "substitution": len(candidate.substituted),
        "erasure": len(candidate.erased) - len(erased_group_positions),
        "insertion": len(candidate.inserted) - group_counts["insertion"] * 4,
        "deletion": len(candidate.deleted) - len(duplicated_positions),
        "duplication": character_duplications,
        "transposition": len(candidate.transposed),
    }

    def summary(counts: dict[str, int]) -> str:
        return ", ".join(count(value, name) for name, value in counts.items() if value)

    character_summary = summary(character_counts)
    group_summary = summary(group_counts)
    details = [
        f"Search-space size: {candidate.search_space_bits:.2f} bits",
    ]
    if character_summary and group_summary:
        details.extend(
            (
                f"Symbol Edits: {character_summary}",
                f" Group Edits: {group_summary}",
            )
        )
    elif character_summary:
        details.append(f"Symbol Edits: {character_summary}")
    elif group_summary:
        details.append(f"Group Edits: {group_summary}")
    else:
        details.append("Edits: none")
    details.append("Corrected positions:")
    details.extend(
        f"  {position}: {before.upper()} → {after.upper()}"
        for position, before, after in candidate.substituted
        if position not in group_positions
    )
    details.extend(
        f"  {position}: {before.upper()} → {after.upper()}"
        for position, before, after in candidate.erased
        if position not in erased_group_positions
    )
    details.extend(
        f"  {start}-{start + 3}: erased group "
        f"{''.join(erased_by_position[position][0] for position in range(start, start + 4)).upper()}"
        " → "
        f"{''.join(erased_by_position[position][1] for position in range(start, start + 4)).upper()}"
        for start in sorted(erased_group_starts)
    )
    details.extend(
        f"  {position}: insert {character.upper()}"
        for position, character in candidate.inserted
        if position not in group_positions
    )
    details.extend(
        f"  {position}-{position + 1}: transpose " f"{before.upper()} → {after.upper()}"
        for position, before, after in candidate.transposed
    )
    for group in candidate.groups:
        end = group.position + 3
        if group.kind == "omitted":
            details.append(
                f"  {group.position}-{end}: insert omitted group "
                f"{group.after.upper()}"
            )
        elif group.kind == "transposed":
            assert group.other_position is not None
            other_end = group.other_position + 3
            details.append(
                f"  {group.position}-{end} ↔ "
                f"{group.other_position}-{other_end}: transpose groups "
                f"{group.before.upper()} → {group.after.upper()}"
            )
        else:
            details.append(
                f"  {group.position}-{end}: erroneous group "
                f"{group.before.upper()} → {group.after.upper()}"
            )
    details.extend(
        (
            f"  input {position}: delete duplicated "
            f"{'four-character group ' if len(block) == 4 and (position - 1) % 4 == 0 else ''}"
            f"{block.upper()}"
        )
        for position, block in candidate.duplicated
    )
    details.extend(
        f"  input {position}: delete {character.upper()}"
        for position, character in candidate.deleted
        if position not in duplicated_positions
    )
    if not candidate.edit_count:
        details.append("  None")
    corrected = parse_codex32(candidate.string)
    if isinstance(corrected, MasterSeed):
        label = (
            "Candidate Master Fingerprint"
            if candidate.edit_count
            else "Master Fingerprint"
        )
        formatted = _format_codex32_string(
            corrected,
            _master_node(corrected),
            candidate.changed_positions,
            label,
        )
    else:
        formatted = _format_transcription_string(corrected, candidate.changed_positions)
    sections = ["\n".join(details)]
    if candidate.inserted or candidate.deleted:
        sections.append(_format_correction_alignment(original, candidate.string))
    sections.append(formatted)
    return "\n\n".join(sections)


def _is_valid_master_seed_string(value: str) -> bool:
    """Return whether a checksum candidate satisfies the full ms profile."""
    return parse_codex32(value).profile is Profile.MS


def _pretty_enabled(ctx: click.Context, local_pretty: bool) -> bool:
    """Allow --pretty before or after a subcommand."""
    return local_pretty or bool(ctx.parent and ctx.parent.params.get("pretty"))


_MEMORY_LOCKED: bool | None = None


def _protect_secret_memory() -> None:
    """Best-effort protection against core dumps and swapped process memory."""
    global _MEMORY_LOCKED  # pylint: disable=global-statement
    if _MEMORY_LOCKED is not None:
        return
    try:
        import resource  # pylint: disable=import-outside-toplevel

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, OSError, ValueError):
        pass
    try:
        mlockall = ctypes.CDLL(None, use_errno=True).mlockall
        mlockall.argtypes = [ctypes.c_int]
        mlockall.restype = ctypes.c_int
        _MEMORY_LOCKED = mlockall(1 | 2) == 0  # MCL_CURRENT | MCL_FUTURE
    except (AttributeError, OSError):
        _MEMORY_LOCKED = False
    if not _MEMORY_LOCKED:
        click.echo(
            "Warning: Unable to lock process memory; secret material may be written "
            "to swap.",
            err=True,
        )


def _secret_strings_from_input() -> tuple[str, ...]:
    """Read visible terminal input or whitespace-delimited redirected input."""
    _protect_secret_memory()
    if sys.stdin.isatty():
        value = click.prompt(
            "codex32 string(s)",
            default="",
            show_default=False,
            hide_input=False,
        )
    else:
        value = sys.stdin.read()
    return tuple(value.split())


def _worksheet_data_from_input(header_supplied: bool) -> str:
    """Read the filled-in portion of a Book checksum worksheet."""
    _protect_secret_memory()
    if sys.stdin.isatty():
        value = click.prompt(
            (
                "Remaining non-pink bold squares"
                if header_supplied
                else "Checksum worksheet non-pink bold squares"
            ),
            default="",
            show_default=False,
            hide_input=False,
        )
    else:
        value = sys.stdin.read()
    return "".join(value.split())


def _worksheet_header_parts(value: str) -> tuple[str, str]:
    """Validate and split a worksheet prefix/header argument."""
    separator = value.rfind("1")
    if separator >= 0:
        prefix, header = value[: separator + 1], value[separator + 1 :]
        if prefix.lower() != "ms1":
            raise ValueError
    else:
        prefix, header = "", value
    _validate_worksheet_header(header)
    if value.upper() != value and value.lower() != value:
        raise ValueError
    return prefix, header


def _validate_worksheet_header(header: str) -> None:
    """Require a Book header for an unshared secret or canonical initial share."""
    lower_header = header.lower()
    if (
        len(header) != 6
        or (header.upper() != header and lower_header != header)
        or any(character not in CHARSET for character in lower_header)
        or lower_header[0] not in "023456789"
    ):
        raise ValueError
    threshold = int(lower_header[0])
    initial_indices = "s" if threshold == 0 else IDX_SORT[1 : threshold + 1]
    if lower_header[5] not in initial_indices:
        raise ValueError


def _worksheet_string(header_argument: str | None, entered: str) -> str:
    """Combine an optional public header argument with protected worksheet input."""
    if header_argument is None:
        separator = entered.rfind("1")
        if separator >= 0:
            prefix, body = entered[: separator + 1], entered[separator + 1 :]
        else:
            prefix, body = "", entered
        header, payload = body[:6], body[6:]
    else:
        prefix, header = _worksheet_header_parts(header_argument)
        payload = entered
    if len(header) != 6 or len(payload) != 26:
        raise ValueError
    _validate_worksheet_header(header)
    if not prefix:
        prefix = "MS1" if (header + payload).isupper() else "ms1"
    return prefix + header + payload


def _verified_strings_from_input() -> list[CodexArtifact]:
    """Read and validate one or more codex32 strings."""
    strings = _secret_strings_from_input()
    if not strings:
        raise click.BadParameter("Input must not be empty.", param_hint="stdin")
    try:
        return [parse_codex32(string) for string in strings]
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="stdin") from error


def _recovered_secret(shares: list[CodexArtifact]) -> Secret:
    """Return an input secret or recover one from an exact threshold set."""
    if len(shares) == 1:
        if not isinstance(shares[0], Secret):
            raise click.BadParameter(
                "A single share cannot recover a secret.", param_hint="stdin"
            )
        return shares[0]
    try:
        if not all(isinstance(share, Share) for share in shares):
            raise click.BadParameter(
                "Recovery requires only ordinary shares.", param_hint="stdin"
            )
        ordinary_shares = [share for share in shares if isinstance(share, Share)]
        return recover_secret(ordinary_shares)
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="stdin") from error


def _master_node(secret: Secret, testnet: bool = False) -> BIP32:
    """Construct a BIP32 master node from an ``ms`` codex32 secret."""
    if not isinstance(secret, MasterSeed):
        raise click.BadParameter(
            "The secret HRP must be 'ms' to derive wallet keys.",
            param_hint="stdin",
        )
    return BIP32.from_seed(secret.seed_bytes, "test" if testnet else "main")


@click.group()
@click.option(
    "--pretty",
    is_flag=True,
    help="Print string metadata and use visually distinct 4 character groups.",
)
@click.version_option(package_name="codex32", prog_name="codex32")
@click.help_option()
@click.pass_context
def cli(ctx: click.Context, pretty: bool) -> None:
    """codex32: BIP-0093 encode/decode/interpolate tools."""
    ctx.ensure_object(dict)
    del pretty


@cli.command(
    name="verify",
    help="Verify checksums and structure without deriving wallet keys.",
)
def verify() -> None:
    """Verify codex32 strings supplied through protected input."""
    for string in _verified_strings_from_input():
        kind = "secret" if isinstance(string, Secret) else "share"
        header_length = len(string.profile.value) + 7
        click.echo(f"Valid codex32 {kind} with header: {string.text[:header_length]}")


@cli.command(
    name="secret",
    help="Recover and print the codex32 secret at index S.",
)
@click.option(
    "--pretty",
    is_flag=True,
    help="Print metadata and visually distinct four-character groups.",
)
@click.pass_context
def secret_command(ctx: click.Context, pretty: bool) -> None:
    """Recover a codex32 secret from protected input."""
    secret = _recovered_secret(_verified_strings_from_input())
    if _pretty_enabled(ctx, pretty):
        if isinstance(secret, MasterSeed):
            click.echo(_format_codex32_string(secret, _master_node(secret)))
        else:
            click.echo(_format_transcription_string(secret))
    else:
        click.echo(secret)


@cli.command(
    name="share",
    help="Derive and print a codex32 share at INDEX.",
)
@click.argument("index")
@click.option(
    "--pretty",
    is_flag=True,
    help="Print metadata and visually distinct four-character groups.",
)
@click.pass_context
def share_command(ctx: click.Context, index: str, pretty: bool) -> None:
    """Derive one codex32 share from an exact threshold set."""
    if len(index) != 1 or index.lower() not in CHARSET:
        raise click.BadParameter(
            "Index must be one Bech32 character.", param_hint="INDEX"
        )
    if index.lower() == "s":
        raise click.BadParameter(
            "Use the secret command to recover index S.", param_hint="INDEX"
        )
    shares = _verified_strings_from_input()
    try:
        if shares[0].profile in (Profile.BIP39_12W, Profile.BIP39_24W):
            raise click.BadParameter(
                "BIP39 share derivation is not exposed by the CLI.",
                param_hint="stdin",
            )
        derived = derive_share(shares, index)
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="stdin") from error
    if _pretty_enabled(ctx, pretty):
        secret = next(
            (artifact for artifact in shares if isinstance(artifact, Secret)), None
        ) or _recovered_secret(shares)
        if isinstance(secret, MasterSeed):
            click.echo(_format_codex32_string(derived, _master_node(secret)))
        else:
            click.echo(_format_transcription_string(derived))
    else:
        click.echo(derived)


@cli.command(
    name="xprv",
    help="Recover and print the BIP32 master extended private key.",
)
@click.option(
    "--testnet",
    is_flag=True,
    help="Use testnet extended-key version bytes.",
)
def xprv(testnet: bool) -> None:
    """Print the master extended private key for protected input."""
    secret = _recovered_secret(_verified_strings_from_input())
    click.echo(_master_node(secret, testnet).get_xpriv())


@cli.command(
    name="descriptors",
    help="Recover and print Bitcoin Core descriptor-import JSON.",
)
@click.option(
    "--testnet",
    is_flag=True,
    help="Use testnet version bytes and BIP44 coin type.",
)
@click.option(
    "--account",
    type=int,
    help="Increment per new wallet joined to prevent key reuse.",
)
@click.option(
    "--private",
    is_flag=True,
    help="Include private keys in descriptors.",
)
def descriptors(testnet: bool, account: int | None, private: bool) -> None:
    """Print descriptors for a recovered BIP32 master seed."""
    secret = _recovered_secret(_verified_strings_from_input())
    node = _master_node(secret, testnet)
    path = "{}/<44h;49h;84h;86h>/{}h/{}h"
    _, account = next_account_for(node, path, account)
    click.echo(
        json.dumps(
            descriptors_from_node(
                node,
                DESCRIPTOR_TEMPLATES,
                account,
                private,
                timestamp="now",
            )
        )
    )


@cli.command(
    name="correct",
    short_help="Correct a damaged string or worksheet residue.",
)
@click.option(
    "--residue",
    "residue_mode",
    is_flag=True,
    help="Correct a final 13- or 15-symbol checksum worksheet residue.",
)
@click.option(
    "--erasure",
    "-e",
    "erasure_positions",
    type=click.IntRange(min=1),
    multiple=True,
    help="One-based reverse position for residue mode; 1 is the final symbol.",
)
@click.option(
    "--pretty",
    is_flag=True,
    help="Group output and highlight corrected characters.",
)
@click.option(
    "--search-seconds",
    type=click.FloatRange(min=0, max=10, min_open=True),
    default=10.0,
    show_default=True,
    help="Maximum insertion/deletion brute-force search time.",
)
@click.pass_context
def correct(
    ctx: click.Context,
    residue_mode: bool,
    erasure_positions: tuple[int, ...],
    pretty: bool,
    search_seconds: float,
) -> None:
    """Correct a damaged string, or interpret a Book worksheet residue.

    With no options, read one damaged codex32 string from protected input. Use
    ``?`` for each unreadable character while preserving its position.
    Insertions and deletions after the fixed ``ms1`` prefix are searched for up
    to ``--search-seconds`` while checksum correction handles substitutions.

    With ``--residue``, read only the final checksum residue and print
    reverse-indexed corrections for the addition wheel. The codex32 string,
    its profile, and its length are not disclosed to this process.

    A checksum-valid correction is only a suggestion. Compare every legible
    character and every reported edit against the physical backup. Do not pipe
    correction output directly into recovery or wallet-import commands.
    """
    _protect_secret_memory()
    prompt = (
        "Final checksum worksheet residue"
        if residue_mode
        else "Damaged codex32 string (? for each unreadable character)"
    )
    value = (
        click.prompt(prompt, hide_input=False)
        if sys.stdin.isatty()
        else sys.stdin.read()
    )
    value = "".join(value.split())
    if not value:
        raise click.BadParameter("Input must not be empty.", param_hint="stdin")

    try:
        if not residue_mode:
            if erasure_positions:
                raise click.UsageError("--erasure requires --residue")
            result = search_codex32_corrections(
                value,
                max_seconds=search_seconds,
                validator=_is_valid_master_seed_string,
            )
            candidate = result.candidate
            if candidate is None:
                raise click.ClickException("Too many errors; unable to correct string.")
            if result.timed_out:
                click.echo(
                    "Warning: Search time expired; showing the best candidate "
                    "found, which may not be the global minimum.",
                    err=True,
                )
            if candidate.edit_count:
                click.echo(
                    "Warning: A checksum-valid correction is only a suggestion. "
                    "Compare every legible character and every reported edit "
                    "against the physical backup. Do not pipe correction output "
                    "directly into recovery or wallet-import commands.",
                    err=True,
                )
            use_pretty = _pretty_enabled(ctx, pretty)
            if (candidate.inserted or candidate.deleted) and not use_pretty:
                click.echo(
                    _format_correction_alignment(value, candidate.string),
                    err=True,
                )
            if use_pretty:
                click.echo(_format_corrected_string(value, candidate))
            else:
                click.echo(candidate.string)
            return

        corrections = correct_worksheet_residue(
            value,
            erasure_indices=tuple(
                position - 1 for position in erasure_positions
            ),
        )
    except InvalidCorrectionInput as error:
        if not residue_mode:
            raise click.BadParameter(str(error), param_hint="stdin") from error
        raise click.UsageError(str(error)) from error
    except CodexError as error:
        raise click.ClickException(
            "The corrected checksum does not form a valid codex32 master-seed string."
        ) from error

    if corrections is None:
        raise click.ClickException("Too many errors; unable to determine corrections.")
    if not corrections:
        click.echo("No errors found. Residue is correct.")
        return
    noun = "error" if len(corrections) == 1 else "errors"
    click.echo(f"{len(corrections)} {noun} found. Make the following corrections.")
    for correction in corrections:
        click.echo(
            f"Add {correction.addend} to reverse position "
            f"{correction.reverse_index + 1}."
        )


@cli.command(
    name="checksum",
    short_help="Complete a Book checksum worksheet.",
    help="Complete a Book checksum worksheet using its non-pink bold squares.",
)
@click.option(
    "--pretty",
    is_flag=True,
    help="Print metadata and visually distinct four-character groups.",
)
@click.argument("header", required=False)
@click.pass_context
def checksum(
    ctx: click.Context,
    pretty: bool,
    header: str | None,
) -> None:
    """Complete a Book checksum worksheet."""
    invalid = (
        "The input does not match the expected format of the non-pink bold "
        "squares.\nConsult the Book and check the worksheet."
    )
    try:
        if header is not None:
            _worksheet_header_parts(header)
    except ValueError as error:
        raise click.ClickException(invalid) from error
    _protect_secret_memory()
    input_instruction = (
        "Enter the header first, then only" if header is None else "Enter only"
    )
    click.echo(
        f"{click.style('DANGER', fg='red', bold=True)}: Incorrect input can make "
        "the wallet predictable and cause "
        f"permanent loss of funds. {input_instruction} characters generated by "
        "following the codex32 dice-debiasing worksheet exactly. Do not enter raw "
        "dice rolls, seed words, hexadecimal seeds, passwords, or anything else.",
        err=True,
    )
    entered = _worksheet_data_from_input(header is not None)
    invalid = (
        "The input does not match the expected format of the filled-out non-pink "
        "bold squares.\nConsult the Book and check the worksheet."
    )
    if not entered:
        raise click.ClickException(invalid)
    try:
        worksheet_data = _worksheet_string(header, entered)
        if worksheet_data[worksheet_data.rfind("1") + 1] not in "023456789":
            raise ValueError
        string = complete_checksum(worksheet_data)
    except (CodexError, ValueError) as error:
        raise click.ClickException(invalid) from error
    if not _pretty_enabled(ctx, pretty):
        click.echo(string)
    elif isinstance(string, MasterSeed):
        click.echo(_format_codex32_string(string, _master_node(string)))
    else:
        click.echo(_format_transcription_string(string))


@cli.command(
    name="create",
    help="Create new codex32 backup set.",
)
@click.option(
    "--prefix",
    type=click.Choice(("ms", "cl"), case_sensitive=False),
    default="ms",
    show_default=True,
    help="Select the registered codex32 application prefix.",
)
@click.option(
    "--threshold",
    type=click.IntRange(0, 9),
    default=2,
    show_default=True,
    help="Use 0 for an unshared secret, or 2 through 9 for shares.",
)
@click.option(
    "--identifier",
    type=str,
    help="Four-character identifier to override the wallet/set-derived default.",
)
@click.option(
    "--bytes",
    "byte_length",
    type=click.IntRange(16, 64),
    help="Fresh ms seed length in bytes (default 16); cl is fixed at 32.",
)
@click.option(
    "--shares",
    type=click.IntRange(1, len(IDX_SORT) - 1),
    help="Number of randomly indexed shares (default 5 for shared output).",
)
@click.option(
    "--indices",
    type=str,
    help="Exact ordered share indices, for example 7cad.",
)
@click.option(
    "--pretty",
    is_flag=True,
    help="Print metadata and visually distinct four-character groups.",
)
@click.pass_context
def create(
    ctx: click.Context,
    prefix: str,
    threshold: int,
    identifier: str | None,
    byte_length: int | None,
    shares: int | None,
    indices: str | None,
    pretty: bool,
) -> None:
    """Create new codex32 backup set."""
    _protect_secret_memory()
    if threshold == 1:
        raise click.BadParameter(
            "Threshold must be 0 for an unshared secret, or 2 through 9.",
            param_hint="--threshold",
        )
    if shares is not None and indices is not None:
        raise click.UsageError("--shares and --indices are mutually exclusive.")
    if threshold == 0 and (shares is not None or indices is not None):
        raise click.UsageError(
            "An unshared secret cannot be combined with --shares or --indices."
        )
    if threshold != 0 and shares is None and indices is None:
        shares = 5
    if shares is not None and threshold > shares:
        raise click.BadParameter(
            "Threshold cannot exceed the number of shares.",
            param_hint="--shares",
        )

    click.echo(
        "Warning: Do not enter BIP39 mnemonic words or BIP39 entropy. "
        "Standard input accepts only raw hexadecimal secret bytes "
        "or an existing codex32 secret.",
        err=True,
    )
    identifier = _validated_identifier(identifier)
    source = _creation_source_from_stdin(prefix)
    if prefix == "cl":
        raise click.UsageError(
            "Fresh cl secrets are not generated; current Core Lightning uses mnemonics."
        )
    if source is not None and byte_length is not None:
        raise click.UsageError("--bytes applies only when generating a fresh secret.")
    if isinstance(source, MasterSeed) and threshold == 0:
        raise click.UsageError(
            "An existing codex32 secret is already complete; create can only "
            "split it at threshold 2 through 9."
        )
    if isinstance(source, MasterSeed) and identifier is None:
        raise click.BadParameter(
            "Re-sharing a secret requires a new explicit identifier.",
            param_hint="--identifier",
        )
    if isinstance(source, bytes) and prefix == "ms" and identifier is None:
        raise click.BadParameter(
            "Raw hexadecimal seeds require an explicit identifier.",
            param_hint="--identifier",
        )

    try:
        if isinstance(source, MasterSeed):
            assert identifier is not None
            secret, generated_shares = split_secret(
                source,
                threshold,
                share_count=shares,
                indices=indices,
                identifier=identifier,
            )
        elif prefix == "ms":
            seed_bytes = source if isinstance(source, bytes) else None
            secret, generated_shares = generate_master_seed(
                seed_bytes,
                byte_length=byte_length,
                threshold=threshold,
                share_count=shares,
                indices=indices,
                identifier=identifier,
            )
    except HeaderCollision as error:
        raise click.ClickException(
            f"{error} Choose another --identifier."
        ) from error
    except CodexError as error:
        raise click.ClickException(str(error)) from error

    strings: tuple[CodexArtifact, ...] = (
        (secret,) if threshold == 0 else generated_shares
    )
    if identifier is None:
        click.echo(
            f"Generated identifier: {secret.header.identifier}",
            err=True,
        )

    click.echo(
        "Warning: Keep the wallet's derivation paths, script policy, and descriptors; "
        "the seed alone may not fully restore the wallet.",
        err=True,
    )
    click.echo(
        "Warning: After independently verifying every recorded share, securely "
        "destroy any dice-debiasing, checksum, or other generation worksheets.",
        err=True,
    )
    pretty = _pretty_enabled(ctx, pretty)
    for string in strings:
        if not pretty:
            click.echo(string)
        elif isinstance(secret, MasterSeed):
            click.echo(_format_codex32_string(string, _master_node(secret)))
        else:
            click.echo(_format_transcription_string(string))


def _validated_identifier(identifier: str | None) -> str | None:
    """Normalize and validate a user-provided codex32 identifier."""
    if identifier is None:
        return None
    identifier = identifier.lower()
    if len(identifier) != 4 or any(char not in CHARSET for char in identifier):
        raise click.BadParameter(
            "Identifier must contain exactly four bech32 characters.",
            param_hint="--identifier",
        )
    return identifier


def _creation_source_from_stdin(
    prefix: str,
) -> bytes | MasterSeed | CoreLightningSecret | None:
    """Read at most one profile-matching secret or hexadecimal byte string."""
    if not (entered := _piped_input()):
        return None
    values = entered.split()
    if len(values) != 1:
        raise click.BadParameter(
            "Create accepts exactly one secret or hexadecimal seed; ordinary "
            "shares and partial bases are unsupported.",
            param_hint="stdin",
        )
    value = values[0]
    try:
        source = parse_codex32(value)
        if isinstance(source, Share):
            raise click.BadParameter(
                "Create accepts a secret, not an ordinary share; partial-basis "
                "generation is unsupported.",
                param_hint="stdin",
            )
        if source.profile in (Profile.BIP39_12W, Profile.BIP39_24W):
            raise click.BadParameter(
                "BIP39 generation and splitting are not supported.",
                param_hint="stdin",
            )
        if source.profile.value != prefix:
            raise click.BadParameter(
                f"Input profile {source.profile.value!r} does not match "
                f"--prefix {prefix!r}.",
                param_hint="stdin",
            )
        if not isinstance(source, (MasterSeed, CoreLightningSecret)):
            raise click.BadParameter(
                "Input must be an ms or cl secret.", param_hint="stdin"
            )
        return source
    except CodexError as codex_error:
        try:
            data = bytes.fromhex(value)
        except ValueError as hex_error:
            raise click.BadParameter(
                "Seed must be hexadecimal bytes or a valid codex32 string.",
                param_hint="stdin",
            ) from hex_error
        valid_length = 16 <= len(data) <= 64 if prefix == "ms" else len(data) == 32
        if not valid_length:
            expected = "16 to 64 bytes" if prefix == "ms" else "exactly 32 bytes"
            raise click.BadParameter(
                f"Raw {prefix} secret must be {expected}.",
                param_hint="stdin",
            ) from codex_error
        return data


def no_empty_param(name: str, val, msg="Must not be empty."):
    """Raise BadParameter if val is empty."""
    if not val:
        raise click.BadParameter(msg, param_hint=name)


def _piped_input() -> str:
    """Read redirected standard input, or return an empty string on a TTY."""
    return "" if sys.stdin.isatty() else sys.stdin.read().strip()


base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
DB_PATH = base / "codex32"


def _load_db(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r+") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise TypeError("codex32 account database must contain a JSON object")
    return loaded


def _save_db(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def next_account_for(node: BIP32, path: str, account: None | int) -> tuple[str, int]:
    """
    key_origin_info: stable identifier per seed
    returns next account index (and increments it atomically)
    """
    fingerprint = node.get_fingerprint().hex()
    coin_type = int(node.network != "main")
    key_origin = f"[{path.format(fingerprint, coin_type, '{account}')}]"

    db = _load_db(DB_PATH / "accounts.json")
    n = int(db.get(key_origin, 0))
    db[key_origin] = n + 1
    if account is None or account == n:
        _save_db(DB_PATH / "accounts.json", db)
    elif account not in range(n):
        raise click.BadParameter(
            f"{key_origin} accounts are numbered from index `0` to `{n}` in sequentially increasing manner.",
            param_hint="--account",
        )
    account = n if account is None else account
    return path.format("m", coin_type, account), account


if __name__ == "__main__":
    cli()
