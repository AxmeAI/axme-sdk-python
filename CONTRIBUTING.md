# Contributing to the AXME Python SDK

Thank you for your interest in contributing. Every bug fix, test, and
improvement helps the entire AXME ecosystem.

AXME is in alpha -- breaking changes may occur. We especially welcome feedback
on API ergonomics.

## Ways to Contribute

- Fix bugs and improve error messages
- Add missing API methods
- Improve type hints and docstrings
- Add test coverage

## Reporting Bugs

Open a GitHub Issue at <https://github.com/AxmeAI/axme-sdk-python/issues>.
Include:

- SDK version and Python version
- Minimal code to reproduce the problem
- Full traceback or error output

## Proposing Changes

1. Fork the repository.
2. Create a branch from `main` (e.g., `fix/improve-error-message`).
3. Make your changes.
4. Run tests and linters (see below).
5. Open a pull request against `main` with a clear description.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Code Style

This project uses **black** for formatting and **ruff** for linting.

```bash
black .
ruff check .
```

All code must include type hints. Public functions and classes must have
docstrings.

## Running Tests

```bash
pytest
```

Tests should pass before you open a PR. If you are adding a new feature or
fixing a bug, add a test that covers the change.

## Code of Conduct

Be respectful and constructive. We value clear communication and good-faith
collaboration.

## Contact

Questions or feedback: hello@axme.ai
