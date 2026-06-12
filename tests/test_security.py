"""Unit tests for the security scanner (Module 3)."""
import config
import security_scanner

BUGGY_DIFF = """diff --git a/app/db.py b/app/db.py
--- a/app/db.py
+++ b/app/db.py
@@ -1,2 +1,6 @@
+import sqlite3
+PASSWORD = "supersecret123"
+def get_user(name):
+    cur.execute("SELECT * FROM users WHERE name = '" + name + "'")
+    return cur.fetchone()
"""


def test_files_from_diff_extracts_added_lines():
    files = security_scanner.files_from_diff(BUGGY_DIFF)
    assert "app/db.py" in files
    assert "supersecret123" in files["app/db.py"]
    assert "diff --git" not in files["app/db.py"]


def test_builtin_rules_catch_sql_injection_and_secret():
    files = security_scanner.files_from_diff(BUGGY_DIFF)
    findings = security_scanner._run_builtin(files)
    rules = {f["rule_id"] for f in findings}
    assert "builtin.sql-injection" in rules
    assert "builtin.hardcoded-secret" in rules
    assert all(f["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL") for f in findings)


def test_scan_diff_persists_findings(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "t.db"))
    database.init_db()
    findings = security_scanner.scan_diff(BUGGY_DIFF)
    assert findings, "expected findings from the buggy diff"
    assert all("explanation" in f for f in findings)
    with database.get_db() as db:
        count = db.execute("SELECT COUNT(*) AS n FROM security_findings").fetchone()["n"]
    assert count == len(findings)


def test_clean_diff_produces_no_findings():
    clean = """diff --git a/app/ok.py b/app/ok.py
--- a/app/ok.py
+++ b/app/ok.py
@@ -1,1 +1,3 @@
+def add(a: int, b: int) -> int:
+    return a + b
"""
    files = security_scanner.files_from_diff(clean)
    assert security_scanner._run_builtin(files) == []
