"""Git diff parsing and analysis."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiffHunk:
    """A single hunk in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: set[int] = field(default_factory=set)
    removed_lines: set[int] = field(default_factory=set)
    context_lines: set[int] = field(default_factory=set)


@dataclass
class FileDiff:
    """Diff information for a single file."""

    old_path: Path | None
    new_path: Path | None
    hunks: list[DiffHunk] = field(default_factory=list)
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed: bool = False

    @property
    def path(self) -> Path:
        """Get the current path of the file."""
        return self.new_path or self.old_path or Path("")

    @property
    def added_lines(self) -> set[int]:
        """Get all added line numbers."""
        result: set[int] = set()
        for hunk in self.hunks:
            result.update(hunk.added_lines)
        return result

    @property
    def removed_lines(self) -> set[int]:
        """Get all removed line numbers (in old file)."""
        result: set[int] = set()
        for hunk in self.hunks:
            result.update(hunk.removed_lines)
        return result

    @property
    def modified_lines(self) -> set[int]:
        """Get all modified line numbers (added lines in new file)."""
        return self.added_lines


@dataclass
class DiffAnalyzer:
    """Analyzes git diffs to determine changed lines."""

    files: dict[Path, FileDiff] = field(default_factory=dict)

    @classmethod
    def from_git_diff(
        cls,
        diff_range: str,
        repo_path: Path | str | None = None,
    ) -> DiffAnalyzer:
        """Create DiffAnalyzer from git diff command.

        Args:
            diff_range: Git diff range (e.g., "main..HEAD", "HEAD~1..HEAD")
            repo_path: Path to git repository (defaults to current directory)

        Returns:
            DiffAnalyzer with parsed diff information
        """
        cmd = ["git", "diff", "--no-color", "-U0", diff_range]
        cwd = Path(repo_path) if repo_path else None

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=True,
        )

        return cls.from_unified_diff(result.stdout)

    @classmethod
    def from_diff_file(cls, path: Path | str) -> DiffAnalyzer:
        """Create DiffAnalyzer from a diff file.

        Args:
            path: Path to unified diff file

        Returns:
            DiffAnalyzer with parsed diff information
        """
        with open(path) as f:
            return cls.from_unified_diff(f.read())

    @classmethod
    def from_unified_diff(cls, diff_content: str) -> DiffAnalyzer:
        """Parse unified diff format.

        Args:
            diff_content: Unified diff content

        Returns:
            DiffAnalyzer with parsed diff information
        """
        analyzer = cls()
        current_file: FileDiff | None = None
        current_hunk: DiffHunk | None = None
        new_line_num = 0

        file_header_re = re.compile(r"^diff --git a/(.+) b/(.+)$")
        old_file_re = re.compile(r"^--- (?:a/)?(.+)$")
        new_file_re = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
        hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        new_file_mode_re = re.compile(r"^new file mode")
        deleted_file_mode_re = re.compile(r"^deleted file mode")
        rename_re = re.compile(r"^rename (from|to) (.+)$")

        for line in diff_content.splitlines():
            if match := file_header_re.match(line):
                if current_file and current_file.new_path:
                    analyzer.files[current_file.new_path] = current_file
                current_file = FileDiff(
                    old_path=Path(match.group(1)),
                    new_path=Path(match.group(2)),
                )
                current_hunk = None

            elif new_file_mode_re.match(line):
                if current_file:
                    current_file.is_new_file = True

            elif deleted_file_mode_re.match(line):
                if current_file:
                    current_file.is_deleted_file = True

            elif match := rename_re.match(line):
                if current_file:
                    current_file.is_renamed = True

            elif match := old_file_re.match(line):
                if current_file and match.group(1) != "/dev/null":
                    current_file.old_path = Path(match.group(1))

            elif match := new_file_re.match(line):
                if current_file and match.group(1) != "/dev/null":
                    current_file.new_path = Path(match.group(1))

            elif match := hunk_re.match(line):
                if current_file:
                    current_hunk = DiffHunk(
                        old_start=int(match.group(1)),
                        old_count=int(match.group(2) or 1),
                        new_start=int(match.group(3)),
                        new_count=int(match.group(4) or 1),
                    )
                    current_file.hunks.append(current_hunk)
                    new_line_num = current_hunk.new_start

            elif current_hunk is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.added_lines.add(new_line_num)
                    new_line_num += 1
                elif line.startswith("-") and not line.startswith("---"):
                    pass
                elif line.startswith(" "):
                    current_hunk.context_lines.add(new_line_num)
                    new_line_num += 1

        if current_file and current_file.new_path:
            analyzer.files[current_file.new_path] = current_file

        return analyzer

    def get_file_diff(self, path: Path | str) -> FileDiff | None:
        """Get diff for a specific file."""
        if isinstance(path, str):
            path = Path(path)

        if path in self.files:
            return self.files[path]

        for file_path, diff in self.files.items():
            if file_path.name == path.name or str(file_path).endswith(str(path)):
                return diff

        return None

    def get_added_lines(self, path: Path | str) -> set[int]:
        """Get added line numbers for a file."""
        diff = self.get_file_diff(path)
        return diff.added_lines if diff else set()

    def get_modified_files(self) -> list[Path]:
        """Get list of modified files."""
        return [
            diff.path
            for diff in self.files.values()
            if not diff.is_deleted_file
        ]

    def get_new_files(self) -> list[Path]:
        """Get list of new files."""
        return [
            diff.path
            for diff in self.files.values()
            if diff.is_new_file
        ]

    def get_deleted_files(self) -> list[Path]:
        """Get list of deleted files."""
        return [
            diff.old_path
            for diff in self.files.values()
            if diff.is_deleted_file and diff.old_path
        ]
