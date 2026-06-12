"""Module 3 — Security scanner: Semgrep OSS static analysis + AI explanation.

Runs `semgrep --config=auto --json` as a subprocess on the changed files,
then sends each finding to NIM for a plain-English explanation and fix.
On platforms without Semgrep (native Windows) a built-in regex rule pack
covering the OWASP basics is used instead, so the module always produces
findings for the demo.
"""
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import nim_client
from database import get_db, now

logger = logging.getLogger("devguardian.security")

SEMGREP_SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}

# Built-in fallback rules (subset of OWASP Top 10 patterns)
BUILTIN_RULES = [
    ("builtin.sql-injection", "CRITICAL",
     r"(execute|executemany)\s*\(\s*(f[\"']|[\"'].*[%+]|.*\.format\()",
     "SQL query built with string formatting — injection risk."),
    ("builtin.hardcoded-secret", "HIGH",
     r"(password|passwd|secret|api_key|apikey|token)\s*=\s*[\"'][^\"']{6,}[\"']",
     "Hardcoded credential committed to source."),
    ("builtin.eval-exec", "CRITICAL",
     r"\b(eval|exec)\s*\(",
     "Dynamic code execution — arbitrary code execution risk."),
    ("builtin.tls-verify-off", "HIGH",
     r"verify\s*=\s*False",
     "TLS certificate verification disabled."),
    ("builtin.weak-hash", "MEDIUM",
     r"hashlib\.(md5|sha1)\s*\(",
     "Weak hash algorithm used — unsuitable for passwords or signatures."),
    ("builtin.shell-injection", "HIGH",
     r"(subprocess|os)\.(system|popen|call|run)\s*\(.*(\+|%|format|f[\"'])",
     "Shell command built from dynamic input — command injection risk."),
    ("builtin.pickle-load", "MEDIUM",
     r"pickle\.loads?\s*\(",
     "Deserialising untrusted pickle data can execute arbitrary code."),
]


def semgrep_available() -> bool:
    return shutil.which("semgrep") is not None


def _run_semgrep(target: Path) -> list[dict]:
    proc = subprocess.run(
        ["semgrep", "--config=auto", "--json", "--quiet", str(target)],
        capture_output=True, text=True, timeout=300,
    )
    results = json.loads(proc.stdout or "{}").get("results", [])
    return [{
        "rule_id": r["check_id"],
        "severity": SEMGREP_SEVERITY.get(r["extra"]["severity"], "MEDIUM"),
        "file": r["path"],
        "line": r["start"]["line"],
        "message": r["extra"]["message"],
        "code": r["extra"].get("lines", ""),
    } for r in results]


def _run_builtin(files: dict[str, str]) -> list[dict]:
    findings = []
    for fname, content in files.items():
        for line_no, line in enumerate(content.splitlines(), 1):
            for rule_id, severity, pattern, message in BUILTIN_RULES:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": rule_id, "severity": severity, "file": fname,
                        "line": line_no, "message": message, "code": line.strip(),
                    })
    return findings


def files_from_diff(diff: str) -> dict[str, str]:
    """Reconstruct added-line content per file from a unified diff."""
    files: dict[str, list[str]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            files[current] = []
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current].append(line[1:])
    return {f: "\n".join(lines) for f, lines in files.items() if lines}


def scan_diff(diff: str, pr_id: int | None = None,
              developer_id: int | None = None) -> list[dict]:
    """Scan the added lines of a PR diff. Persists findings and returns them
    with AI explanations attached."""
    files = files_from_diff(diff)
    if not files:
        return []

    if semgrep_available():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for fname, content in files.items():
                target = root / fname
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            findings = _run_semgrep(root)
            for f in findings:  # restore repo-relative paths
                f["file"] = str(Path(f["file"]).relative_to(root)).replace("\\", "/")
    else:
        logger.info("Semgrep unavailable — using built-in rule pack")
        findings = _run_builtin(files)

    for f in findings:
        f["explanation"] = nim_client.explain_finding(f["rule_id"], f["message"], f["code"])

    with get_db() as db:
        for f in findings:
            db.execute(
                "INSERT INTO security_findings "
                "(pr_id, developer_id, rule_id, severity, file, line, message, explanation, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pr_id, developer_id, f["rule_id"], f["severity"], f["file"],
                 f["line"], f["message"], f["explanation"], now()),
            )
    return findings
