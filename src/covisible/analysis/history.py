"""Coverage history tracking for trend visualization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class HistoryEntry:
    """A single coverage history entry."""

    timestamp: str
    commit: str | None
    branch: str | None
    line_coverage_percent: float
    function_coverage_percent: float
    total_lines: int
    covered_lines: int
    total_functions: int
    covered_functions: int
    total_files: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            timestamp=data.get("timestamp", ""),
            commit=data.get("commit"),
            branch=data.get("branch"),
            line_coverage_percent=data.get("line_coverage_percent", 0),
            function_coverage_percent=data.get("function_coverage_percent", 0),
            total_lines=data.get("total_lines", 0),
            covered_lines=data.get("covered_lines", 0),
            total_functions=data.get("total_functions", 0),
            covered_functions=data.get("covered_functions", 0),
            total_files=data.get("total_files", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CoverageHistory:
    """Manages coverage history for trend tracking."""

    def __init__(self, history_file: Path | str | None = None):
        self.history_file = Path(history_file) if history_file else None
        self.entries: list[HistoryEntry] = []

        if self.history_file and self.history_file.exists():
            self._load()

    def _load(self) -> None:
        """Load history from file."""
        if not self.history_file:
            return

        try:
            with open(self.history_file) as f:
                data = json.load(f)
                self.entries = [HistoryEntry.from_dict(e) for e in data.get("entries", [])]
        except (OSError, json.JSONDecodeError):
            self.entries = []

    def save(self) -> None:
        """Save history to file."""
        if not self.history_file:
            return

        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.history_file, "w") as f:
            json.dump({"entries": [e.to_dict() for e in self.entries]}, f, indent=2)

    def add_entry(
        self,
        line_coverage_percent: float,
        function_coverage_percent: float,
        total_lines: int,
        covered_lines: int,
        total_functions: int,
        covered_functions: int,
        total_files: int,
        commit: str | None = None,
        branch: str | None = None,
    ) -> HistoryEntry:
        """Add a new history entry."""
        entry = HistoryEntry(
            timestamp=datetime.now().isoformat(),
            commit=commit,
            branch=branch,
            line_coverage_percent=line_coverage_percent,
            function_coverage_percent=function_coverage_percent,
            total_lines=total_lines,
            covered_lines=covered_lines,
            total_functions=total_functions,
            covered_functions=covered_functions,
            total_files=total_files,
        )
        self.entries.append(entry)
        return entry

    def get_trend_data(self, max_entries: int = 30) -> list[dict[str, Any]]:
        """Get trend data for visualization."""
        entries = self.entries[-max_entries:] if len(self.entries) > max_entries else self.entries
        return [e.to_dict() for e in entries]

    def get_latest(self) -> HistoryEntry | None:
        """Get the latest entry."""
        return self.entries[-1] if self.entries else None

    def get_delta(self) -> dict[str, float] | None:
        """Get coverage delta from previous entry."""
        if len(self.entries) < 2:
            return None

        current = self.entries[-1]
        previous = self.entries[-2]

        return {
            "line_coverage_delta": current.line_coverage_percent - previous.line_coverage_percent,
            "function_coverage_delta": (
                current.function_coverage_percent - previous.function_coverage_percent
            ),
            "lines_delta": current.covered_lines - previous.covered_lines,
            "functions_delta": current.covered_functions - previous.covered_functions,
        }
