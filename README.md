# Covisible

**PR-first code coverage report generator with modern UI**

Covisible generates beautiful, interactive coverage reports focused on what matters: **your PR changes**.

## Features

- **PR-first view** — Shows coverage for new/modified lines, not the entire repo
- **Diff-based analysis** — Integrates with git diff to highlight what changed
- **Modern UI** — Dark/light theme, interactive charts, instant search
- **Smart summary** — "−1.3% coverage, 3 new uncovered lines" instead of "83.42%"
- **1-click drill-down** — PR → file → function → line
- **Baseline comparison** — Compare current coverage with previous runs

## Installation

```bash
pip install covisible
```

Or install from source:

```bash
git clone https://github.com/LaGrunge/covisible
cd covisible
pip install -e ".[dev]"
```

## Usage

### Basic usage (PR coverage)

```bash
covisible \
  --current coverage.json \
  --baseline baseline.json \
  --git-diff HEAD~1..HEAD \
  --output report/
```

### Generate gcov JSON coverage

```bash
# After running tests with coverage enabled
find . -name "*.gcno" -exec gcov --json-format {} \;
# Or use gcov on specific files
gcov --json-format --stdout myfile.cpp > coverage.json
```

### Options

| Option | Description |
|--------|-------------|
| `--current` | Current coverage file (gcov JSON or lcov.info) |
| `--baseline` | Baseline coverage for comparison (optional) |
| `--git-diff` | Git diff range (e.g., `main..HEAD`) |
| `--diff-file` | Path to unified diff file |
| `--output` | Output directory for HTML report |
| `--format` | Output format: `html`, `json`, or `both` |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src tests
mypy src
```

## License

MIT
