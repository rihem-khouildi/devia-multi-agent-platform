"""
Structured error extraction for Maven compile and test failures.

Takes raw artifact dicts (compile_report.to_dict(), test_run.to_dict()) and
produces a clean, frontend-ready error payload:

{
  "run_id":       str,
  "step":         "compile" | "run_tests",
  "error_type":   str,          # canonical failure_type
  "summary":      str,          # one-sentence human description
  "copyable_error": str,        # copy-paste block (filenames + messages)
  "files": [{"path": str, "line": int, "message": str}],
  "raw_excerpt":  str,          # ≤40 relevant Maven lines
}

Only the extraction logic lives here — no I/O, no HTTP, no storage.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

# Lines from Maven output that are worth keeping in raw_excerpt.
_RELEVANT_PATTERNS = re.compile(
    r"\[ERROR\]|\[WARNING\].*error|compilation failure|compilation error"
    r"|cannot find symbol|symbol:|location:|failed to execute goal"
    r"|BUILD FAILURE|there are test failures|tests run:|error:|exception",
    re.IGNORECASE,
)

# Lines that are noise and should be stripped from the excerpt.
_NOISE_PATTERNS = re.compile(
    r"download(ing|ed)|progress|^\[INFO\] (Building|Scanning|---)|"
    r"^\[INFO\] \[|\[INFO\] Total time|\[INFO\] Finished at|\[INFO\] BUILD",
    re.IGNORECASE,
)

_MAX_EXCERPT_LINES = 40
_MAX_FILES = 30


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_compile_errors(
    run_id: str,
    compile_report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a structured error payload from a compile_report artifact dict.

    compile_report is the dict produced by CompileResult.to_dict():
      {success, error_count, errors[{file,line,message,code_snippet}],
       warnings, output, failure_type, return_code, duration_seconds}
    """
    success = compile_report.get("success", False)
    failure_type = compile_report.get("failure_type") or "maven_or_build_tool_failure"
    raw_errors: List[Dict[str, Any]] = compile_report.get("errors") or []
    output: str = compile_report.get("output") or ""

    # Normalise file entries
    files = _normalise_file_errors(raw_errors)

    summary = _compile_summary(failure_type, files, compile_report.get("error_count", 0))
    copyable = _build_copyable_compile(failure_type, files, output)
    excerpt = _extract_relevant_lines(output)

    return {
        "run_id": run_id,
        "step": "compile",
        "error_type": failure_type,
        "summary": summary,
        "copyable_error": copyable,
        "files": files,
        "raw_excerpt": excerpt,
    }


