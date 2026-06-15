"""Tests for git-blame attribution of uncovered lines.

Regression for the case where coverage paths point into a different checkout
than ``--repo``/``base_path``: ``git blame`` must still find authors by running
from the file's own directory instead of an unrelated repository.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from covisible.analysis.blame import get_uncovered_blame_summary
from covisible.core.models import CoverageData, FileCoverage, LineCoverage
from covisible.report.generator import ReportGenerator, _avatar_url


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _commit_as(repo: Path, name: str, email: str, msg: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
    subprocess.run(
        ["git", "commit", "-q", "-m", msg],
        cwd=repo, check=True, capture_output=True, text=True, env=env,
    )


def _make_multidir_repo(tmp_path: Path) -> Path:
    """Repo where pkg/a.py is by Author A and pkg/sub/b.py is by Author B."""
    repo = tmp_path / "multi"
    (repo / "pkg" / "sub").mkdir(parents=True)
    _git(["init", "-q"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)

    (repo / "pkg" / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    _git(["add", "pkg/a.py"], repo)
    _commit_as(repo, "Author A", "a@example.com", "add a")

    (repo / "pkg" / "sub" / "b.py").write_text("p = 1\nq = 2\n")
    _git(["add", "pkg/sub/b.py"], repo)
    _commit_as(repo, "Author B", "b@example.com", "add b")
    return repo


def _make_repo(tmp_path: Path) -> Path:
    """Create a tiny git repo with one committed file (6 lines)."""
    repo = tmp_path / "src-repo"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "dev@example.com"], repo)
    _git(["config", "user.name", "Dev Example"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "mod.py").write_text(
        "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    )
    _git(["add", "mod.py"], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    return repo


def _coverage_for(file_path: Path, uncovered: list[int]) -> CoverageData:
    lines = {
        ln: LineCoverage(line_number=ln, count=0 if ln in uncovered else 1)
        for ln in range(1, 7)
    }
    return CoverageData(files={file_path: FileCoverage(path=file_path, lines=lines)})


class TestBlameRepoDiscovery:
    def test_blame_found_when_repo_path_mismatched(self, tmp_path):
        repo = _make_repo(tmp_path)
        target = repo / "mod.py"

        # repo_path deliberately points elsewhere — coverage paths live in a
        # different checkout than --repo. Blame must still resolve authors by
        # running git from the file's own directory.
        other = tmp_path / "unrelated"
        other.mkdir()

        authors = get_uncovered_blame_summary({target: [2, 6]}, repo_path=other, limit=10)

        assert authors, "expected blame to attribute uncovered lines to an author"
        assert authors[0]["name"] == "Dev Example"
        assert authors[0]["total_uncovered_lines"] == 2


class TestBlameInReport:
    def test_report_shows_authors_with_mismatched_base_path(self, tmp_path):
        repo = _make_repo(tmp_path)
        target = repo / "mod.py"
        cov = _coverage_for(target, uncovered=[2, 6])

        other = tmp_path / "unrelated"
        other.mkdir()

        gen = ReportGenerator(
            coverage=cov,
            output_dir=tmp_path / "report",
            base_path=other,  # mismatched, as in the bug report
            enable_blame=True,
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        assert "Uncovered Code by Author" in html
        assert "Dev Example" in html
        # Compact card is a clickable anchor with a mailto link and a Gravatar.
        assert 'href="mailto:dev@example.com"' in html
        assert "author-avatar-img" in html
        assert "gravatar.com/avatar/" in html

    def test_no_authors_section_without_blame(self, tmp_path):
        repo = _make_repo(tmp_path)
        target = repo / "mod.py"
        cov = _coverage_for(target, uncovered=[2, 6])

        gen = ReportGenerator(
            coverage=cov,
            output_dir=tmp_path / "report",
            base_path=repo,
            enable_blame=False,
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        # The heading text also appears in a JS comment, so assert on the
        # rendered section element instead.
        assert 'id="authors-section"' not in html


class TestBlameFollowsDirectories:
    """Authorship must be aggregated per directory so the panel can follow
    directory navigation instead of always showing whole-project totals."""

    def _coverage(self, repo: Path) -> CoverageData:
        a = repo / "pkg" / "a.py"
        b = repo / "pkg" / "sub" / "b.py"
        files = {
            a: FileCoverage(
                path=a,
                lines={ln: LineCoverage(line_number=ln, count=0) for ln in (1, 2, 3)},
            ),
            b: FileCoverage(
                path=b,
                lines={ln: LineCoverage(line_number=ln, count=0) for ln in (1, 2)},
            ),
        }
        return CoverageData(files=files)

    def test_authors_aggregated_per_directory(self, tmp_path):
        repo = _make_multidir_repo(tmp_path)
        gen = ReportGenerator(
            coverage=self._coverage(repo),
            output_dir=tmp_path / "report",
            base_path=repo,
            enable_blame=True,
        )
        by_path = gen._build_blame_by_path()

        def names(key: str) -> set[str]:
            return {a["name"] for a in by_path.get(key, [])}

        assert names("") == {"Author A", "Author B"}  # whole project
        assert names("pkg") == {"Author A", "Author B"}
        assert names("pkg/sub") == {"Author B"}  # only the sub file
        # The root bucket counts every uncovered line (3 + 2).
        assert sum(a["total_uncovered_lines"] for a in by_path[""]) == 5

    def test_report_embeds_per_directory_blame(self, tmp_path):
        repo = _make_multidir_repo(tmp_path)
        gen = ReportGenerator(
            coverage=self._coverage(repo),
            output_dir=tmp_path / "report",
            base_path=repo,
            enable_blame=True,
        )
        gen.generate_html()

        html = (tmp_path / "report" / "index.html").read_text()
        match = re.search(r"const blameByPath = (\{.*?\});", html, re.S)
        assert match, "blameByPath blob missing from index.html"
        data = json.loads(match.group(1))

        assert {a["name"] for a in data[""]} == {"Author A", "Author B"}
        assert {a["name"] for a in data["pkg/sub"]} == {"Author B"}


class TestAvatarUrl:
    def test_github_noreply_login(self):
        assert (
            _avatar_url("arcolight@users.noreply.github.com")
            == "https://github.com/arcolight.png?size=48"
        )

    def test_github_noreply_numeric_id(self):
        assert (
            _avatar_url("12345+arcolight@users.noreply.github.com")
            == "https://avatars.githubusercontent.com/u/12345?s=48"
        )

    def test_gravatar_fallback(self):
        assert _avatar_url("dev@example.com").startswith("https://www.gravatar.com/avatar/")

    def test_empty_or_invalid(self):
        assert _avatar_url("") == ""
        assert _avatar_url(None) == ""
        assert _avatar_url("not-an-email") == ""
