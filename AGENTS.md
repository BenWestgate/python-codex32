# Repository Guidelines

## Project Structure & Module Organization

Production code lives in `src/codex32/`; keep its codec, profile, artifact, generation, correction, wallet, and CLI modules narrow. Do not duplicate domain logic in `cli.py`. Tests are in `tests/test_*.py`, with frozen external vectors under `tests/data/`. Architecture, provenance, and user guidance live in `docs/`. `tools/` contains offline verification utilities.

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

Run the local CLI with `codex32 --help`. Python 3.12 is the minimum; CI also covers 3.13 and 3.14.

## Coding Style & Naming Conventions

Use four-space indentation and PEP 8. Ruff is the only linter and formatter. Mypy is strict; keep untyped dependency interaction inside its narrow adapter. Use `snake_case` for functions and modules, `CapWords` for types, `UPPER_CASE` for constants, and leading underscores for private helpers. Prefer small functions and immutable typed values. Optimize for human review.

## Testing Guidelines

Use pytest and Hypothesis. Name tests `test_<behavior>` and give test modules an evidence-focused docstring. Add normative vectors, negative cases, and regressions with behavioral changes. Never derive expected fixtures from production code, weaken assertions, or add skips to pass. Do not use real seeds or funded-wallet data. Tests enforce an installed-package budget below 3,000 lines.

## Security and Agent Instructions

Read `SECURITY.md`, `docs/architecture.md`, and `docs/AI_POLICY.md` before security work. Preserve validated-artifact boundaries, symbol-only shares, OS-backed entropy, and stdout/stderr separation. Agents may edit and test locally, but must not push, open pull requests, post maintainer comments, or claim authorship. A human publishes every contribution.

## Commit & Pull Request Guidelines

Make atomic commits that pass independently. Do not mix formatting, code moves, and behavior. Use an imperative subject of at most 50 characters, then a blank line and paragraphs explaining rationale and security implications. Use `refs #123` or `fixes #123` when applicable. Pull requests need a clear use case, relevant test results, documentation updates, and focused peer review; include before/after CLI transcripts when useful.
