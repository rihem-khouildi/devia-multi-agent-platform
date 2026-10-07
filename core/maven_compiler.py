"""
MavenBuildRunner
================
Compiles AND tests the generated Java project using Maven.

Workflow:
  compile_main()  → mvn compile            (src/main only)
  run_tests()     → mvn test               (src/main + src/test, produces Surefire + JaCoCo)
  parse_surefire_results() → pass/fail per test class
  parse_jacoco_report()    → real line/branch coverage from jacoco.xml

The class MavenCompiler is kept for backward compatibility — it delegates
to MavenBuildRunner.compile_main() internally.
"""

import asyncio
import re
import shutil
import tempfile
import os
import time
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
from xml.etree import ElementTree

from core.models import GeneratedCode, TestResult
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
#  Data classes
# ─────────────────────────────────────────────

@dataclass
class CompileError:
    file: str
    line: int
    message: str
    code_snippet: str = ""

    def __str__(self):
        return f"{self.file}:{self.line} → {self.message}"


@dataclass
class CompileResult:
    success: bool
    errors: List[CompileError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0
    failure_type: Optional[str] = None
    return_code: Optional[int] = None

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def to_prompt(self) -> str:
        if self.success:
            return "✅ Compilation réussie, aucune erreur."
        lines = [f"❌ {self.error_count} erreur(s) de compilation Maven:\n"]
        for e in self.errors[:20]:
            lines.append(f"- Fichier: {e.file}")
            lines.append(f"  Ligne {e.line}: {e.message}")
            if e.code_snippet:
                lines.append(f"  Code: {e.code_snippet}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "error_count": self.error_count,
            "duration_seconds": self.duration_seconds,
            "failure_type": self.failure_type,
            "return_code": self.return_code,
            "errors": [vars(e) for e in self.errors],
            "warnings": self.warnings,
        }


@dataclass
class SurefireTestCase:
    classname: str
    name: str
    time_seconds: float = 0.0
    failure: Optional[str] = None
    error: Optional[str] = None
    skipped: bool = False

    @property
    def passed(self) -> bool:
        return self.failure is None and self.error is None and not self.skipped


@dataclass
class TestRunResult:
    """Result of actually executing mvn test."""
    success: bool                    # True if all tests pass (returncode 0)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    skipped_tests: int = 0
    test_cases: List[SurefireTestCase] = field(default_factory=list)
    # Real coverage from JaCoCo (None if jacoco.xml not found)
    line_coverage: Optional[float] = None    # 0.0 – 100.0
    branch_coverage: Optional[float] = None  # 0.0 – 100.0
    duration_seconds: float = 0.0
    class_coverage: List[Dict[str, object]] = field(default_factory=list)
    method_coverage: List[Dict[str, object]] = field(default_factory=list)
    output: str = ""
    coverage_source: str = "fallback"
    jacoco_report_path: Optional[str] = None
    workspace_path: Optional[str] = None
    written_test_files: List[str] = field(default_factory=list)
    effective_pom_has_jacoco: bool = False
    failure_type: Optional[str] = None
    return_code: Optional[int] = None
    surefire_report_issue: Optional[str] = None

    @property
    def coverage(self) -> Optional[float]:
        """Best available coverage metric."""
        if self.line_coverage is not None:
            return self.line_coverage
        return None

    def failed_test_names(self) -> List[str]:
        return [
            f"{tc.classname}.{tc.name}"
            for tc in self.test_cases
            if not tc.passed
        ]

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "error_tests": self.error_tests,
            "skipped_tests": self.skipped_tests,
            "line_coverage": self.line_coverage,
            "branch_coverage": self.branch_coverage,
            "class_coverage": self.class_coverage,
            "method_coverage": self.method_coverage,
            "duration_seconds": self.duration_seconds,
            "failed_test_names": self.failed_test_names(),
            "coverage_source": self.coverage_source,
            "jacoco_report_path": self.jacoco_report_path,
            "workspace_path": self.workspace_path,
            "written_test_files": self.written_test_files,
            "effective_pom_has_jacoco": self.effective_pom_has_jacoco,
            "failure_type": self.failure_type,
            "return_code": self.return_code,
            "surefire_report_issue": self.surefire_report_issue,
        }


# ─────────────────────────────────────────────
#  MavenBuildRunner
# ─────────────────────────────────────────────

