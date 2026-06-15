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

<img width="2379" height="798" alt="image" src="https://github.com/user-attachments/assets/bbba7bfe-a639-43a7-883b-a479683b4c73" />


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
| `-c, --current` | Coverage file (gcov JSON or lcov.info) — **required**. Repeatable: pass `-c` several times to merge shards/test runs (hit counts are summed) |
| `-b, --baseline` | Baseline coverage for comparison (optional) |
| `--git-diff` | Git diff range (e.g., `main..HEAD`) |
| `--diff-file` | Path to unified diff file |
| `-o, --output` | Output directory for HTML report (default: `coverage-report/`) |
| `--format` | Output format: `html`, `json`, or `both` (default: `html`) |
| `--config FILE` | Read option defaults from a TOML file (default: `./.covisible.toml` if present). CLI flags override the file |
| `--repo` | Path to git repository (for `--git-diff` / title) |
| `--source-root` | Directory where the source files live, used to render code when coverage paths are absolute build paths or relative to another root (defaults to `--repo`) |
| `--title` | Report title (default: `Covisible: <project>`) |
| `--blame / --no-blame` | Include git blame analysis for uncovered code |
| `--branches / --no-branches` | Show branch coverage columns in the report (off by default; only rendered when the coverage data has branch info) |
| `--range LOW,HIGH` | Coverage color thresholds as percentages: below `LOW` is red, `LOW`–`HIGH` yellow, at or above `HIGH` green (default: `50,80`). Applies to the summary cards, module-table bars, sunburst and treemap |
| `--precision N` | Decimal places shown for coverage percentages everywhere (default: `1`) |
| `--badge FILE` | Also write a shields-style SVG coverage badge to `FILE`: rounded line-coverage %, colored by `--range`, with the covisible eye logo |
| `--cobertura FILE` | Also write a Cobertura XML report to `FILE` for CI tools (Jenkins, GitLab, Azure DevOps, SonarQube) |
| `--history FILE` | Append this run to a JSON history file and render a coverage trend chart (commit it / cache it in CI to accumulate history) |
| `--commit SHA` | Commit label for the `--history` entry (default: auto-detected from `--repo`) |
| `--branch NAME` | Branch label for the `--history` entry (default: auto-detected from `--repo`; distinct from `--branches`) |
| `--trend / --no-trend` | Render the coverage trend chart from `--history` data (default on). `--no-trend` keeps recording history but hides the chart |
| `--fail-under PCT` | Exit with status 1 if overall line coverage is below `PCT` (the report is still written) |
| `--fail-under-new PCT` | Exit with status 1 if coverage of new/changed lines is below `PCT` (PR mode only) |
| `--exclude GLOB` | Glob of files to exclude (repeatable, e.g. `--exclude '*_test.cpp'`) |
| `--include GLOB` | Keep only files matching this glob, applied after `--exclude` (repeatable) |
| `--omit-lines REGEXP` | Ignore source lines matching this regex, e.g. `--omit-lines 'assert'` (needs source on disk; repeatable) |
| `--substitute s/RE/REPL/` | Rewrite coverage file paths with a sed-style regex so they match source on disk, e.g. `--substitute 's#/build/##'` (repeatable) |
| `--prefix PREFIX` | Strip a leading path `PREFIX` from coverage file paths |
| `--strip N` | Strip the first `N` leading directory levels from coverage file paths |
| `--ignore-config` | Path to an ignore config (YAML/JSON) with `exclude`/`include`/`line_markers` |

The report ships a light/dark theme that follows the OS `prefers-color-scheme`
by default, with a header toggle (or press `t`) that persists your choice.

### Config file

Put commonly-used options in `.covisible.toml` (auto-discovered in the current
directory, or point at one with `--config`). CLI flags always override it:

```toml
[report]
range = "50,75"
precision = 2
branches = true
exclude = ["*_test.cpp", "third_party/*"]
fail_under = 80
fail_under_new = 90
badge = "coverage.svg"
cobertura = "coverage.xml"
```

### CI gating

Merge shards, fail the build under a threshold, and emit artifacts CI can ingest:

```bash
covisible report -c shard1.info -c shard2.info -o report/ \
  --git-diff origin/main..HEAD --repo . \
  --fail-under 80 --fail-under-new 90 \
  --cobertura coverage.xml --badge coverage.svg --history history.json
```

### Other commands

```bash
# CodeCov-style coverage diff (console), optional markdown brief for CI comments
covisible diff coverage_new.info -b coverage_old.info --markdown brief.md

# List files by coverage (-n 0 lists all, no limit)
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
