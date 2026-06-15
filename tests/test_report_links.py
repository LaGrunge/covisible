"""Tests for report navigation consistency and the markdown diff brief.

Regression tests for the broken "Impacted Files" / "Impacted Modules"
links: every href and navigateToModule() target emitted into index.html
must point at a page or SPA tree node that actually exists.
"""

import json
import re
from pathlib import Path

from covisible.analysis.diff import DiffAnalyzer
from covisible.analysis.pr_coverage import PRCoverageAnalyzer
from covisible.parsers.lcov import parse_lcov_string
from covisible.report.generator import ReportGenerator
from covisible.report.markdown import render_diff_markdown


def make_lcov(file_hits: dict[str, dict[int, int]]) -> str:
    """Build an lcov document: {path: {line: hit_count}}."""
    chunks = []
    for path, lines in file_hits.items():
        body = "\n".join(f"DA:{ln},{cnt}" for ln, cnt in sorted(lines.items()))
        lf = len(lines)
        lh = sum(1 for c in lines.values() if c > 0)
        chunks.append(f"TN:\nSF:{path}\n{body}\nLF:{lf}\nLH:{lh}\nend_of_record")
    return "\n".join(chunks) + "\n"


CURRENT_LCOV = make_lcov(
    {
        "/repo/storage/orthus/core/key.cpp": {1: 1, 2: 0, 3: 1},
        "/repo/storage/orthus/client/impl.cpp": {1: 1, 2: 1},
        "/repo/storage/orthus/ha_orthus.cpp": {1: 1, 2: 0},
        "/repo/sql/handler.h": {1: 0, 2: 0},
    }
)

BASELINE_LCOV = make_lcov(
    {
        "/repo/storage/orthus/core/key.cpp": {1: 1, 2: 1, 3: 1},
        "/repo/storage/orthus/client/impl.cpp": {1: 1, 2: 0},
        "/repo/storage/orthus/ha_orthus.cpp": {1: 0, 2: 0},
        "/repo/sql/handler.h": {1: 1, 2: 1},
    }
)


# Same files as CURRENT_LCOV but with branch data on one line, so
# total_branches > 0 and the --branches flag has something to render.
BRANCH_LCOV = (
    "TN:\n"
    "SF:/repo/storage/orthus/core/key.cpp\n"
    "DA:10,5\n"
    "BRDA:10,0,0,3\n"
    "BRDA:10,0,1,0\n"
    "LF:1\nLH:1\n"
    "end_of_record\n"
)


# Absolute build paths sharing a common prefix. A base_path that does NOT
# contain them forces the canonical relativizer onto its common-prefix
# fallback — the case where the sunburst used to keep the full absolute path
# and desync from the module table.
ABSOLUTE_LCOV = make_lcov(
    {
        "/build/ci/proj/src/core/key.cpp": {1: 1, 2: 0},
        "/build/ci/proj/src/core/val.cpp": {1: 1, 2: 1},
        "/build/ci/proj/src/net/sock.cpp": {1: 0, 2: 0},
    }
)


def extract_coverage_tree_keys(html: str) -> set[str]:
    match = re.search(r"const coverageData = (\{.*?\});\n", html, re.S)
    assert match, "coverageData blob missing from index.html"
    return set(json.loads(match.group(1)).keys())


def extract_sunburst_dir_paths(html: str) -> set[str]:
    """All non-file node paths the sunburst can navigate to."""
    match = re.search(r"const sunburstData = (\{.*?\});", html, re.S)
    assert match, "sunburstData blob missing from index.html"
    root = json.loads(match.group(1))

    paths: set[str] = set()

    def walk(node: dict) -> None:
        for child in node.get("children", []):
            if child.get("is_file"):
                continue
            paths.add(child["path"])
            walk(child)

    walk(root)
    return paths


def assert_links_resolve(out: Path) -> None:
    html = (out / "index.html").read_text()

    static_hrefs = [
        h for h in re.findall(r'href="(files/[^"]+)"', html) if "' +" not in h
    ]
    missing = [h for h in static_hrefs if not (out / h).exists()]
    assert not missing, f"dangling file links: {missing}"

    tree_keys = extract_coverage_tree_keys(html)
    module_targets = set(re.findall(r"navigateToModule\('([^']*)'\)", html))
    dangling = [m for m in module_targets if m and m not in tree_keys]
    assert not dangling, f"navigateToModule targets missing from tree: {dangling}"