class MavenBuildRunner:
    """
    Runs Maven phases on the generated code.

    All methods write the code to a temporary directory, run Maven,
    parse the results, then clean up.
    """

    MAVEN_VERSION = "3.9.9"

    def __init__(self, timeout: int = 180):
        # Allow override via environment variable (Azure / CI tuning)
        env_timeout = (
            os.getenv("MAVEN_TEST_TIMEOUT_SECONDS")
            or os.getenv("PIPELINE_MAVEN_TEST_TIMEOUT_SECONDS")
        )
        self.timeout = int(env_timeout) if env_timeout else timeout

        self.maven_cmd = "mvn.cmd" if os.name == "nt" else "mvn"
        self.maven_embedded_dir = (
            Path(__file__).resolve().parent.parent / ".tools" / "maven"
        )
        # Allow persistent local Maven repo via env (avoids re-downloading on Azure)
        env_repo = os.getenv("MAVEN_LOCAL_REPO")
        if env_repo:
            self.maven_local_repo_dir = Path(env_repo)
        else:
            azure_persistent = Path("/app/output/.m2/repository")
            if azure_persistent.parent.parent.exists():
                self.maven_local_repo_dir = azure_persistent
            else:
                self.maven_local_repo_dir = (
                    Path(__file__).resolve().parent.parent / ".tools" / "m2" / "repository"
                )
        self._resolved_cmd: Optional[str] = None  # cached after first resolution

    # ──────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────

    async def compile_main(self, generated_code: GeneratedCode) -> CompileResult:
        """
        Run `mvn compile` on src/main only.
        Does NOT execute tests.
        """
        tmpdir = Path(tempfile.mkdtemp(prefix="ai-sdlc-compile-"))
        logger.info(f"  📁 Compile tmpdir: {tmpdir}")
        try:
            self._write_main_sources(generated_code, tmpdir)
            maven_cmd = await self._resolve_maven()
            if not maven_cmd:
                return self._maven_unavailable_result()

            start = time.time()
            result = await self._run(tmpdir, maven_cmd, ["compile", "-q", "--no-transfer-progress"])
            result.duration_seconds = round(time.time() - start, 1)

            if result.success:
                logger.info(f"  ✅ Compilation OK in {result.duration_seconds}s")
            else:
                logger.warning(f"  ❌ {result.error_count} compile error(s) in {result.duration_seconds}s")
                for err in result.errors[:5]:
                    logger.warning(f"     → {err}")
            return result
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def run_tests(
        self,
        generated_code: GeneratedCode,
        test_files: Dict[str, str],
    ) -> TestRunResult:
        """
        Run `mvn test` with JaCoCo instrumentation.

        Writes both src/main and src/test, then:
          1. Executes `mvn test`
          2. Parses Surefire XML reports   → pass/fail per test
          3. Parses jacoco.xml              → real line/branch coverage

        Returns a TestRunResult with real metrics.
        """
        tmpdir = Path(tempfile.mkdtemp(prefix="ai-sdlc-test-"))
        logger.info(f"  📁 Test tmpdir: {tmpdir}")
        try:
            normalized_input_tests = sorted(
                path.replace("\\", "/")
                for path, content in (test_files or {}).items()
                if str(content or "").strip()
            )
            if normalized_input_tests:
                logger.info("  Received test files for Maven: " + ", ".join(normalized_input_tests))
            else:
                logger.warning("  Received no non-empty test files for Maven")
            written_main = self._write_main_sources(generated_code, tmpdir)
            written_tests = self._write_test_sources(test_files, tmpdir)
            effective_pom_has_jacoco = self._pom_has_jacoco(tmpdir / "pom.xml")
            logger.info(
                f"  Workspace Maven test: {tmpdir} | "
                f"main_files={len(written_main)} | test_files={len(written_tests)}"
            )
            if written_tests:
                logger.info(f"  Test files written before mvn test: {written_tests}")
            else:
                logger.warning("  No test files were written before mvn test")
            logger.info(
                "  Effective pom JaCoCo: "
                f"{'enabled' if effective_pom_has_jacoco else 'missing'}"
            )

            if not written_tests:
                return TestRunResult(
                    success=False,
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=0,
                    error_tests=0,
                    skipped_tests=0,
                    duration_seconds=0.0,
                    coverage_source="fallback",
                    workspace_path=str(tmpdir),
                    written_test_files=[],
                    effective_pom_has_jacoco=effective_pom_has_jacoco,
                    output="No valid non-empty test sources were written before mvn test",
                    failure_type="no_test_sources_written",
                    return_code=-1,
                )

            maven_cmd = await self._resolve_maven()
            if not maven_cmd:
                return TestRunResult(
                    success=False,
                    workspace_path=str(tmpdir),
                    written_test_files=written_tests,
                    effective_pom_has_jacoco=effective_pom_has_jacoco,
                    output="Maven not available — cannot run tests",
                    failure_type="test_environment_or_dependency_failure",
                    return_code=-1,
                )

            logger.info(
                f"  ▶ mvn test | cwd={tmpdir} | timeout={self.timeout}s "
                f"| repo={self.maven_local_repo_dir}"
            )
            start = time.time()
            returncode, output = await self._run_raw(
                tmpdir, maven_cmd,
                ["test", "--no-transfer-progress", "-Dsurefire.failIfNoSpecifiedTests=false"],
            )
            duration = round(time.time() - start, 1)
            logger.info(
                f"  ⏱️  mvn test finished | duration={duration}s | rc={returncode} "
                f"| timeout_seconds={self.timeout}"
            )

            # Parse Surefire reports
            surefire_dir = tmpdir / "target" / "surefire-reports"
            test_cases, surefire_report_issue = self._parse_surefire_results(surefire_dir)

            total = len(test_cases)
            passed = sum(1 for tc in test_cases if tc.passed)
            failed = sum(1 for tc in test_cases if tc.failure is not None)
            errored = sum(1 for tc in test_cases if tc.error is not None)
            skipped = sum(1 for tc in test_cases if tc.skipped)

            # Parse JaCoCo report
            jacoco_xml = tmpdir / "target" / "site" / "jacoco" / "jacoco.xml"
            if not jacoco_xml.exists() and effective_pom_has_jacoco:
                report_generated = await self._try_generate_jacoco_report(
                    tmpdir,
                    maven_cmd,
                    test_returncode=returncode,
                    total_tests=total,
                    failed_tests=failed,
                    error_tests=errored,
                )
                if report_generated:
                    logger.info("  JaCoCo report generated in a follow-up Maven step")
            line_cov, branch_cov, class_coverage, method_coverage = self._parse_jacoco_report(jacoco_xml)
            coverage_source = "jacoco" if line_cov is not None else "fallback"

            if line_cov is not None:
                logger.info(f"  📊 JaCoCo: line={line_cov:.1f}% branch={branch_cov:.1f}%")
            else:
                logger.warning("  ⚠️  jacoco.xml not found — coverage not measured")

            success = returncode == 0
            failure_type = None if success else self._classify_test_failure(
                output=output,
                returncode=returncode,
                failed_tests=failed,
                error_tests=errored,
                total_tests=total,
                surefire_report_issue=surefire_report_issue,
            )
            if not success:
                logger.warning(
                    f"  ❌ mvn test failed: {failed} failures, {errored} errors"
                    f" (type={failure_type or 'unknown'})"
                )
                if test_cases:
                    failing_names = [
                        f"{tc.classname}.{tc.name}"
                        for tc in test_cases
                        if not tc.passed
                    ]
                    if failing_names:
                        logger.warning(
                            "     → failing tests: " + ", ".join(failing_names[:8])
                        )
                if failure_type == "test_compilation_failure":
                    compile_like_errors = self._parse_errors(output)
                    if compile_like_errors:
                        for err in compile_like_errors[:8]:
                            logger.warning(f"     → {err}")
                    else:
                        for line in self._extract_relevant_test_failure_lines(output)[:8]:
                            logger.warning(f"     → {line}")
            else:
                logger.info(f"  ✅ Tests passed: {passed}/{total}")

            return TestRunResult(
                success=success,
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                error_tests=errored,
                skipped_tests=skipped,
                test_cases=test_cases,
                line_coverage=line_cov,
                branch_coverage=branch_cov,
                class_coverage=class_coverage,
                method_coverage=method_coverage,
                duration_seconds=duration,
                coverage_source=coverage_source,
                jacoco_report_path=str(jacoco_xml) if jacoco_xml.exists() else None,
                workspace_path=str(tmpdir),
                written_test_files=written_tests,
                effective_pom_has_jacoco=effective_pom_has_jacoco,
                failure_type=failure_type,
                return_code=returncode,
                surefire_report_issue=surefire_report_issue,
                output=output[:8000],
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _try_generate_jacoco_report(
        self,
        project_dir: Path,
        maven_cmd: str,
        test_returncode: int,
        total_tests: int,
        failed_tests: int,
        error_tests: int,
    ) -> bool:
        jacoco_xml = project_dir / "target" / "site" / "jacoco" / "jacoco.xml"
        jacoco_exec = project_dir / "target" / "jacoco.exec"
        if jacoco_xml.exists():
            return True
        if not jacoco_exec.exists():
            logger.warning("  JaCoCo exec data not found after mvn test — report cannot be generated")
            return False

        logger.info(
            "  Attempting standalone JaCoCo report generation after mvn test "
            f"(rc={test_returncode}, tests={total_tests}, failures={failed_tests}, errors={error_tests})"
        )
        report_returncode, report_output = await self._run_raw(
            project_dir,
            maven_cmd,
            ["jacoco:report", "-DskipTests", "--no-transfer-progress"],
        )
        if report_returncode == 0 and jacoco_xml.exists():
            return True

        logger.warning(
            "  Standalone JaCoCo report generation failed "
            f"(rc={report_returncode})"
        )
        for line in self._extract_relevant_test_failure_lines(report_output)[:6]:
            logger.warning(f"     → {line}")
        return jacoco_xml.exists()

    # ──────────────────────────────────────────────────────────────
    #  File writers
    # ──────────────────────────────────────────────────────────────

    def _write_main_sources(self, generated_code: GeneratedCode, project_dir: Path) -> List[str]:
        """Write pom.xml + src/main files."""
        pom = self._ensure_jacoco_plugin(generated_code.pom_xml or self._minimal_pom())
        (project_dir / "pom.xml").write_text(pom, encoding="utf-8")

        count = 0
        written: List[str] = []
        for file_path, content in generated_code.files.items():
            normalized = file_path.replace("\\", "/")
            if normalized.startswith("src/test/"):
                continue
            if not (
                normalized.endswith(".java")
                or normalized.startswith("src/main/resources/")
                or normalized.startswith("src/main/java/")
            ):
                continue
            dest = project_dir / normalized if normalized.startswith("src/") else (
                project_dir / "src" / "main" / "java" / normalized
                if normalized.endswith(".java")
                else project_dir / "src" / "main" / "resources" / normalized
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            count += 1
            written.append(dest.relative_to(project_dir).as_posix())

        logger.info(f"  📝 {count} main source file(s) written")

        return written

    def _write_test_sources(self, test_files: Dict[str, str], project_dir: Path) -> List[str]:
        """Write src/test files."""
        count = 0
        written: List[str] = []
        for file_path, content in test_files.items():
            if not str(content or "").strip():
                logger.warning(f"  Skipping empty test source: {file_path}")
                continue
            normalized = file_path.replace("\\", "/")
            if normalized.startswith("src/main/java/"):
                normalized = "src/test/java/" + normalized[len("src/main/java/") :]
            elif normalized.startswith("main/java/"):
                normalized = "src/test/java/" + normalized[len("main/java/") :]
            elif normalized.startswith("java/"):
                normalized = "src/test/java/" + normalized[len("java/") :]
            elif not normalized.startswith("src/test/"):
                normalized = f"src/test/java/{normalized.lstrip('/')}"
            dest = project_dir / normalized
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            count += 1
            written.append(dest.relative_to(project_dir).as_posix())
        logger.info(f"  Wrote {count} test source file(s)")
        return written

    # Result parsers

    def _pom_has_jacoco(self, pom_path: Path) -> bool:
        if not pom_path.exists():
            return False
        raw = pom_path.read_text(encoding="utf-8", errors="replace")
        return all(
            token in raw
            for token in (
                "<artifactId>jacoco-maven-plugin</artifactId>",
                "<goal>prepare-agent</goal>",
                "<goal>report</goal>",
            )
        )

    def _ensure_jacoco_plugin(self, pom_xml: str) -> str:
        if (
            "<artifactId>jacoco-maven-plugin</artifactId>" in pom_xml
            and "<goal>prepare-agent</goal>" in pom_xml
            and "<goal>report</goal>" in pom_xml
        ):
            return pom_xml

        plugin = (
            "            <plugin>\n"
            "                <groupId>org.jacoco</groupId>\n"
            "                <artifactId>jacoco-maven-plugin</artifactId>\n"
            "                <version>0.8.11</version>\n"
            "                <executions>\n"
            "                    <execution>\n"
            "                        <goals>\n"
            "                            <goal>prepare-agent</goal>\n"
            "                        </goals>\n"
            "                    </execution>\n"
            "                    <execution>\n"
            "                        <id>report</id>\n"
            "                        <phase>test</phase>\n"
            "                        <goals>\n"
            "                            <goal>report</goal>\n"
            "                        </goals>\n"
            "                    </execution>\n"
            "                </executions>\n"
            "            </plugin>\n"
        )

        if "</plugins>" in pom_xml:
            return pom_xml.replace("</plugins>", f"{plugin}        </plugins>", 1)
        if "<build>" in pom_xml:
            return pom_xml.replace("<build>", f"<build>\n        <plugins>\n{plugin}        </plugins>", 1)
        return pom_xml.replace(
            "</project>",
            f"    <build>\n        <plugins>\n{plugin}        </plugins>\n    </build>\n</project>",
            1,
        )

    def _parse_surefire_results(
        self,
        surefire_dir: Path,
    ) -> tuple[List[SurefireTestCase], Optional[str]]:
        """Parse all TEST-*.xml files from the Surefire reports directory."""
        test_cases: List[SurefireTestCase] = []
        if not surefire_dir.exists():
            logger.warning(f"  ⚠️  Surefire reports dir not found: {surefire_dir}")
            return test_cases, "missing_or_unreadable_test_report"

        parse_failed = False
        for xml_file in surefire_dir.glob("TEST-*.xml"):
            try:
                tree = ElementTree.parse(xml_file)
                root = tree.getroot()
                for tc_elem in root.findall("testcase"):
                    classname = tc_elem.get("classname", "")
                    name = tc_elem.get("name", "")
                    time_s = float(tc_elem.get("time", "0") or "0")

                    failure = tc_elem.findtext("failure")
                    error = tc_elem.findtext("error")
                    skipped = tc_elem.find("skipped") is not None

                    test_cases.append(SurefireTestCase(
                        classname=classname,
                        name=name,
                        time_seconds=time_s,
                        failure=failure,
                        error=error,
                        skipped=skipped,
                    ))
            except Exception as e:
                logger.warning(f"  ⚠️  Failed to parse {xml_file.name}: {e}")
                parse_failed = True

        if parse_failed:
            return test_cases, "missing_or_unreadable_test_report"
        if not test_cases and not any(surefire_dir.glob("TEST-*.xml")):
            return test_cases, "missing_or_unreadable_test_report"
        return test_cases, None

    def _parse_jacoco_report(
        self, jacoco_xml: Path
    ) -> tuple[Optional[float], Optional[float], List[Dict[str, object]], List[Dict[str, object]]]:
        """
        Parse jacoco.xml and return (line_coverage%, branch_coverage%).
        Returns (None, None) if the file does not exist.

        JaCoCo XML root-level counters give project-wide coverage.
        """
        if not jacoco_xml.exists():
            return None, None, [], []

        try:
            # JaCoCo DOCTYPE causes issues with standard parser — strip it
            raw = jacoco_xml.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
            root = ElementTree.fromstring(raw)

            line_cov = branch_cov = None
            class_coverage: List[Dict[str, object]] = []
            method_coverage: List[Dict[str, object]] = []
            for counter in root.findall("counter"):
                ctype = counter.get("type", "")
                missed = int(counter.get("missed", "0"))
                covered = int(counter.get("covered", "0"))
                total = missed + covered
                if total == 0:
                    continue
                pct = round(covered / total * 100, 1)
                if ctype == "LINE":
                    line_cov = pct
                elif ctype == "BRANCH":
                    branch_cov = pct

            for package_elem in root.findall("package"):
                package_name = (package_elem.get("name", "") or "").replace("/", ".")
                for class_elem in package_elem.findall("class"):
                    raw_name = class_elem.get("name", "") or ""
                    fqcn = raw_name.replace("/", ".")
                    class_name = fqcn.rsplit(".", 1)[-1] if fqcn else ""
                    if not class_name or "$" in class_name:
                        continue

                    class_line_cov = None
                    class_branch_cov = None
                    covered_lines = missed_lines = covered_branches = missed_branches = 0
                    for counter in class_elem.findall("counter"):
                        ctype = counter.get("type", "")
                        missed = int(counter.get("missed", "0"))
                        covered = int(counter.get("covered", "0"))
                        total = missed + covered
                        if ctype == "LINE":
                            missed_lines = missed
                            covered_lines = covered
                            class_line_cov = round(covered / total * 100, 1) if total > 0 else None
                        elif ctype == "BRANCH":
                            missed_branches = missed
                            covered_branches = covered
                            class_branch_cov = round(covered / total * 100, 1) if total > 0 else None

                    class_coverage.append({
                        "package_name": package_name,
                        "class_name": class_name,
                        "fqcn": fqcn,
                        "line_coverage": class_line_cov,
                        "branch_coverage": class_branch_cov,
                        "covered_lines": covered_lines,
                        "missed_lines": missed_lines,
                        "covered_branches": covered_branches,
                        "missed_branches": missed_branches,
                    })

                    for method_elem in class_elem.findall("method"):
                        method_name = method_elem.get("name", "") or ""
                        if not method_name or method_name == "<init>":
                            continue

                        method_line_cov = None
                        method_branch_cov = None
                        method_covered_lines = method_missed_lines = 0
                        method_covered_branches = method_missed_branches = 0
                        for counter in method_elem.findall("counter"):
                            ctype = counter.get("type", "")
                            missed = int(counter.get("missed", "0"))
                            covered = int(counter.get("covered", "0"))
                            total = missed + covered
                            if ctype == "LINE":
                                method_missed_lines = missed
                                method_covered_lines = covered
                                method_line_cov = round(covered / total * 100, 1) if total > 0 else None
                            elif ctype == "BRANCH":
                                method_missed_branches = missed
                                method_covered_branches = covered
                                method_branch_cov = round(covered / total * 100, 1) if total > 0 else None

                        method_coverage.append({
                            "fqcn": fqcn,
                            "class_name": class_name,
                            "method_name": method_name,
                            "line_coverage": method_line_cov,
                            "branch_coverage": method_branch_cov,
                            "covered_lines": method_covered_lines,
                            "missed_lines": method_missed_lines,
                            "covered_branches": method_covered_branches,
                            "missed_branches": method_missed_branches,
                        })

            class_coverage.sort(
                key=lambda item: (
                    item.get("line_coverage") is None,
                    item.get("line_coverage") if item.get("line_coverage") is not None else 101.0,
                    str(item.get("fqcn", "")),
                )
            )
            method_coverage.sort(
                key=lambda item: (
                    item.get("branch_coverage") is None,
                    item.get("branch_coverage") if item.get("branch_coverage") is not None else 101.0,
                    item.get("line_coverage") if item.get("line_coverage") is not None else 101.0,
                    str(item.get("fqcn", "")),
                    str(item.get("method_name", "")),
                )
            )
            return line_cov, branch_cov, class_coverage, method_coverage

        except Exception as e:
            logger.warning(f"  ⚠️  Failed to parse jacoco.xml: {e}")
            return None, None, [], []

    # ──────────────────────────────────────────────────────────────
    #  Maven runners
    # ──────────────────────────────────────────────────────────────

    async def _run(self, project_dir: Path, maven_cmd: str, goals: List[str]) -> CompileResult:
        """Run Maven goals and return a CompileResult."""
        returncode, output = await self._run_raw(project_dir, maven_cmd, goals)
        errors = self._parse_errors(output)
        success = returncode == 0 or (len(errors) == 0 and returncode == 0)
        failure_type = None
        # Recheck: if returncode non-zero but no structured errors found, still fail
        if returncode != 0 and not errors:
            errors = [CompileError(
                file="build",
                line=0,
                message=f"Maven exited with code {returncode}. Check output.",
                code_snippet=output[-500:] if output else "",
            )]
            success = False
        if not success:
            failure_type = self._classify_compile_failure(output, returncode, errors)
        return CompileResult(
            success=success,
            errors=errors,
            output=output,
            failure_type=failure_type,
            return_code=returncode,
        )

    async def _run_raw(
        self, project_dir: Path, maven_cmd: str, goals: List[str]
    ) -> tuple[int, str]:
        """Run Maven and return (returncode, combined_output)."""
        try:
            self.maven_local_repo_dir.mkdir(parents=True, exist_ok=True)
            completed = await asyncio.to_thread(
                subprocess.run,
                [
                    maven_cmd,
                    f"-Dmaven.repo.local={self.maven_local_repo_dir}",
                    *goals,
                ],
                cwd=str(project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
            )
            output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
            return completed.returncode, output

        except subprocess.TimeoutExpired:
            logger.error(
                f"  ⏰ Maven test timeout | timeout_seconds={self.timeout} "
                f"| cwd={project_dir} | goals={goals}"
            )
            return -1, (
                f"Maven test timeout after {self.timeout}s\n"
                f"command: {maven_cmd} {' '.join(goals)}\n"
                f"working_dir: {project_dir}\n"
                f"timeout_seconds: {self.timeout}\n"
                f"exit_code: -1\n"
            )

        except FileNotFoundError:
            return -1, "mvn not found in PATH"

    def _parse_errors(self, output: str) -> List[CompileError]:
        """Parse Maven compiler output for Java errors."""
        errors = []
        patterns = [
            re.compile(r"\[ERROR\]\s+(.+?\.java):\[(\d+),\d+\]\s+(.+)"),
            re.compile(r"(.+?\.java):(\d+):\s+error:\s+(.+)"),
            re.compile(r"\[ERROR\]\s+(.+?\.java):(\d+):\s+(.+)"),
            re.compile(r"ERROR in (.+?\.java) \(at line (\d+)\)"),
        ]
        seen = set()
        for line in output.splitlines():
            for pat in patterns:
                m = pat.search(line)
                if m:
                    file_path = Path(m.group(1)).name
                    line_num = int(m.group(2)) if len(m.groups()) >= 2 else 0
                    message = m.group(3).strip() if len(m.groups()) >= 3 else line.strip()
                    key = (file_path, line_num, message)
                    if key not in seen:
                        seen.add(key)
                        errors.append(CompileError(file=file_path, line=line_num, message=message))
                    break
        return errors

    def _classify_compile_failure(
        self,
        output: str,
        returncode: int,
        errors: List[CompileError],
    ) -> str:
        if errors and any(err.file.endswith(".java") for err in errors):
            return "java_compilation_failure"

        # Fallback: check raw output for Java compile error signals even when
        # the structured regex didn't match (different Maven output formats).
        java_error_signals = (
            "error:",
            "cannot find symbol",
            "package does not exist",
            "incompatible types",
            "method does not override",
            "variable might not have been initialized",
            "unreported exception",
            "class, interface, or enum expected",
            ".java:",
        )
        lowered = output.lower()
        if any(sig in lowered for sig in java_error_signals):
            return "java_compilation_failure"

        environment_markers = (
            "mvn not found",
            "java_home",
            "java home",
            "jdk",
            "toolchain",
            "unsupported class file major version",
            "invalid target release",
            "could not resolve dependencies",
            "could not find artifact",
            "non-resolvable parent pom",
            "pluginresolutionexception",
            "dependencyresolutionexception",
            "transfer failed",
            "unknown host",
            "connection timed out",
            "connection reset",
            "read timed out",
            "pkix path building failed",
            "unable to access jarfile",
            "timeout after",
        )
        if returncode == -1 or any(marker in lowered for marker in environment_markers):
            return "environment_or_dependency_failure"

        return "maven_or_build_tool_failure"

    def _classify_test_failure(
        self,
        output: str,
        returncode: int,
        failed_tests: int,
        error_tests: int,
        total_tests: int,
        surefire_report_issue: Optional[str],
    ) -> str:
        lowered = output.lower()
        test_compile_markers = (
            "failed to execute goal org.apache.maven.plugins:maven-compiler-plugin",
            "default-testcompile",
            "compilation failure",
            "compilation error",
            "testcompile",
        )
        environment_markers = (
            "mvn not found",
            "java_home",
            "java home",
            "jdk",
            "toolchain",
            "could not resolve dependencies",
            "could not find artifact",
            "non-resolvable parent pom",
            "dependencyresolutionexception",
            "pluginresolutionexception",
            "transfer failed",
            "unknown host",
            "connection timed out",
            "connection reset",
            "read timed out",
            "pkix path building failed",
            "timeout after",
            "could not create local repository",
            "localrepositorynotaccessibleexception",
            "access is denied",
            "accès refusé",
        )
        if returncode == -1:
            if "timeout" in output.lower():
                return "maven_test_timeout"
            return "test_environment_or_dependency_failure"
        if failed_tests > 0:
            return "test_assertion_failure"
        if error_tests > 0:
            return "test_execution_failure"
        if returncode != 0 and any(marker in lowered for marker in test_compile_markers):
            return "test_compilation_failure"
        if any(marker in lowered for marker in environment_markers):
            return "test_environment_or_dependency_failure"
        if surefire_report_issue:
            return "missing_or_unreadable_test_report"

        tooling_markers = (
            "surefirebooterforkexception",
            "there are test failures",
            "failed to execute goal",
            "maven-surefire-plugin",
            "forked process",
            "junitplatform",
            "tests run: 0",
        )
        if returncode != 0 and (total_tests == 0 or any(marker in lowered for marker in tooling_markers)):
            return "test_tooling_failure"

        return "test_execution_failure"

    def _extract_relevant_test_failure_lines(self, output: str) -> List[str]:
        relevant = []
        seen = set()
        for raw_line in output.splitlines():
            line = raw_line.strip()
            lowered = line.lower()
            if not line:
                continue
            if any(
                marker in lowered
                for marker in (
                    "[error]",
                    "compilation failure",
                    "compilation error",
                    "cannot find symbol",
                    "symbol:",
                    "location:",
                    "failed to execute goal",
                    "default-testcompile",
                )
            ):
                if line not in seen:
                    seen.add(line)
                    relevant.append(line)
        return relevant

    # ──────────────────────────────────────────────────────────────
    #  Maven resolution
    # ──────────────────────────────────────────────────────────────

    async def _resolve_maven(self) -> Optional[str]:
        if self._resolved_cmd:
            return self._resolved_cmd
        if await self._maven_available():
            self._resolved_cmd = self.maven_cmd
            return self.maven_cmd
        embedded = await asyncio.to_thread(self._ensure_embedded_maven)
        if embedded:
            logger.info(f"  📦 Embedded Maven: {embedded}")
            self._resolved_cmd = embedded
        return embedded

    async def _maven_available(self) -> bool:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [self.maven_cmd, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            return completed.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _ensure_embedded_maven(self) -> Optional[str]:
        version = os.getenv("MAVEN_VERSION", self.MAVEN_VERSION)
        dist_name = f"apache-maven-{version}"
        bin_name = "mvn.cmd" if os.name == "nt" else "mvn"
        maven_bin = self.maven_embedded_dir / dist_name / "bin" / bin_name

        if maven_bin.exists():
            return str(maven_bin)

        self.maven_embedded_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.maven_embedded_dir / f"{dist_name}-bin.zip"
        download_url = (
            f"https://archive.apache.org/dist/maven/maven-3/{version}/binaries/"
            f"{dist_name}-bin.zip"
        )
        try:
            logger.info(f"  ⬇️  Downloading embedded Maven: {download_url}")
            urllib.request.urlretrieve(download_url, archive_path)
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(self.maven_embedded_dir)
            archive_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"  ⚠️  Cannot install embedded Maven: {e}")
            return None

        return str(maven_bin) if maven_bin.exists() else None

    def _maven_unavailable_result(self) -> CompileResult:
        return CompileResult(
            success=False,
            output="Maven not available",
            failure_type="environment_or_dependency_failure",
            return_code=-1,
            errors=[CompileError(file="pom.xml", line=0, message="Maven not found in PATH or embedded")],
        )

    def _minimal_pom(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>generated-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>21</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.11</version>
                <executions>
                    <execution><goals><goal>prepare-agent</goal></goals></execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals><goal>report</goal></goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>"""


# ─────────────────────────────────────────────
#  Backward-compatible alias
# ─────────────────────────────────────────────

class MavenCompiler(MavenBuildRunner):
    """
    Backward-compatible alias for MavenBuildRunner.
    The compile() method delegates to compile_main().
    """

    async def compile(self, generated_code: GeneratedCode) -> CompileResult:
        return await self.compile_main(generated_code)
