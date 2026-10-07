"""
Deterministic quality analysis for generated Java code.

This module complements the LLM-based reviewer with reproducible checks for:
- skipped tests
- duplicated code
- oversized / complex methods
- security hotspots
- style / convention violations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models import GeneratedCode


@dataclass
class QualityIssue:
    category: str
    severity: str
    file: str
    message: str
    metric: float | int | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "file": self.file,
            "message": self.message,
            "metric": self.metric,
        }


@dataclass
class QualityReport:
    passed: bool
    gates: Dict[str, bool]
    metrics: Dict[str, float | int]
    issues: List[QualityIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "gates": self.gates,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class QualityAnalyzer:
    DUPLICATION_WINDOW_SIZE = 3
    METHOD_PATTERN = re.compile(
        r"(?P<signature>(?:public|protected|private)\s+[\w<>\[\], ?]+\s+\w+\s*\([^;{}]*\))\s*\{",
        re.MULTILINE,
    )
    CONTROL_FLOW_PATTERN = re.compile(r"\b(if|for|while|case|catch|switch)\b|\&\&|\|\||\?")
    LINE_COMMENT_PATTERN = re.compile(r"//.*?$", re.MULTILINE)
    BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)

    def __init__(self, config: Any):
        self.config = config

    def analyze(self, generated_code: GeneratedCode, test_run_data: Dict[str, Any]) -> QualityReport:
        issues: List[QualityIssue] = []
        source_files = {
            path: content
            for path, content in generated_code.files.items()
            if path.endswith(".java") and "/test/" not in path.replace("\\", "/")
        }

        skipped_tests = int(test_run_data.get("skipped_tests", 0) or 0)
        skipped_tests_ok = skipped_tests <= self.config.max_skipped_tests
        if not skipped_tests_ok:
            issues.append(QualityIssue(
                category="tests",
                severity="MAJOR",
                file="tests",
                message=(
                    f"Too many skipped tests: {skipped_tests} > allowed {self.config.max_skipped_tests}"
                ),
                metric=skipped_tests,
            ))

        duplication_percent = self._compute_duplication_percent(source_files)
        duplication_ok = duplication_percent <= self.config.max_duplicate_code_percent
        if not duplication_ok:
            issues.append(QualityIssue(
                category="duplication",
                severity="MAJOR",
                file="src/main/java",
                message=(
                    f"Duplicate code ratio {duplication_percent:.1f}% exceeds "
                    f"limit {self.config.max_duplicate_code_percent:.1f}%"
                ),
                metric=round(duplication_percent, 1),
            ))

        max_method_lines = 0
        max_complexity = 0
        maintainability_issues = 0
        complexity_issues = 0
        security_hotspots = 0
        style_violations = 0

        for path, content in source_files.items():
            method_metrics = self._analyze_methods(path, content)
            max_method_lines = max(max_method_lines, method_metrics["max_method_lines"])
            max_complexity = max(max_complexity, method_metrics["max_complexity"])
            maintainability_issues += len(method_metrics["long_methods"])
            complexity_issues += len(method_metrics["complex_methods"])

            for name, line_count in method_metrics["long_methods"]:
                issues.append(QualityIssue(
                    category="maintainability",
                    severity="MAJOR",
                    file=path,
                    message=(
                        f"Method '{name}' is too long: {line_count} lines > "
                        f"allowed {self.config.max_method_lines}"
                    ),
                    metric=line_count,
                ))

            for name, complexity in method_metrics["complex_methods"]:
                issues.append(QualityIssue(
                    category="complexity",
                    severity="MAJOR",
                    file=path,
                    message=(
                        f"Method '{name}' is too complex: {complexity} > "
                        f"allowed {self.config.max_cyclomatic_complexity}"
                    ),
                    metric=complexity,
                ))

            security_matches = self._find_security_hotspots(path, content)
            security_hotspots += len(security_matches)
            issues.extend(security_matches)

            style_matches = self._find_style_violations(path, content)
            style_violations += len(style_matches)
            issues.extend(style_matches)

        maintainability_ok = maintainability_issues == 0
        complexity_ok = complexity_issues == 0
        security_ok = security_hotspots == 0
        style_ok = style_violations == 0

        gates = {
            "skipped_tests_ok": skipped_tests_ok,
            "duplication_ok": duplication_ok,
            "maintainability_ok": maintainability_ok,
            "complexity_ok": complexity_ok,
            "security_ok": security_ok,
            "style_ok": style_ok,
        }
        metrics = {
            "skipped_tests": skipped_tests,
            "duplication_percent": round(duplication_percent, 1),
            "max_method_lines": int(max_method_lines),
            "max_cyclomatic_complexity": int(max_complexity),
            "maintainability_issues": maintainability_issues,
            "complexity_issues": complexity_issues,
            "security_hotspots": security_hotspots,
            "style_violations": style_violations,
        }
        return QualityReport(
            passed=all(gates.values()),
            gates=gates,
            metrics=metrics,
            issues=issues,
        )

    def _compute_duplication_percent(self, source_files: Dict[str, str]) -> float:
        normalized_windows: List[str] = []
        for content in source_files.values():
            significant_lines = self._significant_duplication_lines(content)
            if len(significant_lines) < self.DUPLICATION_WINDOW_SIZE:
                continue
            for index in range(len(significant_lines) - self.DUPLICATION_WINDOW_SIZE + 1):
                window = "\n".join(significant_lines[index:index + self.DUPLICATION_WINDOW_SIZE])
                normalized_windows.append(window)
        if not normalized_windows:
            return 0.0
        unique = set(normalized_windows)
        duplicate_instances = len(normalized_windows) - len(unique)
        return (duplicate_instances / len(normalized_windows)) * 100

    def _significant_duplication_lines(self, content: str) -> List[str]:
        significant_lines: List[str] = []
        stripped = self._strip_comments(content)
        for raw_line in stripped.splitlines():
            line = self._normalize_duplication_line(raw_line)
            if (
                not line
                or self._is_structural_duplication_line(line)
                or self._is_low_signal_duplication_line(line)
            ):
                continue
            significant_lines.append(line)
        return significant_lines

    def _normalize_duplication_line(self, raw_line: str) -> str:
        line = raw_line.strip()
        if not line:
            return ""
        line = re.sub(r"\s+", " ", line)
        return line

    def _is_structural_duplication_line(self, line: str) -> bool:
        if line in {"{", "}", ");", "(", ")", "};"}:
            return True
        structural_patterns = [
            r"^package\s+[\w.]+;$",
            r"^import\s+[\w.*]+;$",
            r"^@[A-Za-z_][\w.]*\s*(\([^)]*\))?$",
            r"^(public\s+)?(class|interface|enum|record)\s+\w+.*$",
            r"^(public|protected|private)\s+(static\s+)?(final\s+)?[\w<>\[\], ?]+\s+\w+\s*(=\s*[^;]+)?;$",
            r"^(public|protected|private)\s+[\w<>\[\], ?]+\s+\w+\s*\([^;{}]*\)\s*\{$",
        ]
        return any(re.match(pattern, line) for pattern in structural_patterns)

    def _is_low_signal_duplication_line(self, line: str) -> bool:
        low_signal_patterns = [
            r"^return\s+ResponseEntity\..*;$",
            r"^\w+\.\w+\([^;]*\);$",
            r"^return\s+\w+\.\w+\([^;]*\);$",
            r"^return\s+\w+\([^;]*\);$",
        ]
        return any(re.match(pattern, line) for pattern in low_signal_patterns)

    def _analyze_methods(self, path: str, content: str) -> Dict[str, Any]:
        long_methods: List[tuple[str, int]] = []
        complex_methods: List[tuple[str, int]] = []
        max_method_lines = 0
        max_complexity = 0
        for match in self.METHOD_PATTERN.finditer(content):
            method_name = self._method_name(match.group("signature"))
            start_index = match.end() - 1
            body = self._extract_block(content, start_index)
            if not body:
                continue
            method_lines = self._logical_line_count(body)
            complexity = 1 + len(self.CONTROL_FLOW_PATTERN.findall(body))
            max_method_lines = max(max_method_lines, method_lines)
            max_complexity = max(max_complexity, complexity)
            if method_lines > self.config.max_method_lines:
                long_methods.append((method_name, method_lines))
            if complexity > self.config.max_cyclomatic_complexity:
                complex_methods.append((method_name, complexity))
        return {
            "long_methods": long_methods,
            "complex_methods": complex_methods,
            "max_method_lines": max_method_lines,
            "max_complexity": max_complexity,
        }

    def _find_security_hotspots(self, path: str, content: str) -> List[QualityIssue]:
        issues: List[QualityIssue] = []
        patterns = [
            (r'@Query\s*\(\s*"[^"]*(select|update|delete|insert)[^"]*"\s*\+', "Possible SQL query concatenation in @Query"),
            (r'createNativeQuery\s*\([^)]*\+', "Possible SQL injection via createNativeQuery string concatenation"),
            (r'execute(Query|Update)\s*\([^)]*\+', "Possible SQL injection via query string concatenation"),
            (r'Runtime\.getRuntime\(\)\.exec\s*\(', "Runtime.exec usage detected"),
            (r'System\.setProperty\s*\(\s*"[^"]*password', "Sensitive password-like value configured in code"),
        ]
        for pattern, message in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append(QualityIssue(
                    category="security",
                    severity="CRITICAL",
                    file=path,
                    message=message,
                ))
        return issues

    def _find_style_violations(self, path: str, content: str) -> List[QualityIssue]:
        issues: List[QualityIssue] = []
        checks = [
            (r'^\s*import\s+javax\.', "Forbidden javax import; use jakarta.* instead"),
            (r'^\s*import\s+jakarta\.ws\.rs\.', "Forbidden jakarta.ws.rs import; use Spring Web annotations instead"),
            (r'@\s*Autowired\s*\n\s*(private|protected|public)\s+', "Field injection detected; prefer constructor injection"),
            (r'^\s*import\s+.+\.\*\s*;', "Wildcard import detected"),
        ]
        for pattern, message in checks:
            if re.search(pattern, content, re.MULTILINE):
                issues.append(QualityIssue(
                    category="style",
                    severity="MAJOR",
                    file=path,
                    message=message,
                ))
        return issues

    def _strip_comments(self, content: str) -> str:
        without_block = self.BLOCK_COMMENT_PATTERN.sub("", content)
        return self.LINE_COMMENT_PATTERN.sub("", without_block)

    def _extract_block(self, content: str, brace_index: int) -> str:
        depth = 0
        end_index = brace_index
        for index in range(brace_index, len(content)):
            char = content[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_index = index
                    break
        if end_index <= brace_index:
            return ""
        return content[brace_index + 1:end_index]

    def _logical_line_count(self, body: str) -> int:
        count = 0
        for raw_line in self._strip_comments(body).splitlines():
            line = raw_line.strip()
            if line:
                count += 1
        return count

    def _method_name(self, signature: str) -> str:
        head = signature.split("(")[0].strip()
        return head.split()[-1] if head else "method"
