"""Module 4 — Test gap detector + AI test generator.

Python AST finds public functions in the PR that have no corresponding
test, then Qwen3 Coder (via NIM) generates the missing pytest tests.
"""
import ast
import logging
import re

import nim_client

logger = logging.getLogger("devguardian.testgen")


def find_functions(source: str) -> list[dict]:
    """All top-level and method functions defined in a Python source string."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({
                "name": node.name,
                "line": node.lineno,
                "args": [a.arg for a in node.args.args if a.arg not in ("self", "cls")],
                "is_private": node.name.startswith("_"),
            })
    return out


def find_untested(files: dict[str, str]) -> dict[str, list[dict]]:
    """Map source file -> public functions with no matching test reference.

    A function counts as tested if any test file in the PR mentions its name
    or contains test_<name>.
    """
    test_blob = "\n".join(
        content for fname, content in files.items()
        if re.search(r"(^|/)test_|_test\.py$|(^|/)tests?/", fname)
    )
    gaps: dict[str, list[dict]] = {}
    for fname, content in files.items():
        if not fname.endswith(".py") or re.search(r"(^|/)test_|_test\.py$", fname):
            continue
        untested = [
            fn for fn in find_functions(content)
            if not fn["is_private"]
            and f"test_{fn['name']}" not in test_blob
            and fn["name"] not in test_blob
        ]
        if untested:
            gaps[fname] = untested
    return gaps


def generate_missing_tests(files: dict[str, str]) -> dict[str, str]:
    """Generate a pytest module for every source file with untested functions.

    Returns {test_file_path: test_source}.
    """
    generated = {}
    for fname, funcs in find_untested(files).items():
        names = [f["name"] for f in funcs]
        logger.info("Generating tests for %s: %s", fname, names)
        test_source = nim_client.generate_tests(files[fname], names)
        test_name = "tests/test_" + fname.replace("/", "_").removesuffix(".py") + ".py"
        generated[test_name] = test_source
    return generated