def extract_test_errors(
    run_id: str,
    test_run: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a structured error payload from a test_run artifact dict.

    test_run is the dict produced by TestRunResult.to_dict():
      {success, total_tests, passed_tests, failed_tests, error_tests,
       failed_test_names, failure_type, output, duration_seconds, return_code, …}
    """
    failure_type = test_run.get("failure_type") or "test_execution_failure"
    output: str = test_run.get("output") or ""
    failed_names: List[str] = test_run.get("failed_test_names") or []
    total = test_run.get("total_tests", 0)
    passed = test_run.get("passed_tests", 0)
    failed = test_run.get("failed_tests", 0)
    errored = test_run.get("error_tests", 0)
    duration_seconds = test_run.get("duration_seconds")
    return_code = test_run.get("return_code")

    # For test_compilation_failure the output has javac-style errors
    files: List[Dict[str, Any]] = []
    if failure_type == "test_compilation_failure":
        files = _parse_javac_errors_from_output(output)

    summary = _test_summary(failure_type, total, passed, failed, errored, failed_names,
                            duration_seconds=duration_seconds)
    copyable = _build_copyable_test(failure_type, failed_names, files, output,
                                    duration_seconds=duration_seconds,
                                    return_code=return_code)
    excerpt = _extract_relevant_lines(output) or _timeout_excerpt(output, failure_type)
    recommended_action = _recommended_action(failure_type)

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "step": "run_tests",
        "error_type": failure_type,
        "summary": summary,
        "copyable_error": copyable,
        "files": files,
        "raw_excerpt": excerpt,
        "recommended_action": recommended_action,
    }

    # Include timeout diagnostics when relevant
    if failure_type == "maven_test_timeout":
        payload["timeout_details"] = {
            "timeout_seconds": _parse_timeout_seconds(output),
            "duration_seconds": duration_seconds,
            "exit_code": return_code,
        }

    return payload


def combine_run_errors(
    run_id: str,
    compile_error: Optional[Dict[str, Any]],
    test_error: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return the list of structured errors for a run.
    Skips None entries (step did not fail or was not reached).
    """
    result = []
    if compile_error:
        result.append(compile_error)
    if test_error:
        result.append(test_error)
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_file_errors(raw_errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert CompileError dicts to the canonical {path, line, message} shape."""
    seen = set()
    out = []
    for e in raw_errors[:_MAX_FILES]:
        path = e.get("file") or "unknown"
        line = int(e.get("line") or 0)
        message = (e.get("message") or "").strip()
        key = (path, line, message)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": path, "line": line, "message": message})
    return out


def _parse_javac_errors_from_output(output: str) -> List[Dict[str, Any]]:
    """
    Re-parse Maven output for javac-style errors that appear during test compilation.
    Uses the same patterns as MavenBuildRunner._parse_errors().
    """
    pattern1 = re.compile(r"\[ERROR\]\s+(.+?\.java):\[(\d+),\d+\]\s+(.+)")
    pattern2 = re.compile(r"(.+?\.java):(\d+):\s+error:\s+(.+)")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for line in output.splitlines():
        for pat in [pattern1, pattern2]:
            m = pat.search(line)
            if m:
                path = m.group(1).strip()
                lineno = int(m.group(2))
                msg = m.group(3).strip()
                key = (path, lineno, msg)
                if key not in seen:
                    seen.add(key)
                    out.append({"path": path, "line": lineno, "message": msg})
                break
        if len(out) >= _MAX_FILES:
            break
    return out


def _extract_relevant_lines(output: str) -> str:
    """
    Keep only error-relevant lines from Maven output.
    Returns at most _MAX_EXCERPT_LINES lines joined as a string.
    """
    relevant = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _NOISE_PATTERNS.search(stripped):
            continue
        if _RELEVANT_PATTERNS.search(stripped):
            relevant.append(stripped)

    # Fallback: last N lines if nothing matched
    if not relevant:
        fallback = [l.strip() for l in output.splitlines() if l.strip()]
        relevant = fallback[-_MAX_EXCERPT_LINES:]

    return "\n".join(relevant[:_MAX_EXCERPT_LINES])


# ── Summary builders ──────────────────────────────────────────────────────────

def _compile_summary(failure_type: str, files: List[Dict], error_count: int) -> str:
    n = error_count or len(files)
    if failure_type == "java_compilation_failure":
        if n == 1:
            f = files[0] if files else {}
            return (
                f"1 compilation error in {f.get('path','?')} "
                f"at line {f.get('line','?')}: {f.get('message','?')}"
            )
        return f"{n} Java compilation error(s) — fix the highlighted files before proceeding."
    if failure_type == "environment_or_dependency_failure":
        return "Maven environment or dependency resolution failed. Check your JDK, network, or pom.xml."
    return f"Maven build failed (type: {failure_type}). See raw excerpt for details."


def _test_summary(
    failure_type: str,
    total: int,
    passed: int,
    failed: int,
    errored: int,
    failed_names: List[str],
    duration_seconds: Optional[float] = None,
) -> str:
    if failure_type == "maven_test_timeout":
        dur = f" after {duration_seconds:.0f}s" if duration_seconds else ""
        return (
            f"Quality Gate blocked — Maven test execution timed out{dur}. "
            "Increase the timeout, enable Maven cache, or remove slow full-context tests (e.g. ApplicationTests)."
        )
    if failure_type == "test_assertion_failure":
        names = ", ".join(failed_names[:3])
        suffix = f" … and {len(failed_names) - 3} more" if len(failed_names) > 3 else ""
        return f"{failed} test(s) failed: {names}{suffix}"
    if failure_type == "test_execution_failure":
        return f"{errored} test(s) raised unexpected exceptions during execution."
    if failure_type == "test_compilation_failure":
        return "Test sources did not compile. Fix the compilation errors shown below."
    if failure_type == "test_environment_or_dependency_failure":
        return "Test environment failure (JDK/Maven/network issue). No tests were run."
    if failure_type == "test_tooling_failure":
        return f"Maven Surefire/JUnit tooling failure — {total} test(s) discovered, {passed} passed."
    if failure_type == "missing_or_unreadable_test_report":
        return "Surefire reports are missing or unreadable — cannot determine test results."
    return f"Tests failed (type: {failure_type}). {passed}/{total} tests passed."


# ── Copy-paste block builders ─────────────────────────────────────────────────

def _parse_timeout_seconds(output: str) -> Optional[int]:
    """Extract the timeout value from a Maven timeout output string."""
    m = re.search(r"timeout[_\s]+seconds[:\s]+(\d+)", output, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"[Tt]imeout after (\d+)s", output)
    if m:
        return int(m.group(1))
    return None


def _timeout_excerpt(output: str, failure_type: str) -> str:
    """Return a minimal excerpt for timeout errors when _extract_relevant_lines returns nothing."""
    if failure_type != "maven_test_timeout":
        return ""
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    return "\n".join(lines[:20]) if lines else output[:500]


def _recommended_action(failure_type: str) -> Optional[str]:
    _actions = {
        "maven_test_timeout": (
            "Increase Maven timeout via MAVEN_TEST_TIMEOUT_SECONDS, "
            "enable Maven cache via MAVEN_LOCAL_REPO, "
            "or remove slow full-context tests (ApplicationTests)."
        ),
        "test_environment_or_dependency_failure": (
            "Check JDK installation, network connectivity, and pom.xml dependency resolution."
        ),
        "test_compilation_failure": (
            "Fix the compilation errors in the test sources shown below."
        ),
        "test_assertion_failure": (
            "Review the failing assertions and align them with the current production code."
        ),
    }
    return _actions.get(failure_type)


def _build_copyable_compile(
    failure_type: str,
    files: List[Dict[str, Any]],
    output: str,
) -> str:
    if failure_type == "java_compilation_failure" and files:
        lines = ["=== Compilation Errors ==="]
        for f in files:
            lines.append(f"  {f['path']}:{f['line']}  →  {f['message']}")
        return "\n".join(lines)
    # For env/tool failures, use the excerpt
    relevant = _extract_relevant_lines(output)
    return f"=== Build Failure ===\n{relevant}" if relevant else f"Build failed — type: {failure_type}"


def _build_copyable_test(
    failure_type: str,
    failed_names: List[str],
    files: List[Dict[str, Any]],
    output: str,
    duration_seconds: Optional[float] = None,
    return_code: Optional[int] = None,
) -> str:
    if failure_type == "maven_test_timeout":
        timeout_val = _parse_timeout_seconds(output)
        lines = ["=== Maven Test Timeout ==="]
        if timeout_val:
            lines.append(f"  timeout_seconds : {timeout_val}")
        if duration_seconds is not None:
            lines.append(f"  duration_seconds: {duration_seconds:.1f}")
        if return_code is not None:
            lines.append(f"  exit_code       : {return_code}")
        lines.append("")
        lines.append("No generated source file is directly responsible.")
        lines.append("This is an infrastructure or test execution timeout.")
        lines.append("")
        lines.append("Recommended actions:")
        lines.append("  1. Set MAVEN_TEST_TIMEOUT_SECONDS=360 (or higher) in your environment.")
        lines.append("  2. Set MAVEN_LOCAL_REPO=/app/output/.m2/repository to persist Maven cache.")
        lines.append("  3. Remove or skip ApplicationTests.java if it loads the full Spring context.")
        # Include the raw output excerpt if we have one
        excerpt = _extract_relevant_lines(output)
        if not excerpt and output:
            excerpt = "\n".join(output.splitlines()[-20:])
        if excerpt:
            lines.append("")
            lines.append("--- stdout/stderr excerpt ---")
            lines.append(excerpt)
        return "\n".join(lines)
    if failure_type == "test_compilation_failure" and files:
        lines = ["=== Test Compilation Errors ==="]
        for f in files:
            lines.append(f"  {f['path']}:{f['line']}  →  {f['message']}")
        return "\n".join(lines)
    if failure_type == "test_assertion_failure" and failed_names:
        lines = ["=== Failed Tests ==="]
        for name in failed_names[:20]:
            lines.append(f"  ✗ {name}")
        return "\n".join(lines)
    relevant = _extract_relevant_lines(output)
    return f"=== Test Failure ===\n{relevant}" if relevant else f"Tests failed — type: {failure_type}"
