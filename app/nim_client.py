"""NVIDIA NIM client with DTS-adaptive model routing and 429 fallback chain.

Depth -> model:
    shallow  -> meta/llama-4-maverick            (~8s quick scan)
    standard -> mistralai/devstral-2-123b        (~25s full review)
    deep     -> qwen/qwen3-coder-480b-instruct   (~45s audit + tests)
Fallback on rate limit: nvidia/nemotron-super-49b-instruct.

If NVIDIA_API_KEY is missing the client runs in mock mode and returns
deterministic structured reviews so the whole pipeline works offline.
"""
import json
import logging
import re
import time

import config

logger = logging.getLogger("devguardian.nim")

DEPTH_MODELS = {
    "shallow": config.MODEL_SHALLOW,
    "standard": config.MODEL_STANDARD,
    "deep": config.MODEL_DEEP,
}

DEPTH_PROMPTS = {
    "shallow": (
        "You are DevGuardian, a fast pre-merge gate. Quick scan: list ONLY "
        "critical bugs or security issues. Ignore style."
    ),
    "standard": (
        "You are DevGuardian, an AI code reviewer. Full review: bugs, logic "
        "errors, security issues, and concrete improvements."
    ),
    "deep": (
        "You are DevGuardian in DEEP AUDIT mode (low-trust author). Examine "
        "security vulnerabilities, logic errors, missing tests, error handling "
        "and architectural problems. Be aggressive and thorough."
    ),
}

REVIEW_SCHEMA_HINT = (
    'Respond ONLY with JSON: {"summary": str, "verdict": "approve"|"comment"|'
    '"request_changes", "findings": [{"file": str, "line": int, "severity": '
    '"LOW"|"MEDIUM"|"HIGH"|"CRITICAL", "title": str, "detail": str, '
    '"suggested_fix": str}]}'
)


def _client():
    from openai import OpenAI
    return OpenAI(base_url=config.NIM_BASE_URL, api_key=config.NVIDIA_API_KEY)


def _chat(model: str, system: str, user: str, max_retries: int = 2) -> str:
    """Single chat completion with fallback to Nemotron on rate limit."""
    models = [model, config.MODEL_FALLBACK]
    last_err: Exception | None = None
    for m in models:
        for attempt in range(max_retries):
            try:
                resp = _client().chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.2,
                    max_tokens=2048,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # 429 / transient — try fallback chain
                last_err = exc
                if "429" in str(exc):
                    logger.warning("Rate limited on %s, retrying/falling back", m)
                    time.sleep(2 * (attempt + 1))
                    continue
                break
    raise RuntimeError(f"NIM call failed across fallback chain: {last_err}")


