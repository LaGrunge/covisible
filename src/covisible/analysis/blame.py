"""Git blame integration for uncovered code analysis."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BlameInfo:
    """Blame information for a single line."""

    line_number: int
    commit_hash: str
    author: str
    author_email: str
    timestamp: str
    line_content: str


@dataclass
class AuthorStats:
    """Statistics for a single author."""

    name: str
    email: str
    total_uncovered_lines: int = 0
    files: set[str] = field(default_factory=set)
    lines: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "total_uncovered_lines": self.total_uncovered_lines,
            "files_count": len(self.files),
            "files": sorted(self.files),
            "lines": self.lines[:20],
        }


class GitBlameAnalyzer:
    """Analyzes git blame for uncovered lines."""

    def __init__(self, repo_path: Path | str | None = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._cache: dict[Path, dict[int, BlameInfo]] = {}

    def get_blame_for_file(self, file_path: Path | str) -> dict[int, BlameInfo]:
        """Get blame information for all lines in a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary mapping line numbers to BlameInfo
        """
        file_path = Path(file_path)

        if file_path in self._cache:
            return self._cache[file_path]

        result: dict[int, BlameInfo] = {}

        try:
            cmd = [
                "git", "blame",
                "--line-porcelain",
                str(file_path),
            ]

            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                check=True,
            )

            result = self._parse_porcelain_blame(output.stdout)

        except subprocess.CalledProcessError:
            pass

        self._cache[file_path] = result
        return result

    def _parse_porcelain_blame(self, output: str) -> dict[int, BlameInfo]:
        """Parse git blame --line-porcelain output."""
        result: dict[int, BlameInfo] = {}
        lines = output.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue

            parts = line.split(" ")
            if len(parts) < 3:
                i += 1
                continue

            commit_hash = parts[0]
            if len(commit_hash) != 40:
                i += 1
                continue

            line_number = int(parts[2])

            author = ""
            author_email = ""
            timestamp = ""
            content = ""

            i += 1
            while i < len(lines) and not lines[i].startswith("\t"):
                if lines[i].startswith("author "):
                    author = lines[i][7:]
                elif lines[i].startswith("author-mail "):
                    author_email = lines[i][12:].strip("<>")
                elif lines[i].startswith("author-time "):
                    timestamp = lines[i][12:]
                i += 1

            if i < len(lines) and lines[i].startswith("\t"):
                content = lines[i][1:]
                i += 1

            result[line_number] = BlameInfo(
                line_number=line_number,
                commit_hash=commit_hash,
                author=author,
                author_email=author_email,
                timestamp=timestamp,
                line_content=content,
            )

        return result

    def get_blame_for_lines(
        self, file_path: Path | str, line_numbers: list[int]
    ) -> dict[int, BlameInfo]:
        """Get blame information for specific lines.

        Args:
            file_path: Path to the file
            line_numbers: List of line numbers to get blame for

        Returns:
            Dictionary mapping line numbers to BlameInfo
        """
        all_blame = self.get_blame_for_file(file_path)
        return {ln: all_blame[ln] for ln in line_numbers if ln in all_blame}

    def analyze_uncovered_lines(
        self,
        uncovered_by_file: dict[Path, list[int]],
    ) -> dict[str, AuthorStats]:
        """Analyze who wrote uncovered lines.

        Args:
            uncovered_by_file: Dictionary mapping file paths to uncovered line numbers

        Returns:
            Dictionary mapping author emails to their stats
        """
        author_stats: dict[str, AuthorStats] = {}

        for file_path, line_numbers in uncovered_by_file.items():
            blame_info = self.get_blame_for_lines(file_path, line_numbers)

            for line_num, info in blame_info.items():
                email = info.author_email or info.author

                if email not in author_stats:
                    author_stats[email] = AuthorStats(
                        name=info.author,
                        email=info.author_email,
                    )

                stats = author_stats[email]
                stats.total_uncovered_lines += 1
                stats.files.add(str(file_path))
                stats.lines.append((str(file_path), line_num))

        return author_stats

    def get_top_authors_by_uncovered(
        self,
        uncovered_by_file: dict[Path, list[int]],
        limit: int = 10,
    ) -> list[AuthorStats]:
        """Get top authors by number of uncovered lines.

        Args:
            uncovered_by_file: Dictionary mapping file paths to uncovered line numbers
            limit: Maximum number of authors to return

        Returns:
            List of AuthorStats sorted by uncovered lines descending
        """
        stats = self.analyze_uncovered_lines(uncovered_by_file)
        sorted_stats = sorted(
            stats.values(),
            key=lambda x: x.total_uncovered_lines,
            reverse=True,
        )
        return sorted_stats[:limit]


def get_uncovered_blame_summary(
    uncovered_by_file: dict[Path, list[int]],
    repo_path: Path | str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get summary of who wrote uncovered code.

    Args:
        uncovered_by_file: Dictionary mapping file paths to uncovered line numbers
        repo_path: Path to git repository
        limit: Maximum number of authors to return

    Returns:
        List of author stats as dictionaries
    """
    analyzer = GitBlameAnalyzer(repo_path)
    top_authors = analyzer.get_top_authors_by_uncovered(uncovered_by_file, limit)
    return [author.to_dict() for author in top_authors]
