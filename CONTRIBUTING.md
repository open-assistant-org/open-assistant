# Contributing to Open Assistant

Thanks for your interest in contributing! This document explains how to report
issues, propose changes, and submit pull requests.

## Code of Conduct

Be respectful and constructive. We want Open Assistant to be a welcoming
project for contributors of all backgrounds and experience levels.

## Ways to Contribute

- **Report bugs** — open an issue describing what happened, what you expected,
  and how to reproduce it.
- **Suggest features** — open an issue outlining the use case and proposed
  behavior before writing code, so we can align on the approach.
- **Improve documentation** — fixes to the guides under `docs/` are always
  welcome.
- **Submit code** — bug fixes, new integrations, and enhancements via pull
  request.

## Reporting Issues

Before opening a new issue, please search existing issues to avoid duplicates.
A good bug report includes:

- A clear, descriptive title.
- Steps to reproduce, including relevant configuration (with secrets redacted).
- Expected vs. actual behavior.
- Environment details (OS, Python version, deployment method).
- Logs or stack traces where applicable.

## Development Setup

The project targets **Python 3.11+** and uses [uv](https://docs.astral.sh/uv/)
for dependency management.

```bash
# Clone your fork
git clone https://github.com/<your-username>/open-assistant
cd open-assistant

# Install dependencies (including dev extras)
uv sync --all-extras --dev

# Copy the example environment file and fill in your values
cp .env.example .env
```

See [`docs/setup/development.md`](docs/setup/development.md) for the full
development environment guide, and [`docs/setup/configuration.md`](docs/setup/configuration.md)
for configuration details.

## Making Changes

1. Create a branch off `main` for your work:
   ```bash
   git checkout -b fix/short-description
   ```
2. Make your changes, keeping commits focused and descriptive.
3. Add or update tests for any behavior you change.
4. Update the relevant documentation under `docs/` — this project values
   keeping docs in sync with the code.

## Code Style and Quality

CI runs the same checks locally available through `uv`. Before pushing, make
sure the following pass:

```bash
# Format check (CI runs `black --check .`)
uv run black .

# Lint
uv run ruff check .

# Type check
uv run mypy src

# Tests with coverage
uv run pytest --cov=src
```

Tooling configuration (line length, lint rules, test settings) lives in
[`pyproject.toml`](pyproject.toml).

## Submitting a Pull Request

1. Push your branch to your fork and open a pull request against `main`.
2. Fill in a clear description of **what** changed and **why**. Link any
   related issues (e.g. `Closes #123`).
3. Ensure CI is green — pull requests run formatting checks and the test
   suite automatically.
4. Be responsive to review feedback; maintainers may request changes before
   merging.

Keep pull requests focused on a single concern where possible — smaller PRs are
easier to review and merge.

## License

By contributing, you agree that your contributions will be licensed under the
project's [Business Source License 1.1](LICENSE).
