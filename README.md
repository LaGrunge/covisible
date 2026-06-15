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

Covisible is a command group. The main command is `report`; `diff`, `files`,
and `summary` are console-only helpers. Coverage input is auto-detected: `.json`
(and `*.gcov.json`) is parsed as gcov JSON, everything else as LCOV `.info`.

### Generate a report (PR coverage)

```bash
covisible report \
  --current coverage.info \
  --baseline baseline.info \
  --git-diff HEAD~1..HEAD \
  --output report/ \
  --format both
```

Without `--git-diff`/`--diff-file` you get a whole-project report; with one of
them the report focuses on new/modified lines.

To render the actual source code, covisible locates each file by the path
recorded in the coverage data, then by `--source-root` — joining relative paths
and matching absolute build paths by their longest existing suffix (so a foreign
build prefix like `/home/ci/build/...` still resolves). Files it cannot find are
rendered with coverage but no code, and the run prints how many were missing.

### Generate gcov JSON coverage

```bash
# After running tests with coverage enabled
find . -name "*.gcno" -exec gcov --json-format {} \;
# Or use gcov on specific files
gcov --json-format --stdout myfile.cpp > coverage.json
```

### `report` options

| Option | Description |
|--------|-------------|
| `-c, --current` | Current coverage file (gcov JSON or lcov.info) — **required** |
| `-b, --baseline` | Baseline coverage for comparison (optional) |
| `--git-diff` | Git diff range (e.g., `main..HEAD`) |
| `--diff-file` | Path to unified diff file |
| `-o, --output` | Output directory for HTML report (default: `coverage-report/`) |
| `--format` | Output format: `html`, `json`, or `both` (default: `html`) |
| `--repo` | Path to git repository (for `--git-diff` / title) |
| `--source-root` | Directory where the source files live, used to render code when coverage paths are absolute build paths or relative to another root (defaults to `--repo`) |
| `--title` | Report title (default: `Covisible: <project>`) |
| `--blame / --no-blame` | Include git blame analysis for uncovered code |
| `--exclude GLOB` | Glob of files to exclude (repeatable, e.g. `--exclude '*_test.cpp'`) |
| `--ignore-config` | Path to an ignore config (YAML/JSON) with `exclude`/`include`/`line_markers` |

### Other commands

```bash
# CodeCov-style coverage diff (console), optional markdown brief for CI comments
covisible diff coverage_new.info -b coverage_old.info --markdown brief.md

# List files by coverage
covisible files coverage.info --sort uncovered --limit 20

# One-file summary
covisible summary coverage.info
```

### Excluding files and lines

Pass `--exclude` one or more times, or point `--ignore-config` at a YAML/JSON
file:

```yaml
# covisible-ignore.yaml
ignore:
  exclude:
    - "*_test.cpp"
    - "third_party/*"
  line_markers:
    - "// LCOV_EXCL_LINE"
    - "# pragma: no cover"
```

Excluded files are dropped from the report; lines matched by a marker (or a
`LCOV_EXCL_START`/`STOP` block) are removed from their file's coverage.

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
