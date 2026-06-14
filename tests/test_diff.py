"""Tests for diff parsing."""


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