def _parse_review(raw: str) -> dict:
    """Extract the JSON review object from a model response."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, AttributeError):
        data = {"summary": raw[:500], "verdict": "comment", "findings": []}
    data.setdefault("summary", "")
    data.setdefault("verdict", "comment")
    data.setdefault("findings", [])
    return data


# --- Mock reviews (used when no API key) ------------------------------------

_MOCK_FINDING_PATTERNS = [
    (r"execute\([^)]*[%+]|f[\"'].*SELECT|SELECT.*\{", "CRITICAL", "SQL injection",
     "Query is built by string interpolation; attacker-controlled input reaches the database.",
     "Use parameterised queries: cursor.execute('SELECT ... WHERE id = ?', (user_id,))"),
    (r"(password|secret|api_key|token)\s*=\s*[\"'][^\"']{6,}[\"']", "HIGH", "Hardcoded secret",
     "A credential is committed in source code and will leak via git history.",
     "Move the value to an environment variable loaded with python-dotenv."),
    (r"except\s*:\s*pass|except Exception\s*:\s*pass", "MEDIUM", "Swallowed exception",
     "Errors are silently discarded, hiding production failures.",
     "Log the exception and re-raise or handle the specific error type."),
    (r"eval\(|exec\(", "CRITICAL", "Arbitrary code execution",
     "eval/exec on dynamic input allows remote code execution.",
     "Replace with ast.literal_eval or an explicit dispatch table."),
    (r"verify\s*=\s*False", "HIGH", "TLS verification disabled",
     "requests(... verify=False) allows man-in-the-middle attacks.",
     "Remove verify=False and trust the system CA bundle."),
]


def _mock_review(diff: str, depth: str) -> dict:
    findings = []
    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+"):
            continue
        for pattern, sev, title, detail, fix in _MOCK_FINDING_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({
                    "file": _current_file(diff, i), "line": i, "severity": sev,
                    "title": title, "detail": detail, "suggested_fix": fix,
                })
    if depth == "shallow":
        findings = [f for f in findings if f["severity"] in ("HIGH", "CRITICAL")]
    verdict = ("request_changes" if any(f["severity"] in ("HIGH", "CRITICAL") for f in findings)
               else "comment" if findings else "approve")
    return {
        "summary": (f"[mock {depth} review] {len(findings)} issue(s) detected by offline "
                    "pattern engine. Connect an NVIDIA_API_KEY for full AI review."),
        "verdict": verdict,
        "findings": findings,
    }


def _current_file(diff: str, line_no: int) -> str:
    current = "unknown"
    for i, line in enumerate(diff.splitlines(), 1):
        if line.startswith("+++ b/"):
            current = line[6:]
        if i >= line_no:
            break
    return current


# --- Public API --------------------------------------------------------------

def review_pr(diff: str, depth: str) -> dict:
    """DTS-adaptive PR review. Returns {summary, verdict, findings[], model, duration_ms}."""
    start = time.monotonic()
    model = DEPTH_MODELS.get(depth, config.MODEL_STANDARD)
    if config.MOCK_NIM:
        result = _mock_review(diff, depth)
        model = f"mock:{model}"
    else:
        raw = _chat(model, f"{DEPTH_PROMPTS[depth]}\n{REVIEW_SCHEMA_HINT}", diff[:60000])
        result = _parse_review(raw)
    result["model"] = model
    result["duration_ms"] = int((time.monotonic() - start) * 1000)
    return result


def explain_finding(rule_id: str, message: str, code: str) -> str:
    """Plain-English explanation + fix for a Semgrep finding."""
    if config.MOCK_NIM:
        return (f"{message} This was flagged by rule '{rule_id}'. Review the highlighted "
                "code and apply the secure alternative. (mock explanation — add "
                "NVIDIA_API_KEY for AI-generated guidance)")
    return _chat(
        config.MODEL_DEEP,
        "Explain this security finding to a developer in 2-3 plain sentences, then give a concrete fix.",
        f"Rule: {rule_id}\nFinding: {message}\nCode:\n{code}",
    )


def generate_tests(source: str, functions: list[str], framework: str = "pytest") -> str:
    """Generate missing unit tests for the given functions."""
    if config.MOCK_NIM:
        lines = ["# Auto-generated test skeletons (mock mode — add NVIDIA_API_KEY for full AI tests)",
                 "import pytest", ""]
        for fn in functions:
            lines += [f"def test_{fn}_happy_path():",
                      f"    # TODO: arrange inputs and assert expected output of {fn}()",
                      "    raise NotImplementedError", ""]
        return "\n".join(lines)
    return _chat(
        config.MODEL_DEEP,
        f"Write complete, runnable {framework} tests. Respond with code only.",
        f"Untested functions: {', '.join(functions)}\n\nSource:\n{source[:40000]}",
    )


def write_report(prompt: str) -> str:
    """Narrative generation (team risk reports, deploy summaries) via Llama 4."""
    if config.MOCK_NIM:
        return ""  # caller supplies its own mock narrative
    return _chat(config.MODEL_REPORT,
                 "You are DevGuardian's analyst. Write concise, anonymised, actionable reports.",
                 prompt)
