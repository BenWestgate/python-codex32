# Repository Guidelines

## Project Structure & Module Organization

Production code lives in `src/codex32/`; keep its modules narrow. Do not duplicate domain logic in `cli.py` or `profiles/`. Tests are in `tests/test_*.py`, with frozen external vectors under `tests/data/`. Durable documentation is grouped under `docs/user/`, `docs/developer/`, and `docs/security/`. Local plans and unfinished gate reports belong in the ignored `docs/planning/` directory. `tools/` contains offline verification utilities.

## Build, Test, and Development Commands

```bash
python -m pip install -e '.[dev]'  # editable install with review tools
python -m pytest -q                # complete test suite
python -O -m pytest -q             # verify behavior without assertions
python -m ruff check .             # lint source and tests
python -m ruff format --check .    # verify formatting
python -m mypy src/codex32         # strict type checking
python -m build                    # build wheel and source archive
python -m twine check dist/*       # validate release metadata
```

Run the local CLI with `codex32 --help`. Python 3.12 is the minimum; CI also covers 3.13.

## Coding Style & Naming Conventions

- Use 4 space indentation
- The line limit for Python code is 79 characters, while comments and docstrings must be wrapped at 72 characters. However, lines up to 99 characters may be used where they improve readability and reduce line count. Definitions should use lines up to 99 characters when it reduces line count.

- Easy to match operators with operands

- Surround top-level function and class definitions with 2 blank lines
- Method definitions inside a class are surrounded by 1 blank line
- Extra blank lines may be used (sparingly) to separate groups of related functions
- Blank lines may be omitted between a bunch of related one-liners (e.g. a set of dummy implementations)
- Use blank lines in functions, sparingly, to indicate logical sections

- Prefer f-strings over `str.format()` or `%` formatting

- Comments that contradict the code are worse than no comments. Always make a priority of keeping the comments up-to-date when the code changes!
- Comments should be complete sentences. The first word should be capitalized, unless it is an identifier that begins with a lower case letter (never alter the case of identifiers!).
- Ensure that your comments are clear and easily understandable to English speakers.
- Use inline comments sparingly.
- An inline comment is a comment on the same line as a statement. Inline comments should be separated by at least two spaces from the statement. They should start with a # and a single space.
- Inline comments are unnecessary and in fact distracting if they state the obvious.
- Write one liner docstrings for all public modules, functions, classes, and methods. Docstrings are not necessary for non-public methods, but you should have a comment that describes what the method does. This comment should appear after the def line.

- Names that are visible to the user as public parts of the API should follow conventions that reflect usage rather than implementation.

- Use type hints, no wildcard imports
- Embrace idiomatic Python like comprehensions, generators, and decorators
- If more than one name from a module is needed, use lexicographically sorted multi-line imports in order to reduce the possibility of potential merge conflicts

Use a python linter like Ruff/flake8/Black before submitting to catch common style nits (eg trailing whitespace, unused imports, etc)
Mypy is strict; keep ignores for untyped dependency by its references. Use `snake_case` for functions and modules, `CapWords` for types, `UPPER_CASE` for constants. Optimize for human readability.

In text codex32 is always lowercase unless it refers to the Codex32 Book.

## Constraints

- Ask before adding any external dependency.
- Ask before changing the signature and response shape of existing endpoints
- Ask before suppressing format or style lints.
- Tests enforce an installed-package budget below 3,000 logical lines of code.
- Declare a task done only after the gates pass and docstrings are updated

## Testing Guidelines

Use pytest and Hypothesis. Name tests `test_<behavior>` and give test modules an evidence-focused docstring. Add normative vectors, negative cases, and regressions with behavioral changes. Never derive expected fixtures from production code, weaken assertions, or add skips to pass. Do not use real seeds or funded-wallet data. Do not test the correction if the change could not affect it.

## Security

For security-sensitive or boundary changes, first read the mandatory
`docs/security/invariants.md` contract. Then inspect the specification-to-code
map in `docs/developer/api.md` and only the relevant sections of
`docs/security/model.md`. Read the complete security model when changing the
threat model, security guarantees, release posture, or multiple interacting
boundaries.

Do not automatically run security-diff during intermediate implementation;
run it once on stable security-sensitive diffs. If unsure, stop and ask first.

## Agent Instructions

Agents may edit, test and commit locally, but must not commit/push to master, push to open pull request branches, open pull requests, post maintainer comments, or claim authorship. A human publishes every contribution.

Commit atomic commits that pass independently. Do not mix formatting, code moves, and behavior. Use an imperative subject of at most 50 characters, then a blank line and paragraphs explaining rationale and security implications. Use `refs #123` or `fixes #123` when applicable. Pull requests need a clear use case, relevant test results, documentation updates, and focused peer review; include before/after CLI transcripts when useful.