class TestSunburstSync:
    """The sunburst must use the same path keys as the module table so that
    clicking a slice navigates to a directory the table actually has."""

    def test_sunburst_paths_match_tree_keys(self, tmp_path):
        cov = parse_lcov_string(ABSOLUTE_LCOV)
        # base_path does not contain the absolute coverage paths, so the
        # relativizer falls back to the common prefix (/build/ci/proj/src).
        # The sunburst must follow suit, not emit absolute paths.
        gen = ReportGenerator(
            coverage=cov,
            output_dir=tmp_path / "report",
            base_path="/some/unrelated/root",
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        tree_keys = extract_coverage_tree_keys(html)
        sunburst_dirs = extract_sunburst_dir_paths(html)

        assert sunburst_dirs, "expected directory nodes in the sunburst"
        # Every sunburst directory must be a navigable key in the module tree.
        dangling = sunburst_dirs - tree_keys
        assert not dangling, f"sunburst dirs missing from module tree: {dangling}"
        # No absolute-path leakage — the relativization must have applied.
        leaked = {p for p in sunburst_dirs if p.startswith("/")}
        assert not leaked, f"sunburst kept absolute paths: {leaked}"
        # Concretely: the relative module dirs are present.
        assert {"core", "net"} <= sunburst_dirs

    def test_sunburst_paths_match_tree_keys_no_base_path(self, tmp_path):
        # Without base_path, both table and sunburst use the common prefix;
        # they must still agree.
        cov = parse_lcov_string(ABSOLUTE_LCOV)
        gen = ReportGenerator(coverage=cov, output_dir=tmp_path / "report")
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        tree_keys = extract_coverage_tree_keys(html)
        sunburst_dirs = extract_sunburst_dir_paths(html)

        assert sunburst_dirs - tree_keys == set()


class TestBaselineComparisonLinks:
    def test_impacted_links_resolve(self, tmp_path):
        current = parse_lcov_string(CURRENT_LCOV)
        baseline = parse_lcov_string(BASELINE_LCOV)

        gen = ReportGenerator(
            coverage=current,
            baseline=baseline,
            output_dir=tmp_path / "report",
            base_path="/repo/storage/orthus",
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        assert "Impacted Files" in html
        assert "Impacted Modules" in html
        assert_links_resolve(tmp_path / "report")

    def test_root_files_grouped_under_root_module(self, tmp_path):
        current = parse_lcov_string(CURRENT_LCOV)
        baseline = parse_lcov_string(BASELINE_LCOV)

        gen = ReportGenerator(
            coverage=current,
            baseline=baseline,
            output_dir=tmp_path / "report",
            base_path="/repo/storage/orthus",
        )
        modules = gen._build_impacted_modules()
        by_name = {m["name"]: m for m in modules}

        # ha_orthus.cpp lives at the repo root: it must not become a
        # one-file module pointing at a nonexistent tree node.
        assert "ha_orthus.cpp" not in by_name
        assert "(root)" in by_name
        assert by_name["(root)"]["path"] == ""

    def test_module_paths_are_tree_keys(self, tmp_path):
        current = parse_lcov_string(CURRENT_LCOV)
        baseline = parse_lcov_string(BASELINE_LCOV)

        gen = ReportGenerator(
            coverage=current,
            baseline=baseline,
            output_dir=tmp_path / "report",
            base_path="/repo/storage/orthus",
        )
        tree = gen._build_full_tree_for_spa()
        for module in gen._build_impacted_modules():
            assert module["path"] in tree, module


class TestAnalyzerModePages:
    def test_all_coverage_files_get_pages(self, tmp_path):
        """PR mode must generate pages for files outside the diff too —
        impacted-files links and SPA navigation point at all of them."""
        current = parse_lcov_string(CURRENT_LCOV)
        baseline = parse_lcov_string(BASELINE_LCOV)

        diff_text = (
            "diff --git a/core/key.cpp b/core/key.cpp\n"
            "--- a/core/key.cpp\n"
            "+++ b/core/key.cpp\n"
            "@@ -1,0 +1,2 @@\n"
            "+line one\n"
            "+line two\n"
        )
        diff = DiffAnalyzer.from_unified_diff(diff_text)
        analyzer = PRCoverageAnalyzer(current=current, diff=diff, baseline=baseline)
        analyzer.analyze()

        gen = ReportGenerator(
            analyzer=analyzer,
            output_dir=tmp_path / "report",
            base_path="/repo/storage/orthus",
        )
        gen.generate_html()

        pages = {p.name for p in (tmp_path / "report" / "files").iterdir()}
        # Full-path page for every covered file…
        for path in CURRENT_LCOV.splitlines():
            if path.startswith("SF:"):
                mangled = path[3:].replace("/", "_") + ".html"
                assert mangled in pages, f"missing page {mangled}"
        # …plus the diff-relative PR page.
        assert "core_key.cpp.html" in pages

        assert_links_resolve(tmp_path / "report")


class TestSourceMissingFallback:
    """When source files aren't on disk, file pages must still show coverage."""

    def test_file_page_renders_coverage_without_source(self, tmp_path):
        # CURRENT_LCOV paths (/repo/...) do not exist on disk, so source
        # reading yields nothing — the page must fall back to coverage rows.
        current = parse_lcov_string(CURRENT_LCOV)
        gen = ReportGenerator(coverage=current, output_dir=tmp_path / "report")
        gen.generate_html()

        page = (
            tmp_path / "report" / "files" / "_repo_storage_orthus_core_key.cpp.html"
        ).read_text()

        # The "source not found" note is shown…
        assert "source-missing-note" in page
        # …and a row is emitted for each executable line (1, 2, 3).
        for line_num in (1, 2, 3):
            assert f'data-line="{line_num}"' in page
        # Covered vs uncovered status reflects the hit counts (1:1, 2:0, 3:1).
        assert page.count("status-covered-dim") == 2
        assert page.count("status-uncovered-dim") == 1


class TestFunctionNavOrdering:
    """The function dropdown lists uncovered functions first."""

    def test_uncovered_functions_sort_first(self, tmp_path):
        # 'aaa_covered' is hit, 'zzz_uncovered' is not. Despite the alphabetical
        # order, the uncovered one must appear first in the dropdown.
        lcov = (
            "SF:/repo/storage/orthus/x.cpp\n"
            "FN:10,20,aaa_covered\n"
            "FN:30,40,zzz_uncovered\n"
            "FNDA:5,aaa_covered\n"
            "FNDA:0,zzz_uncovered\n"
            "DA:10,5\nDA:30,0\nend_of_record\n"
        )
        gen = ReportGenerator(
            coverage=parse_lcov_string(lcov), output_dir=tmp_path / "report"
        )
        gen.generate_html()

        page = (
            tmp_path / "report" / "files" / "_repo_storage_orthus_x.cpp.html"
        ).read_text()
        dropdown = page.split('id="func-dropdown"', 1)[1].split("</div>\n        </div>", 1)[0]

        assert dropdown.index("zzz_uncovered") < dropdown.index("aaa_covered")
        assert dropdown.index("func-item-uncovered") < dropdown.index("func-item-covered")


class TestMarkdownBrief:
    def test_brief_has_deltas(self):
        current = parse_lcov_string(CURRENT_LCOV)
        baseline = parse_lcov_string(BASELINE_LCOV)

        md = render_diff_markdown(current, baseline)
        assert "| Coverage | Master | PR |" in md
        assert "Lines" in md and "Functions" in md
        # current: 5/9 covered vs baseline 6/9 → red delta
        assert "🔴" in md

    def test_brief_zero_delta_is_neutral(self):
        current = parse_lcov_string(CURRENT_LCOV)
        md = render_diff_markdown(current, current)
        assert "⚪" in md
        assert "🔴" not in md and "🟢" not in md

    def test_brief_no_branches_row_without_branch_data(self):
        current = parse_lcov_string(CURRENT_LCOV)
        md = render_diff_markdown(current, current)
        assert "Branches" not in md


class TestBranchColumnsFlag:
    """Branch coverage columns in the Modules table are opt-in via --branches."""

    def test_branches_hidden_by_default(self, tmp_path):
        cov = parse_lcov_string(BRANCH_LCOV)
        gen = ReportGenerator(coverage=cov, output_dir=tmp_path / "report")
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        assert "Branch Coverage" not in html
        assert 'id="stat-branch-pct"' not in html
        assert "const hasBranches = false" in html

    def test_branches_shown_with_flag(self, tmp_path):
        cov = parse_lcov_string(BRANCH_LCOV)
        gen = ReportGenerator(
            coverage=cov, output_dir=tmp_path / "report", show_branches=True
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        assert "Branch Coverage" in html
        # The top summary card (next to Line/Function Coverage) is present too.
        assert 'id="stat-branch-pct"' in html
        assert "const hasBranches = true" in html

    def test_flag_is_noop_without_branch_data(self, tmp_path):
        # CURRENT_LCOV has no BRDA records, so there is nothing to show even
        # when the flag is on — columns must stay hidden (no empty 100% column).
        cov = parse_lcov_string(CURRENT_LCOV)
        gen = ReportGenerator(
            coverage=cov, output_dir=tmp_path / "report", show_branches=True
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        assert "Branch Coverage" not in html
        assert 'id="stat-branch-pct"' not in html
        assert "const hasBranches = false" in html


class TestExceptionBranchParsing:
    def test_e_prefixed_blocks_counted(self):
        lcov = (
            "TN:\n"
            "SF:/repo/a.cpp\n"
            "DA:10,5\n"
            "BRDA:10,0,0,3\n"
            "BRDA:10,0,1,0\n"
            "BRDA:10,e0,0,-\n"
            "BRDA:10,e0,1,2\n"
            "LF:1\nLH:1\n"
            "end_of_record\n"
        )
        cov = parse_lcov_string(lcov)
        f = next(iter(cov.files.values()))
        assert f.total_branches == 4
        assert f.covered_branches == 2
        throws = [b for b in f.lines[10].branches if b.is_throw]
        assert len(throws) == 2
