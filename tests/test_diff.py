"""Tests for diff parsing."""

from pathlib import Path

from covisible.analysis.diff import DiffAnalyzer


class TestDiffAnalyzer:
    """Tests for unified diff parser."""

    def test_parse_simple_diff(self):
        diff_content = """diff --git a/file.cpp b/file.cpp
index abc123..def456 100644
--- a/file.cpp
+++ b/file.cpp
@@ -10,0 +11,3 @@ void func() {
+    int x = 1;
+    int y = 2;
+    int z = 3;
"""
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)

        assert len(analyzer.files) == 1
        file_diff = analyzer.get_file_diff("file.cpp")
        assert file_diff is not None
        assert file_diff.added_lines == {11, 12, 13}

    def test_parse_new_file(self):
        diff_content = """diff --git a/new_file.cpp b/new_file.cpp
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/new_file.cpp
@@ -0,0 +1,3 @@
+line 1
+line 2
+line 3
"""
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)

        file_diff = analyzer.get_file_diff("new_file.cpp")
        assert file_diff is not None
        assert file_diff.is_new_file
        assert file_diff.added_lines == {1, 2, 3}

    def test_parse_deleted_file(self):
        diff_content = """diff --git a/old_file.cpp b/old_file.cpp
deleted file mode 100644
index abc123..0000000
--- a/old_file.cpp
+++ /dev/null
@@ -1,3 +0,0 @@
-line 1
-line 2
-line 3
"""
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)

        deleted = analyzer.get_deleted_files()
        assert len(deleted) == 1

    def test_parse_multiple_hunks(self):
        diff_content = """diff --git a/file.cpp b/file.cpp
--- a/file.cpp
+++ b/file.cpp
@@ -5,0 +6,1 @@
+new line at 6
@@ -20,0 +22,2 @@
+new line at 22
+new line at 23
"""
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)

        file_diff = analyzer.get_file_diff("file.cpp")
        assert file_diff is not None
        assert file_diff.added_lines == {6, 22, 23}
        assert len(file_diff.hunks) == 2

    def test_get_modified_files(self):
        diff_content = """diff --git a/file1.cpp b/file1.cpp
--- a/file1.cpp
+++ b/file1.cpp
@@ -1,0 +2,1 @@
+new line
diff --git a/file2.cpp b/file2.cpp
--- a/file2.cpp
+++ b/file2.cpp
@@ -1,0 +2,1 @@
+another line
"""
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)

        modified = analyzer.get_modified_files()
        assert len(modified) == 2

    def test_empty_diff(self):
        analyzer = DiffAnalyzer.from_unified_diff("")
        assert len(analyzer.files) == 0

    def test_hunk_mixes_added_removed_context(self):
        # -U0 normally omits context, but the parser must still advance line
        # numbers correctly across removed (-), added (+) and context ( ) rows.
        diff_content = (
            "diff --git a/f.c b/f.c\n--- a/f.c\n+++ b/f.c\n"
            "@@ -5,2 +5,2 @@\n-old line\n+new line\n unchanged\n"
        )
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)
        fd = analyzer.get_file_diff("f.c")
        assert fd is not None
        assert fd.added_lines == {5}
        assert fd.modified_lines == {5}
        # Removed lines are not tracked into hunk.removed_lines (parser skips them).
        assert fd.removed_lines == set()

    def test_parse_rename(self):
        diff_content = (
            "diff --git a/old.c b/new.c\n"
            "similarity index 95%\n"
            "rename from old.c\n"
            "rename to new.c\n"
        )
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)
        fd = analyzer.get_file_diff("new.c")
        assert fd is not None
        assert fd.is_renamed

    def test_get_file_diff_name_fallback_and_miss(self):
        diff_content = (
            "diff --git a/src/deep/mod.c b/src/deep/mod.c\n"
            "--- a/src/deep/mod.c\n+++ b/src/deep/mod.c\n@@ -0,0 +1,1 @@\n+x\n"
        )
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)
        # Path input (not str) + basename fallback to the stored full path.
        assert analyzer.get_file_diff(Path("mod.c")) is not None
        # No match -> None.
        assert analyzer.get_file_diff("nope.c") is None

    def test_get_added_lines_and_new_files(self):
        diff_content = (
            "diff --git a/n.c b/n.c\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/n.c\n@@ -0,0 +1,2 @@\n+a\n+b\n"
        )
        analyzer = DiffAnalyzer.from_unified_diff(diff_content)
        assert analyzer.get_added_lines("n.c") == {1, 2}
        assert analyzer.get_new_files() == [Path("n.c")]
        # Unknown file -> empty set (get_file_diff returns None).
        assert analyzer.get_added_lines("missing.c") == set()

    def test_from_diff_file(self, tmp_path):
        p = tmp_path / "pr.diff"
        p.write_text(
            "diff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n@@ -0,0 +1,1 @@\n+x\n"
        )
        analyzer = DiffAnalyzer.from_diff_file(p)
        fd = analyzer.get_file_diff("x.c")
        assert fd is not None and fd.added_lines == {1}

    def test_from_git_diff_invokes_git(self, monkeypatch):
        captured = {}

        class _Proc:
            stdout = (
                "diff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"
                "@@ -0,0 +1,1 @@\n+line\n"
            )

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            return _Proc()

        monkeypatch.setattr("covisible.analysis.diff.subprocess.run", fake_run)
        analyzer = DiffAnalyzer.from_git_diff("main..HEAD", repo_path="/tmp/repo")

        assert captured["cmd"][:3] == ["git", "diff", "--no-color"]
        assert captured["cmd"][-1] == "main..HEAD"
        assert Path(captured["cwd"]) == Path("/tmp/repo")
        fd = analyzer.get_file_diff("x.c")
        assert fd is not None and fd.added_lines == {1}
