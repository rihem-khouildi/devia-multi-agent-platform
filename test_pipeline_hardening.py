import io
import json
import logging
import os
import tempfile
import subprocess
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.analyzer import RepositoryAnalyzerAgent
from agents.developer import DeveloperAgent
from agents.planner import PlannerAgent
from agents.reviewer import ReviewResult
from config.settings import Settings
from core.maven_compiler import CompileResult, TestRunResult
from core.models import (
    AnalysisResult,
    Entity,
    Endpoint,
    GeneratedCode,
    PipelineState,
    PlanResult,
    RepoAnalysis,
    StoryCoverageReport,
    StoryScope,
    SubTask,
    TestResult,
    UserStory,
)
from core.pipeline import SDLCPipeline
import main as main_entry


class PipelineHardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.output_dir = root / "output"
        self.artifacts_dir = root / "artifacts"
        self.logs_dir = root / "logs"
        self.docs_dir = root / "docs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        self._env_backup = {
            key: os.environ.get(key)
            for key in ("OUTPUT_DIR", "ARTIFACTS_DIR", "LOGS_DIR", "DOCS_DIR", "PIPELINE_DEBUG_CRASH_AFTER")
        }
        os.environ["OUTPUT_DIR"] = str(self.output_dir)
        os.environ["ARTIFACTS_DIR"] = str(self.artifacts_dir)
        os.environ["LOGS_DIR"] = str(self.logs_dir)
        os.environ["DOCS_DIR"] = str(self.docs_dir)
        os.environ.pop("PIPELINE_DEBUG_CRASH_AFTER", None)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def _settings(self):
        return Settings()

    def _make_story(self) -> UserStory:
        return UserStory(
            id="US-TEST",
            title="Story",
            description="Desc",
            acceptance_criteria=["A"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )

    def _make_analysis(self) -> AnalysisResult:
        return AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="GET", path="/api/demo", description="demo")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Demo",
            dependencies=[],
            business_rules=[],
        )

    def _make_repo_analysis(self) -> RepoAnalysis:
        return RepoAnalysis(
            repo_path=str(self.output_dir),
            languages=["java"],
            frameworks=["spring-boot"],
            build_system="maven",
            build_commands={"compile": "mvn compile", "test": "mvn test"},
            entry_points=[],
            relevant_files=[],
            potentially_impacted=[],
            existing_patterns=[],
            change_map={},
            risks=[],
            summary="repo",
        )

    def _make_plan(self) -> PlanResult:
        return PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Code",
                    description="Generate code",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/Application.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                )
            ],
            execution_groups=[["task-1"]],
            risks=[],
            summary="plan",
        )

    def _make_generated_code(self) -> GeneratedCode:
        return GeneratedCode(
            files={
                "src/main/java/com/example/app/Application.java": (
                    "package com.example.app;\n"
                    "public class Application {}\n"
                ),
                "src/main/java/com/example/app/controller/DemoController.java": (
                    "package com.example.app.controller;\n"
                    "import org.springframework.web.bind.annotation.GetMapping;\n"
                    "import org.springframework.web.bind.annotation.RestController;\n"
                    "@RestController\n"
                    "public class DemoController {\n"
                    "    @GetMapping(\"/api/demo\")\n"
                    "    public String demo() { return \"ok\"; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

    def _make_quality_problem_code(self) -> GeneratedCode:
        duplicated_block = "\n".join(
            [
                '        String status = "OK";',
                '        String message = "hello";',
                "        if (status != null && message != null) {",
                '            return status + message;',
                "        }",
                '        return "fallback";',
            ]
        )
        return GeneratedCode(
            files={
                "src/main/java/com/example/app/Application.java": (
                    "package com.example.app;\n"
                    "public class Application {}\n"
                ),
                "src/main/java/com/example/app/BadService.java": (
                    "package com.example.app;\n"
                    "import org.springframework.beans.factory.annotation.Autowired;\n"
                    "public class BadService {\n"
                    "    @Autowired\n"
                    "    private Dependency dependency;\n"
                    "    public String alpha() {\n"
                    f"{duplicated_block}\n"
                    "    }\n"
                    "    public String beta() {\n"
                    f"{duplicated_block}\n"
                    "    }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

    def _make_repo_file(self, relative_path: str, content: str) -> Path:
        full_path = self.output_dir / "repo-under-test" / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return full_path

    def test_deterministic_compile_fixes_sync_missing_model_fields_from_service_usage(self):
        pipeline = SDLCPipeline(self._settings())
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/entity/User.java": (
                    "package com.example.app.entity;\n\n"
                    "import lombok.AllArgsConstructor;\n"
                    "import lombok.Builder;\n"
                    "import lombok.Data;\n"
                    "import lombok.NoArgsConstructor;\n\n"
                    "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                    "public class User {\n"
                    "    private Long id;\n"
                    "    private String name;\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/dto/UserRequest.java": (
                    "package com.example.app.dto;\n\n"
                    "import lombok.AllArgsConstructor;\n"
                    "import lombok.Builder;\n"
                    "import lombok.Data;\n"
                    "import lombok.NoArgsConstructor;\n\n"
                    "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                    "public class UserRequest {\n"
                    "    private String name;\n"
                    "    private String username;\n"
                    "    private String email;\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/dto/UserResponse.java": (
                    "package com.example.app.dto;\n\n"
                    "import lombok.AllArgsConstructor;\n"
                    "import lombok.Builder;\n"
                    "import lombok.Data;\n"
                    "import lombok.NoArgsConstructor;\n\n"
                    "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                    "public class UserResponse {\n"
                    "    private String name;\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/service/impl/UserServiceImpl.java": (
                    "package com.example.app.service.impl;\n\n"
                    "import com.example.app.dto.UserRequest;\n"
                    "import com.example.app.dto.UserResponse;\n"
                    "import com.example.app.entity.User;\n\n"
                    "public class UserServiceImpl {\n"
                    "    public UserResponse mapToResponse(User user) {\n"
                    "        return UserResponse.builder()\n"
                    "            .id(user.getId())\n"
                    "            .name(user.getName())\n"
                    "            .username(user.getUsername())\n"
                    "            .email(user.getEmail())\n"
                    "            .build();\n"
                    "    }\n\n"
                    "    public User mapToEntity(UserRequest request) {\n"
                    "        User user = new User();\n"
                    "        user.setName(request.getName());\n"
                    "        user.setUsername(request.getUsername());\n"
                    "        user.setEmail(request.getEmail());\n"
                    "        return user;\n"
                    "    }\n"
                    "}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        fixed_code, fix_count = pipeline._apply_deterministic_compile_fixes(generated_code)

        self.assertGreaterEqual(fix_count, 4)
        self.assertIn("private String username;", fixed_code.files["src/main/java/com/example/app/entity/User.java"])
        self.assertIn("private String email;", fixed_code.files["src/main/java/com/example/app/entity/User.java"])
        self.assertIn("private Long id;", fixed_code.files["src/main/java/com/example/app/dto/UserResponse.java"])
        self.assertIn("private String username;", fixed_code.files["src/main/java/com/example/app/dto/UserResponse.java"])
        self.assertIn("private String email;", fixed_code.files["src/main/java/com/example/app/dto/UserResponse.java"])

    def _wire_basic_pipeline(self, pipeline: SDLCPipeline, generated_code: GeneratedCode | None = None):
        story = self._make_story()
        analysis = self._make_analysis()
        repo_analysis = self._make_repo_analysis()
        plan = self._make_plan()
        code = generated_code or self._make_generated_code()

        pipeline._resolve_user_story = AsyncMock(return_value=story)
        pipeline.doc_loader.load_all = AsyncMock(return_value={})
        pipeline.advisor.analyze = AsyncMock(return_value=analysis)
        pipeline.analyzer.analyze = AsyncMock(return_value=repo_analysis)
        pipeline.planner.plan = AsyncMock(return_value=plan)
        pipeline.developer.generate_from_plan = AsyncMock(return_value=code)
        pipeline._compile_with_precheck = AsyncMock(return_value=(code, CompileResult(success=True, errors=[])))
        pipeline._review_and_correct = AsyncMock(return_value=(ReviewResult(score=90, approved=True, summary="ok"), code))
        return story, analysis, repo_analysis, plan, code

    def _make_resume_state(self, pipeline: SDLCPipeline, include_compile: bool) -> None:
        story = self._make_story()
        analysis = self._make_analysis()
        repo_analysis = self._make_repo_analysis()
        plan = self._make_plan()
        code = self._make_generated_code()

        state = PipelineState(user_story_id=story.id)
        state.artifacts["user_story"] = {
            "id": story.id,
            "title": story.title,
            "description": story.description,
            "acceptance_criteria": story.acceptance_criteria,
            "priority": story.priority,
            "story_points": story.story_points,
            "labels": story.labels,
            "epic": story.epic,
            "raw": story.raw,
        }
        state.artifacts["analysis"] = analysis.to_dict()
        state.artifacts["repo_analysis"] = repo_analysis.to_dict()
        state.artifacts["plan"] = plan.to_dict()
        state.artifacts["generated_code"] = pipeline._generated_code_to_dict(code)
        state.artifacts["generated_files"] = list(code.files.keys())

        for step in ("resolve_user_story", "load_docs", "advisor", "analyzer", "planner", "developer"):
            state.mark_completed(step)

        pipeline._save_generated_code_artifact(story.id, code)

        if include_compile:
            compile_report = CompileResult(success=True, errors=[]).to_dict()
            state.artifacts["compile_report"] = compile_report
            state.artifacts["compile_success"] = True
            state.artifacts["compile_errors"] = 0
            state.mark_completed("compile")
            pipeline._save_artifact("compile_report.json", compile_report)

        pipeline._save_state(state)

    async def test_resume_from_tester_uses_checkpointed_plan_and_code(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        self._make_resume_state(pipeline, include_compile=True)

        pipeline.doc_loader.load_all = AsyncMock(return_value={})
        pipeline.developer.generate_from_plan = AsyncMock(side_effect=AssertionError("developer should not regenerate"))
        pipeline.advisor.analyze = AsyncMock(side_effect=AssertionError("advisor should not rerun"))
        pipeline.analyzer.analyze = AsyncMock(side_effect=AssertionError("analyzer should not rerun"))
        pipeline.planner.plan = AsyncMock(side_effect=AssertionError("planner should not rerun"))
        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=42.0,
            passed=True,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=91.0,
            branch_coverage=80.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(
            ReviewResult(score=90, approved=True, summary="ok"),
            pipeline._restore_generated_code(PipelineState(user_story_id="x"), "US-TEST")
        ))

        result = await pipeline.run(
            user_story_input="US-TEST",
            dry_run=True,
            repo_path=str(self.output_dir),
            resume=True,
            resume_from="tester",
        )

        self.assertEqual(result["coverage_source"], "jacoco")
        self.assertEqual(result["coverage_gate_mode"], "strict")
        self.assertTrue(result["coverage_ok"])
        pipeline.developer.generate_from_plan.assert_not_called()
        pipeline.advisor.analyze.assert_not_called()
        pipeline.analyzer.analyze.assert_not_called()
        pipeline.planner.plan.assert_not_called()
        pipeline.tester.test.assert_awaited_once()
        pipeline.build_runner.run_tests.assert_awaited_once()

    async def test_resume_from_tester_after_developer_fails_clearly_without_compile_artifact(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        self._make_resume_state(pipeline, include_compile=False)
        pipeline.doc_loader.load_all = AsyncMock(return_value={})

        with self.assertRaises(FileNotFoundError) as ctx:
            await pipeline.run(
                user_story_input="US-TEST",
                dry_run=True,
                repo_path=str(self.output_dir),
                resume=True,
                resume_from="tester",
            )

        self.assertIn("compile_report", str(ctx.exception))

    async def test_pipeline_bootstraps_without_repo_path(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, code = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=42.0,
            passed=True,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=85.0,
            branch_coverage=70.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(ReviewResult(score=90, approved=True, summary="ok"), code))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=None,
        )

        self.assertTrue(result["compile_success"])
        pipeline.analyzer.analyze.assert_not_called()
        pipeline.developer.generate_from_plan.assert_awaited_once()

    def test_load_existing_project_code_preserves_repo_files(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        repo_root = self.output_dir / "repo-under-test"

        self._make_repo_file("pom.xml", "<project></project>")
        self._make_repo_file("README.md", "# Demo")
        self._make_repo_file(
            "src/main/java/com/example/app/Existing.java",
            "package com.example.app;\nclass Existing {}\n",
        )
        self._make_repo_file(
            "src/test/java/com/example/app/ExistingTest.java",
            "class ExistingTest {}\n",
        )
        self._make_repo_file(
            "src/main/resources/application.properties",
            "spring.application.name=demo\n",
        )

        loaded = pipeline._load_existing_project_code(str(repo_root))

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.pom_xml, "<project></project>")
        self.assertEqual(loaded.readme, "# Demo")
        self.assertIn("src/main/java/com/example/app/Existing.java", loaded.files)
        self.assertIn("src/test/java/com/example/app/ExistingTest.java", loaded.files)
        self.assertIn("src/main/resources/application.properties", loaded.files)

    async def test_compile_failure_blocks_real_test_execution_and_routes_as_infrastructure(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        story = self._make_story()
        analysis = self._make_analysis()
        repo_analysis = self._make_repo_analysis()
        plan = self._make_plan()
        code = self._make_generated_code()

        pipeline._resolve_user_story = AsyncMock(return_value=story)
        pipeline.doc_loader.load_all = AsyncMock(return_value={})
        pipeline.advisor.analyze = AsyncMock(return_value=analysis)
        pipeline.analyzer.analyze = AsyncMock(return_value=repo_analysis)
        pipeline.planner.plan = AsyncMock(return_value=plan)
        pipeline.developer.generate_from_plan = AsyncMock(return_value=code)
        pipeline._compile_with_precheck = AsyncMock(return_value=(
            code,
            CompileResult(
                success=False,
                errors=[],
                failure_type="maven_or_build_tool_failure",
            ),
        ))
        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(side_effect=AssertionError("mvn test should be skipped"))
        pipeline._review_and_correct = AsyncMock(return_value=(ReviewResult(score=90, approved=True, summary="ok"), code))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertFalse(result["compile_success"])
        self.assertEqual(result["decision_route"], "maven_or_build_tool_failure")
        self.assertEqual(result["recommended_next_action"], "surface_infrastructure_blockage")
        self.assertTrue(result["pipeline_blocked"])
        pipeline.build_runner.run_tests.assert_not_called()

    async def test_review_score_threshold_is_treated_as_approved_in_quality_gate(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, code = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=91.0,
            branch_coverage=80.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(
            ReviewResult(score=80, approved=False, summary="score-only approval"),
            code,
        ))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertTrue(result["review_approved"])
        self.assertTrue(result["all_gates_passed"])
        self.assertTrue(result["quality_scan_passed"])

    async def test_test_assertion_failure_retries_once_and_uses_post_retry_result(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, code = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.developer.fix_compile_errors = AsyncMock(return_value=code)
        pipeline.build_runner.compile_main = AsyncMock(return_value=CompileResult(success=True, errors=[]))
        pipeline.build_runner.run_tests = AsyncMock(side_effect=[
            TestRunResult(
                success=False,
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                line_coverage=65.0,
                branch_coverage=50.0,
                coverage_source="jacoco",
                output="assertion failed",
                failure_type="test_assertion_failure",
                test_cases=[],
            ),
            TestRunResult(
                success=True,
                total_tests=1,
                passed_tests=1,
                line_coverage=92.0,
                branch_coverage=80.0,
                coverage_source="jacoco",
                output="ok",
                test_cases=[],
            ),
        ])

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertTrue(result["tests_passed"])
        self.assertTrue(result["coverage_ok"])
        self.assertEqual(result["test_coverage"], 92.0)
        self.assertEqual(result["coverage_source"], "jacoco")
        pipeline.developer.fix_compile_errors.assert_awaited_once()
        pipeline.build_runner.compile_main.assert_awaited_once()
        self.assertEqual(pipeline.build_runner.run_tests.await_count, 2)

    async def test_zero_tests_discovered_retries_once_and_uses_post_retry_result(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline)
        pipeline._validate_generated_code_alignment = lambda *args, **kwargs: {"passed": True, "issues": []}

        initial_tests = TestResult(
            coverage=40.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="initial",
        )
        regenerated_tests = TestResult(
            coverage=75.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationRetryTest.java": "class ApplicationRetryTest {}"},
            test_summary="retry",
        )
        pipeline.tester.test = AsyncMock(side_effect=[initial_tests, regenerated_tests])
        pipeline.build_runner.run_tests = AsyncMock(side_effect=[
            TestRunResult(
                success=True,
                total_tests=0,
                passed_tests=0,
                line_coverage=None,
                branch_coverage=None,
                coverage_source="fallback",
                output="no tests",
                test_cases=[],
            ),
            TestRunResult(
                success=True,
                total_tests=1,
                passed_tests=1,
                line_coverage=88.0,
                branch_coverage=70.0,
                coverage_source="jacoco",
                output="ok",
                test_cases=[],
            ),
        ])

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertFalse(result["zero_tests_discovered"])
        self.assertTrue(result["tests_validation_ok"])
        self.assertTrue(result["coverage_ok"])
        self.assertEqual(result["test_coverage"], 88.0)
        self.assertEqual(pipeline.tester.test.await_count, 2)
        self.assertEqual(pipeline.build_runner.run_tests.await_count, 2)

    async def test_failed_test_run_with_zero_reports_is_not_misclassified_as_zero_tests(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=40.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="initial",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=False,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            error_tests=0,
            line_coverage=None,
            branch_coverage=None,
            coverage_source="fallback",
            output="[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:testCompile",
            failure_type="test_compilation_failure",
            surefire_report_issue="missing_or_unreadable_test_report",
            test_cases=[],
        ))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertFalse(result["zero_tests_discovered"])
        self.assertEqual(result["decision_route"], "test_compilation_failure")
        self.assertEqual(result["recommended_next_action"], "test_logic_fix_path")
        self.assertFalse(result["pipeline_blocked"])

    def test_classify_test_failure_detects_test_compilation_errors(self):
        from core.maven_compiler import MavenBuildRunner

        runner = MavenBuildRunner()
        failure_type = runner._classify_test_failure(
            output=(
                "[ERROR] Failed to execute goal "
                "org.apache.maven.plugins:maven-compiler-plugin:3.11.0:testCompile "
                "(default-testCompile) on project demo: Compilation failure"
            ),
            returncode=1,
            failed_tests=0,
            error_tests=0,
            total_tests=0,
            surefire_report_issue="missing_or_unreadable_test_report",
        )

        self.assertEqual(failure_type, "test_compilation_failure")

    async def test_coverage_below_threshold_retries_once_and_uses_post_retry_result(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline)
        pipeline._validate_generated_code_alignment = lambda *args, **kwargs: {"passed": True, "issues": []}

        initial_tests = TestResult(
            coverage=60.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="initial",
        )
        improved_tests = TestResult(
            coverage=85.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationCoverageTest.java": "class ApplicationCoverageTest {}"},
            test_summary="improved",
        )
        pipeline.tester.test = AsyncMock(side_effect=[initial_tests, improved_tests])
        pipeline.build_runner.run_tests = AsyncMock(side_effect=[
            TestRunResult(
                success=True,
                total_tests=1,
                passed_tests=1,
                line_coverage=65.0,
                branch_coverage=50.0,
                coverage_source="jacoco",
                output="low coverage",
                test_cases=[],
            ),
            TestRunResult(
                success=True,
                total_tests=1,
                passed_tests=1,
                line_coverage=91.0,
                branch_coverage=72.0,
                coverage_source="jacoco",
                output="improved coverage",
                test_cases=[],
            ),
        ])

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertTrue(result["tests_passed"])
        self.assertTrue(result["coverage_ok"])
        self.assertFalse(result["coverage_below_threshold"])
        self.assertEqual(result["test_coverage"], 91.0)
        self.assertEqual(result["coverage_source"], "jacoco")
        self.assertEqual(pipeline.tester.test.await_count, 2)
        self.assertEqual(pipeline.build_runner.run_tests.await_count, 2)
        self.assertEqual(pipeline.tester.test.await_args_list[1].kwargs["mode"], "coverage_retry_targeted")
        self.assertIsNotNone(pipeline.tester.test.await_args_list[1].kwargs["story_scope"])

    async def test_coverage_below_threshold_retries_twice_with_targeted_classes(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/ApplicationServiceImpl.java": (
                    "package com.example.app.service; public class ApplicationServiceImpl {}"
                ),
                "src/main/java/com/example/app/controller/ApplicationController.java": (
                    "package com.example.app.controller; public class ApplicationController {}"
                ),
                "src/main/java/com/example/app/repository/ApplicationRepository.java": (
                    "package com.example.app.repository; public interface ApplicationRepository {}"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline, generated_code=generated_code)
        pipeline._validate_generated_code_alignment = lambda *args, **kwargs: {"passed": True, "issues": []}

        initial_tests = TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="initial",
        )
        retry_one_tests = TestResult(
            coverage=68.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationCoverageRetryOneTest.java": "class ApplicationCoverageRetryOneTest {}"},
            test_summary="retry-one",
        )
        retry_two_tests = TestResult(
            coverage=84.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationCoverageRetryTwoTest.java": "class ApplicationCoverageRetryTwoTest {}"},
            test_summary="retry-two",
        )
        pipeline.tester.test = AsyncMock(side_effect=[initial_tests, retry_one_tests, retry_two_tests])
        pipeline.build_runner.run_tests = AsyncMock(side_effect=[
            TestRunResult(
                success=True,
                total_tests=2,
                passed_tests=2,
                line_coverage=61.0,
                branch_coverage=40.0,
                coverage_source="jacoco",
                class_coverage=[
                    {"class_name": "ApplicationServiceImpl", "line_coverage": 0.0},
                    {"class_name": "ApplicationController", "line_coverage": 0.0},
                ],
                output="low coverage 1",
                test_cases=[],
            ),
            TestRunResult(
                success=True,
                total_tests=3,
                passed_tests=3,
                line_coverage=69.0,
                branch_coverage=55.0,
                coverage_source="jacoco",
                class_coverage=[
                    {"class_name": "ApplicationController", "line_coverage": 0.0},
                    {"class_name": "ApplicationRepository", "line_coverage": 10.0},
                ],
                output="low coverage 2",
                test_cases=[],
            ),
            TestRunResult(
                success=True,
                total_tests=4,
                passed_tests=4,
                line_coverage=91.0,
                branch_coverage=76.0,
                coverage_source="jacoco",
                class_coverage=[
                    {"class_name": "ApplicationServiceImpl", "line_coverage": 90.0},
                    {"class_name": "ApplicationController", "line_coverage": 85.0},
                ],
                output="coverage improved",
                test_cases=[],
            ),
        ])

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertTrue(result["coverage_ok"])
        self.assertEqual(result["coverage_retry_attempts"], 2)
        self.assertEqual(
            result["coverage_target_classes"],
            ["ApplicationServiceImpl", "ApplicationController"],
        )
        self.assertEqual(pipeline.tester.test.await_count, 3)
        self.assertEqual(pipeline.build_runner.run_tests.await_count, 3)
        self.assertCountEqual(
            pipeline.tester.test.await_args_list[1].kwargs["target_classes"],
            ["ApplicationServiceImpl", "ApplicationController"],
        )
        self.assertEqual(
            pipeline.tester.test.await_args_list[1].kwargs["mode"],
            "coverage_retry_targeted",
        )
        self.assertCountEqual(
            pipeline.tester.test.await_args_list[2].kwargs["target_classes"],
            ["ApplicationServiceImpl", "ApplicationController"],
        )
        self.assertEqual(
            pipeline.tester.test.await_args_list[2].kwargs["mode"],
            "coverage_retry_targeted",
        )

    def test_select_low_coverage_targets_prioritizes_uncovered_business_classes(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/ApplicationServiceImpl.java": (
                    "package com.example.app.service; public class ApplicationServiceImpl {}"
                ),
                "src/main/java/com/example/app/controller/ApplicationController.java": (
                    "package com.example.app.controller; public class ApplicationController {}"
                ),
                "src/main/java/com/example/app/repository/ApplicationRepository.java": (
                    "package com.example.app.repository; public interface ApplicationRepository {}"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        run_result = TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=62.0,
            branch_coverage=40.0,
            coverage_source="jacoco",
            class_coverage=[
                {"class_name": "ApplicationController", "line_coverage": 0.0},
                {"class_name": "ApplicationRepository", "line_coverage": 15.0},
            ],
            test_cases=[],
        )

        targets = pipeline._select_low_coverage_targets(generated_code, run_result)

        self.assertEqual(targets[:2], ["ApplicationServiceImpl", "ApplicationController"])

    def test_parse_jacoco_report_exposes_class_level_coverage(self):
        from core.maven_compiler import MavenBuildRunner

        runner = MavenBuildRunner()
        jacoco_xml = self.artifacts_dir / "jacoco.xml"
        jacoco_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<report name="demo">
  <package name="com/example/app/service">
    <class name="com/example/app/service/ApplicationServiceImpl">
      <counter type="LINE" missed="10" covered="0"/>
      <counter type="BRANCH" missed="2" covered="0"/>
    </class>
  </package>
  <package name="com/example/app/controller">
    <class name="com/example/app/controller/ApplicationController">
      <counter type="LINE" missed="2" covered="8"/>
      <counter type="BRANCH" missed="1" covered="3"/>
    </class>
  </package>
  <counter type="LINE" missed="12" covered="8"/>
  <counter type="BRANCH" missed="3" covered="3"/>
</report>
""",
            encoding="utf-8",
        )

        line_cov, branch_cov, class_coverage, method_coverage = runner._parse_jacoco_report(jacoco_xml)

        self.assertEqual(line_cov, 40.0)
        self.assertEqual(branch_cov, 50.0)
        self.assertEqual(class_coverage[0]["class_name"], "ApplicationServiceImpl")
        self.assertEqual(class_coverage[0]["line_coverage"], 0.0)
        self.assertEqual(class_coverage[1]["class_name"], "ApplicationController")
        self.assertEqual(class_coverage[1]["line_coverage"], 80.0)
        self.assertEqual(method_coverage, [])

    def test_compute_story_scoped_coverage_ignores_out_of_scope_classes(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/ApplicationServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/ApplicationServiceImpl.java"],
            entrypoints=[],
            dependencies=[],
            excluded_files=["src/main/java/com/example/app/controller/LegacyController.java"],
            file_roles={"src/main/java/com/example/app/service/ApplicationServiceImpl.java": "service"},
        )
        run_result = TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            coverage_source="jacoco",
            class_coverage=[
                {"class_name": "ApplicationServiceImpl", "line_coverage": 40.0, "branch_coverage": 0.0},
                {"class_name": "LegacyController", "line_coverage": 100.0, "branch_coverage": 100.0},
            ],
        )

        report = pipeline.compute_story_scoped_coverage(run_result, story_scope)

        self.assertEqual(report.line_coverage, 40.0)
        self.assertEqual(len(report.scoped_classes), 1)
        self.assertEqual(report.scoped_classes[0]["class_name"], "ApplicationServiceImpl")

    def test_combine_test_files_excludes_legacy_repo_tests_when_story_scope_is_present(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/test/java/com/example/app/service/HelloWorldServiceTest.java": "class HelloWorldServiceTest {}",
                "src/main/java/com/example/app/service/AuthenticationServiceImpl.java": "class AuthenticationServiceImpl {}",
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={
                "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java": "class AuthenticationServiceImplTest {}",
            },
            test_summary="generated",
        )
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/AuthenticationServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/AuthenticationServiceImpl.java"],
            entrypoints=[],
            dependencies=[],
            excluded_files=["src/test/java/com/example/app/service/HelloWorldServiceTest.java"],
            file_roles={"src/main/java/com/example/app/service/AuthenticationServiceImpl.java": "service"},
        )

        combined = pipeline._combine_test_files(generated_code, test_result, story_scope)

        self.assertIn(
            "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java",
            combined,
        )
        self.assertNotIn(
            "src/test/java/com/example/app/service/HelloWorldServiceTest.java",
            combined,
        )

    def test_combine_test_files_keeps_coverage_safety_net_when_story_scope_is_present(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/AuthenticationServiceImpl.java": "class AuthenticationServiceImpl {}",
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={
                "src/test/java/com/example/app/CoverageSafetyNetTest.java": "class CoverageSafetyNetTest {}",
            },
            test_summary="generated",
        )
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/AuthenticationServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/AuthenticationServiceImpl.java"],
            entrypoints=[],
            dependencies=[],
            excluded_files=[],
            file_roles={"src/main/java/com/example/app/service/AuthenticationServiceImpl.java": "service"},
        )

        combined = pipeline._combine_test_files(generated_code, test_result, story_scope)

        self.assertIn(
            "src/test/java/com/example/app/CoverageSafetyNetTest.java",
            combined,
        )

    def test_prepare_test_files_for_execution_extracts_generated_files_metadata(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={},
            pom_xml="<project></project>",
            readme="demo",
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=[],
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={},
            test_summary="generated",
            metadata={
                "generated_files": [
                    {
                        "path": "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java",
                        "content": "package com.example.app.service;\nclass AuthenticationServiceImplTest {}\n",
                    }
                ]
            },
        )

        prepared = pipeline._prepare_test_files_for_execution(
            generated_code,
            test_result,
            analysis,
            story_scope=None,
        )

        self.assertIn(
            "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java",
            prepared,
        )

    def test_prepare_test_files_for_execution_injects_smoke_test_when_all_tests_are_empty(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={},
            pom_xml="<project></project>",
            readme="demo",
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=[],
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={
                "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java": "   ",
            },
            test_summary="generated",
        )

        prepared = pipeline._prepare_test_files_for_execution(
            generated_code,
            test_result,
            analysis,
            story_scope=None,
        )

        self.assertEqual(list(prepared.keys()), ["src/test/java/com/example/app/PipelineSmokeTest.java"])
        self.assertIn("smokeTest_compiles", prepared["src/test/java/com/example/app/PipelineSmokeTest.java"])

    def test_prepare_test_files_for_execution_excludes_unrelated_legacy_story_tests(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/test/java/com/example/app/service/HelloWorldServiceTest.java": (
                    "package com.example.app.service;\n"
                    "import com.example.app.service.impl.HelloWorldServiceImpl;\n"
                    "class HelloWorldServiceTest {}\n"
                ),
                "src/main/java/com/example/app/service/impl/UserServiceImpl.java": (
                    "package com.example.app.service.impl;\n"
                    "public class UserServiceImpl {}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        analysis = AnalysisResult(
            entities=[Entity(name="User", fields=[])],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="User",
            dependencies=[],
            business_rules=["email validation"],
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={
                "src/test/java/com/example/app/service/UserServiceImplTest.java": (
                    "package com.example.app.service;\n"
                    "import com.example.app.service.impl.UserServiceImpl;\n"
                    "class UserServiceImplTest {}\n"
                )
            },
            test_summary="generated",
        )
        story_scope = StoryScope(
            story_id="TEST-2",
            business_files=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            entrypoints=[],
            dependencies=[],
            excluded_files=["src/test/java/com/example/app/service/HelloWorldServiceTest.java"],
            new_files=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            modified_files=[],
            fixer_touched_files=[],
            file_roles={"src/main/java/com/example/app/service/impl/UserServiceImpl.java": "service"},
        )

        prepared = pipeline._prepare_test_files_for_execution(
            generated_code,
            test_result,
            analysis,
            story_scope=story_scope,
        )

        self.assertIn("src/test/java/com/example/app/service/UserServiceImplTest.java", prepared)
        self.assertNotIn("src/test/java/com/example/app/service/HelloWorldServiceTest.java", prepared)

    def test_prepare_test_files_for_execution_builds_story_scoped_smoke_test_when_needed(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/impl/UserServiceImpl.java": (
                    "package com.example.app.service.impl;\n"
                    "public class UserServiceImpl {}\n"
                ),
                "src/test/java/com/example/app/service/HelloWorldServiceTest.java": (
                    "package com.example.app.service;\nclass HelloWorldServiceTest {}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        analysis = AnalysisResult(
            entities=[Entity(name="User", fields=[])],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="User",
            dependencies=[],
            business_rules=[],
        )
        test_result = TestResult(
            coverage=0.0,
            passed=False,
            test_files={},
            test_summary="generated",
        )
        story_scope = StoryScope(
            story_id="TEST-2",
            business_files=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            entrypoints=[],
            dependencies=[],
            excluded_files=["src/test/java/com/example/app/service/HelloWorldServiceTest.java"],
            new_files=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
            modified_files=[],
            fixer_touched_files=[],
            file_roles={"src/main/java/com/example/app/service/impl/UserServiceImpl.java": "service"},
        )

        prepared = pipeline._prepare_test_files_for_execution(
            generated_code,
            test_result,
            analysis,
            story_scope=story_scope,
        )

        self.assertEqual(list(prepared.keys()), ["src/test/java/com/example/app/StoryScopeSmokeTest.java"])
        self.assertIn("UserServiceImpl.class", prepared["src/test/java/com/example/app/StoryScopeSmokeTest.java"])

    def test_extract_uncovered_story_targets_prioritizes_service_and_controller_before_dto_entity(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=[
                "src/main/java/com/example/app/service/AuthenticationServiceImpl.java",
                "src/main/java/com/example/app/controller/AuthenticationController.java",
                "src/main/java/com/example/app/dto/AuthenticationRequest.java",
                "src/main/java/com/example/app/entity/User.java",
            ],
            test_targets=[
                "src/main/java/com/example/app/service/AuthenticationServiceImpl.java",
                "src/main/java/com/example/app/controller/AuthenticationController.java",
                "src/main/java/com/example/app/dto/AuthenticationRequest.java",
                "src/main/java/com/example/app/entity/User.java",
            ],
            entrypoints=["src/main/java/com/example/app/controller/AuthenticationController.java"],
            dependencies=[],
            excluded_files=[],
            file_roles={
                "src/main/java/com/example/app/service/AuthenticationServiceImpl.java": "service",
                "src/main/java/com/example/app/controller/AuthenticationController.java": "controller",
                "src/main/java/com/example/app/dto/AuthenticationRequest.java": "dto",
                "src/main/java/com/example/app/entity/User.java": "entity",
            },
        )
        story_coverage = StoryCoverageReport(
            story_id="US-TEST",
            line_coverage=10.0,
            branch_coverage=0.0,
            uncovered_classes=[
                {"class_name": "User", "missed_lines": 10, "missed_branches": 0},
                {"class_name": "AuthenticationRequest", "missed_lines": 8, "missed_branches": 0},
                {"class_name": "AuthenticationController", "missed_lines": 5, "missed_branches": 1},
                {"class_name": "AuthenticationServiceImpl", "missed_lines": 6, "missed_branches": 2},
            ],
            scoped_classes=[
                {"class_name": "User"},
                {"class_name": "AuthenticationRequest"},
                {"class_name": "AuthenticationController"},
                {"class_name": "AuthenticationServiceImpl"},
            ],
        )

        targets = pipeline.extract_uncovered_story_targets(story_scope, story_coverage, limit=4)

        self.assertCountEqual(
            targets[:2],
            ["AuthenticationServiceImpl", "AuthenticationController"],
        )

    async def test_coverage_retry_stops_early_when_no_material_test_delta(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline)
        pipeline._validate_generated_code_alignment = lambda *args, **kwargs: {"passed": True, "issues": []}

        unchanged_tests = TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="unchanged",
            metadata={},
        )
        pipeline.tester.test = AsyncMock(side_effect=[unchanged_tests, unchanged_tests])
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=55.0,
            branch_coverage=10.0,
            coverage_source="jacoco",
            class_coverage=[
                {"class_name": "Application", "line_coverage": 55.0, "branch_coverage": 10.0},
            ],
            test_cases=[],
        ))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertEqual(pipeline.build_runner.run_tests.await_count, 1)
        self.assertEqual(result["coverage_retry_attempts"], 1)
        self.assertEqual(
            result["coverage_retry_diagnostics"][0]["material_delta"]["changed"],
            False,
        )

    async def test_retry_test_compilation_failure_preserves_last_valid_story_coverage(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, _ = self._wire_basic_pipeline(pipeline)
        pipeline._validate_generated_code_alignment = lambda *args, **kwargs: {"passed": True, "issues": []}

        initial_tests = TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="initial",
        )
        retry_tests = TestResult(
            coverage=80.0,
            passed=False,
            test_files={
                "src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}",
                "src/test/java/com/example/app/ApplicationCoverageRetryTest.java": "class ApplicationCoverageRetryTest {}",
            },
            test_summary="retry",
        )
        pipeline.tester.test = AsyncMock(side_effect=[initial_tests, retry_tests])
        pipeline.build_runner.run_tests = AsyncMock(side_effect=[
            TestRunResult(
                success=True,
                total_tests=2,
                passed_tests=2,
                line_coverage=61.0,
                branch_coverage=40.0,
                coverage_source="jacoco",
                class_coverage=[
                    {"class_name": "Application", "line_coverage": 61.0, "branch_coverage": 40.0},
                ],
                test_cases=[],
            ),
            TestRunResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                line_coverage=None,
                branch_coverage=None,
                coverage_source="fallback",
                failure_type="test_compilation_failure",
                test_cases=[],
            ),
        ])

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertEqual(result["story_coverage_line"], 61.0)
        self.assertEqual(result["coverage_source"], "jacoco")
        self.assertEqual(
            result["coverage_retry_diagnostics"][-1]["status"],
            "retry_test_compilation_failure",
        )

    async def test_quality_gate_blocks_when_skipped_tests_exceed_threshold(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, code = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=2,
            passed_tests=1,
            skipped_tests=1,
            line_coverage=91.0,
            branch_coverage=80.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(
            ReviewResult(score=90, approved=True, summary="ok"),
            code,
        ))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertFalse(result["quality_scan_passed"])
        self.assertIn("quality_policy_failure", result["failure_types"])
        self.assertFalse(result["all_gates_passed"])
        self.assertEqual(result["decision_route"], "quality_policy_failure")

    async def test_maven_runner_fails_clearly_when_no_non_empty_test_sources_written(self):
        from core.maven_compiler import MavenBuildRunner

        runner = MavenBuildRunner()
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/Application.java": (
                    "package com.example.app;\npublic class Application {}\n"
                )
            },
            pom_xml="<project><dependencies></dependencies><build><plugins></plugins></build></project>",
            readme="demo",
        )

        result = await runner.run_tests(
            generated_code,
            {"src/test/java/com/example/app/EmptyTest.java": "   "},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, "no_test_sources_written")
        self.assertEqual(result.total_tests, 0)
        self.assertEqual(result.written_test_files, [])

    async def test_maven_runner_generates_jacoco_report_after_failed_test_execution(self):
        from core.maven_compiler import MavenBuildRunner, SurefireTestCase

        runner = MavenBuildRunner()
        generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/Application.java": (
                    "package com.example.app;\npublic class Application {}\n"
                )
            },
            pom_xml="<project><dependencies></dependencies><build><plugins></plugins></build></project>",
            readme="demo",
        )

        async def fake_run_raw(project_dir, maven_cmd, goals):
            target_dir = project_dir / "target"
            target_dir.mkdir(parents=True, exist_ok=True)
            if goals and goals[0] == "test":
                (target_dir / "jacoco.exec").write_text("exec", encoding="utf-8")
                return 1, "[ERROR] Tests run: 1, Failures: 0, Errors: 1"

            jacoco_dir = target_dir / "site" / "jacoco"
            jacoco_dir.mkdir(parents=True, exist_ok=True)
            (jacoco_dir / "jacoco.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<report name="demo">
  <counter type="LINE" missed="1" covered="3"/>
  <counter type="BRANCH" missed="0" covered="2"/>
</report>
""",
                encoding="utf-8",
            )
            return 0, "[INFO] jacoco:report"

        with patch.object(runner, "_resolve_maven", new=AsyncMock(return_value="mvn")), \
             patch.object(runner, "_run_raw", new=AsyncMock(side_effect=fake_run_raw)), \
             patch.object(
                 runner,
                 "_parse_surefire_results",
                 return_value=(
                     [
                         SurefireTestCase(
                             classname="com.example.app.ApplicationTest",
                             name="fails",
                             time_seconds=0.1,
                             failure=None,
                             error="boom",
                             skipped=False,
                         )
                     ],
                     None,
                 ),
             ):
            result = await runner.run_tests(
                generated_code,
                {"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            )

        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, "test_execution_failure")
        self.assertEqual(result.coverage_source, "jacoco")
        self.assertEqual(result.line_coverage, 75.0)
        self.assertEqual(result.branch_coverage, 100.0)

    async def test_quality_gate_blocks_on_deterministic_style_and_duplication_issues(self):
        settings = self._settings()
        settings.pipeline.max_duplicate_code_percent = 1.0
        pipeline = SDLCPipeline(settings)
        code = self._make_quality_problem_code()
        self._wire_basic_pipeline(pipeline, generated_code=code)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            skipped_tests=0,
            line_coverage=91.0,
            branch_coverage=80.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(
            ReviewResult(score=90, approved=True, summary="ok"),
            code,
        ))

        result = await pipeline.run(
            user_story_input="raw story input",
            dry_run=True,
            repo_path=str(self.output_dir),
        )

        self.assertFalse(result["quality_scan_passed"])
        self.assertIn("quality_policy_failure", result["failure_types"])
        self.assertGreater(result["quality_metrics"]["duplication_percent"], 1.0)
        self.assertTrue(any(issue["category"] == "style" for issue in result["quality_issues"]))

    async def test_startup_guard_fails_early_for_missing_executables_and_skips_pipeline_construction(self):
        settings = self._settings()
        settings.hf.api_key = "token"
        stderr = io.StringIO()

        with patch.object(main_entry, "Settings", return_value=settings), \
             patch.object(main_entry, "_command_available", new=AsyncMock(side_effect=[False, False])), \
             patch.object(main_entry, "SDLCPipeline") as pipeline_cls, \
             redirect_stderr(stderr), \
             self.assertRaises(SystemExit) as ctx:
            await main_entry.main(
                user_story_input="raw story input",
                dry_run=True,
                repo_path=str(self.output_dir),
            )

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("STARTUP_PREREQUISITE_FAILURE", stderr.getvalue())
        self.assertIn("missing executable: java", stderr.getvalue())
        self.assertIn("missing executable: mvn", stderr.getvalue())
        pipeline_cls.assert_not_called()

    async def test_startup_guard_requires_credentials_only_in_the_correct_context(self):
        settings = self._settings()
        settings.hf.api_key = "token"
        settings.jira.url = ""
        settings.jira.username = ""
        settings.jira.api_token = ""
        settings.github.token = ""
        settings.github.owner = ""
        settings.github.repo = ""

        with patch.object(main_entry, "_command_available", new=AsyncMock(return_value=True)):
            raw_errors = await main_entry._validate_startup_prerequisites(
                settings,
                user_story_input="raw story input",
                dry_run=True,
            )
            jira_errors = await main_entry._validate_startup_prerequisites(
                settings,
                user_story_input="PROJ-123",
                dry_run=False,
            )

        self.assertFalse(any("JIRA_" in err for err in raw_errors))
        self.assertFalse(any("GITHUB_" in err for err in raw_errors))
        self.assertTrue(any("JIRA_URL" in err for err in jira_errors))
        self.assertTrue(any("JIRA_USERNAME" in err for err in jira_errors))
        self.assertTrue(any("JIRA_API_TOKEN" in err for err in jira_errors))
        self.assertTrue(any("GITHUB_TOKEN" in err for err in jira_errors))
        self.assertTrue(any("GITHUB_OWNER" in err for err in jira_errors))
        self.assertTrue(any("GITHUB_REPO" in err for err in jira_errors))

    async def test_startup_guard_allows_local_git_commit_mode_without_github_credentials(self):
        settings = self._settings()
        settings.hf.api_key = "token"
        settings.github.token = ""
        settings.github.owner = ""
        settings.github.repo = ""

        local_repo = Path(self.tmpdir.name) / "local-repo"
        local_repo.mkdir(parents=True, exist_ok=True)
        (local_repo / ".git").mkdir()

        with patch.object(main_entry, "_command_available", new=AsyncMock(side_effect=[True, True, True])):
            errors = await main_entry._validate_startup_prerequisites(
                settings,
                user_story_input="raw story input",
                dry_run=False,
                repo_path=str(local_repo),
            )

        self.assertFalse(any("GITHUB_" in err for err in errors))
        self.assertFalse(any("missing executable: git" in err for err in errors))

    async def test_pipeline_prefers_local_git_commit_when_repo_path_is_a_git_repo(self):
        settings = self._settings()
        pipeline = SDLCPipeline(settings)
        _, _, _, _, code = self._wire_basic_pipeline(pipeline)

        pipeline.tester.test = AsyncMock(return_value=TestResult(
            coverage=55.0,
            passed=False,
            test_files={"src/test/java/com/example/app/ApplicationTest.java": "class ApplicationTest {}"},
            test_summary="generated",
        ))
        pipeline.build_runner.run_tests = AsyncMock(return_value=TestRunResult(
            success=True,
            total_tests=1,
            passed_tests=1,
            line_coverage=91.0,
            branch_coverage=80.0,
            coverage_source="jacoco",
        ))
        pipeline._review_and_correct = AsyncMock(return_value=(
            ReviewResult(score=80, approved=False, summary="score-only approval"),
            code,
        ))

        local_repo = Path(self.tmpdir.name) / "git-target"
        local_repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=local_repo, check=True, capture_output=True)

        with patch("core.pipeline.LocalGitClient.commit_code", new=AsyncMock(return_value="abc123")) as local_commit, \
             patch.object(pipeline.github, "commit_code", new=AsyncMock(side_effect=AssertionError("github fallback should not run"))):
            result = await pipeline.run(
                user_story_input="raw story input",
                dry_run=False,
                repo_path=str(local_repo),
            )

        self.assertEqual(result["commit_sha"], "abc123")
        local_commit.assert_awaited_once()

    def test_developer_conflict_split_and_duplicate_merge_detection_are_deterministic(self):
        developer = DeveloperAgent(self._settings().hf)
        tasks = [
            SubTask("task-b", "B", "", [], ["src/main/java/B.java"], [], "developer", 2),
            SubTask("task-a", "A", "", [], ["src/main/java/A.java"], [], "developer", 1),
            SubTask("task-c", "C", "", [], ["src/main/java/A.java"], [], "developer", 3),
        ]

        parallel, sequential, conflicts = developer._split_by_conflicts(tasks)

        self.assertEqual([task.id for task in parallel], ["task-a", "task-b"])
        self.assertEqual([task.id for task in sequential], ["task-c"])
        self.assertEqual(conflicts["task-c"], ["src/main/java/A.java"])

        with self.assertRaises(ValueError):
            developer._merge_task_outputs(
                {},
                [
                    (tasks[0], {"src/main/java/Duplicate.java": "one"}),
                    (tasks[1], {"src/main/java/Duplicate.java": "two"}),
                ],
                group_number=1,
            )

    def test_developer_subtask_output_validation_rejects_missing_expected_files(self):
        developer = DeveloperAgent(self._settings().hf)
        task = SubTask(
            "task-1",
            "Create auth controller",
            "Create controller",
            [],
            ["src/main/java/com/example/app/controller/AuthController.java"],
            [],
            "developer",
            1,
        )

        with self.assertRaises(ValueError):
            developer._validate_subtask_output(task, {})

    def test_developer_subtask_output_validation_rejects_unexpected_files(self):
        developer = DeveloperAgent(self._settings().hf)
        task = SubTask(
            "task-1",
            "Create auth controller",
            "Create controller",
            [],
            ["src/main/java/com/example/app/controller/AuthController.java"],
            [],
            "developer",
            1,
        )

        with self.assertRaises(ValueError):
            developer._validate_subtask_output(
                task,
                {"src/main/java/com/example/app/controller/HelloWorldController.java": "class HelloWorldController {}"},
            )

    async def test_developer_execute_subtask_retries_when_first_response_misses_expected_files(self):
        developer = DeveloperAgent(self._settings().hf)
        story = self._make_story()
        analysis = self._make_analysis()
        task = SubTask(
            "task-1",
            "Create auth controller",
            "Create controller",
            [],
            ["src/main/java/com/example/app/controller/AuthController.java"],
            [],
            "developer",
            1,
        )

        env_backup = os.environ.get("DEVELOPER_USE_LLM")
        os.environ["DEVELOPER_USE_LLM"] = "true"
        developer.call_llm = AsyncMock(side_effect=[
            """```java:src/main/java/com/example/app/controller/HelloWorldController.java
package com.example.app.controller;
class HelloWorldController {}
```""",
            """```java:src/main/java/com/example/app/controller/AuthController.java
package com.example.app.controller;
class AuthController {}
```""",
        ])
        try:
            generated = await developer._execute_subtask(
                task=task,
                user_story=story,
                analysis=analysis,
                current_files={},
                docs={},
            )
        finally:
            if env_backup is None:
                os.environ.pop("DEVELOPER_USE_LLM", None)
            else:
                os.environ["DEVELOPER_USE_LLM"] = env_backup

        self.assertEqual(
            list(generated.keys()),
            ["src/main/java/com/example/app/controller/AuthController.java"],
        )
        self.assertEqual(developer.call_llm.await_count, 2)

    def test_intent_summary_includes_acceptance_criteria_and_minimality_rule(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="SCRUM-9",
            title="Consultation du statut",
            description="Consulter le statut d'une candidature",
            acceptance_criteria=[
                "GET /api/applications/{id}/status returns the application status",
                "Default status is SUBMITTED",
            ],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = self._make_analysis()

        summary = pipeline._build_intent_summary(story, analysis)

        self.assertIn("Acceptance criteria:", summary)
        self.assertIn("GET /api/applications/{id}/status", summary)
        self.assertIn("do not add generic CRUD operations", summary)

    def test_repository_analyzer_samples_pom_xml_as_key_file(self):
        analyzer = RepositoryAnalyzerAgent(self._settings().hf)
        repo_root = Path(self.tmpdir.name) / "repo-analyzer"
        repo_root.mkdir(parents=True, exist_ok=True)
        (repo_root / "pom.xml").write_text("<project></project>", encoding="utf-8")
        java_path = repo_root / "src/main/java/com/example/app/Application.java"
        java_path.parent.mkdir(parents=True, exist_ok=True)
        java_path.write_text("package com.example.app;\nclass Application {}\n", encoding="utf-8")

        snippets = analyzer._sample_key_files(repo_root, "consult application status")

        self.assertIn("pom.xml", snippets)

    def test_repository_analyzer_handles_repo_path_nested_under_output_directory_name(self):
        analyzer = RepositoryAnalyzerAgent(self._settings().hf)
        repo_root = Path(self.tmpdir.name) / "output" / "generated" / "SCRUM-8"
        repo_root.mkdir(parents=True, exist_ok=True)
        (repo_root / "pom.xml").write_text("<project></project>", encoding="utf-8")
        java_path = repo_root / "src/main/java/com/example/app/controller/ApplicationController.java"
        java_path.parent.mkdir(parents=True, exist_ok=True)
        java_path.write_text("package com.example.app.controller;\nclass ApplicationController {}\n", encoding="utf-8")

        snippets = analyzer._sample_key_files(repo_root, "consult application status")

        self.assertGreaterEqual(len(snippets), 1)
        self.assertIn("pom.xml", snippets)

    def test_analysis_cache_is_invalidated_when_story_content_changes(self):
        pipeline = SDLCPipeline(self._settings())
        story = self._make_story()
        docs = {"root/doc.md": "original"}
        analysis = self._make_analysis()
        cache_path = self.artifacts_dir / "analysis_US-TEST.json"

        pipeline._save_analysis_cache(cache_path, story, docs, analysis)
        loaded = pipeline._load_analysis_cache(cache_path, story, docs)
        self.assertIsNotNone(loaded)

        changed_story = UserStory(
            id=story.id,
            title=story.title,
            description="changed description",
            acceptance_criteria=story.acceptance_criteria,
            priority=story.priority,
            story_points=story.story_points,
            labels=story.labels,
            epic=story.epic,
            raw=story.raw,
        )
        invalidated = pipeline._load_analysis_cache(cache_path, changed_story, docs)
        self.assertIsNone(invalidated)

    def test_plan_alignment_rejects_unexpected_resource_for_status_story(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="SCRUM-9",
            title="Consultation du statut d'une candidature",
            description="Le candidat consulte le statut de sa candidature",
            acceptance_criteria=["GET /api/applications/{id}/status retourne le statut"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="GET", path="/api/applications/{id}/status", description="Get application status")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Application",
            dependencies=[],
            business_rules=["Expose only the status consultation endpoint"],
        )
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Create Candidate controller",
                    description="Add CRUD operations for candidates",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/controller/CandidateController.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                )
            ],
            execution_groups=[["task-1"]],
            risks=[],
            summary="plan",
        )

        validation = pipeline._validate_plan_alignment(story, analysis, plan)

        self.assertFalse(validation["passed"])
        self.assertTrue(any("unexpected planned resources" in issue for issue in validation["issues"]))

    def test_plan_alignment_allows_standard_global_exception_handler_support_files(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-2",
            title="Create user registration service with email validation",
            description="As an admin, I want a registration flow with email validation.",
            acceptance_criteria=["POST /api/users validates email before creating the user"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/users", description="Create user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="User",
            dependencies=[],
            business_rules=["Validate email format before persisting the user"],
        )
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="User service",
                    description="Implement user registration flow",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/service/impl/UserServiceImpl.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                ),
                SubTask(
                    id="task-2",
                    title="Exception mapping",
                    description="Reuse standard exception handler support",
                    files_to_edit=["src/main/java/com/example/app/exception/GlobalExceptionHandler.java"],
                    files_to_create=[],
                    depends_on=["task-1"],
                    agent="developer",
                    priority=2,
                ),
            ],
            execution_groups=[["task-1"], ["task-2"]],
            risks=[],
            summary="plan",
        )

        validation = pipeline._validate_plan_alignment(story, analysis, plan)

        self.assertTrue(validation["passed"])

    def test_generated_code_alignment_rejects_crud_for_status_story(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="SCRUM-9",
            title="Consultation du statut d'une candidature",
            description="Le candidat consulte le statut de sa candidature",
            acceptance_criteria=["GET /api/applications/{id}/status retourne le statut"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="GET", path="/api/applications/{id}/status", description="Get application status")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Application",
            dependencies=[],
            business_rules=["Expose only the status consultation endpoint"],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/ApplicationController.java": (
                    "package com.example.app.controller;\n"
                    "import org.springframework.web.bind.annotation.*;\n"
                    "@RestController\n"
                    "class ApplicationController {\n"
                    "  @PostMapping(\"/api/applications\") void create() {}\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        validation = pipeline._validate_generated_code_alignment(story, analysis, generated)

        self.assertFalse(validation["passed"])
        self.assertTrue(any("CRUD behavior" in issue for issue in validation["issues"]))

    def test_plan_alignment_allows_auth_alias_for_login_story(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-1",
            title="Add login endpoint with username and password validation",
            description="As a user, I want a login endpoint with username and password validation.",
            acceptance_criteria=["POST /api/v1/login authenticates a user with valid credentials"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Create auth controller",
                    description="Add login endpoint handling",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/controller/AuthController.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                )
            ],
            execution_groups=[["task-1"]],
            risks=[],
            summary="plan",
        )

        validation = pipeline._validate_plan_alignment(story, analysis, plan)

        self.assertTrue(validation["passed"])

    def test_plan_path_normalization_rewrites_aliases_to_canonical_analysis_names(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-1",
            title="Add login endpoint with username and password validation",
            description="As a user, I want a login endpoint with username and password validation.",
            acceptance_criteria=["POST /api/v1/login authenticates a user with valid credentials"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Create auth controller",
                    description="Add login endpoint handling",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/controller/AuthController.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                ),
                SubTask(
                    id="task-2",
                    title="Create auth service",
                    description="Implement authentication service",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/service/AuthService.java"],
                    depends_on=["task-1"],
                    agent="developer",
                    priority=2,
                ),
            ],
            execution_groups=[["task-1"], ["task-2"]],
            risks=[],
            summary="plan",
        )

        normalized = pipeline._normalize_plan_paths_against_analysis(story, analysis, plan)
        normalized_paths = {
            path
            for task in normalized.subtasks
            for path in (task.files_to_create + task.files_to_edit)
        }

        self.assertIn(
            "src/main/java/com/example/app/controller/AuthenticationController.java",
            normalized_paths,
        )
        self.assertIn(
            "src/main/java/com/example/app/service/AuthenticationService.java",
            normalized_paths,
        )

    def test_generated_code_alignment_rejects_missing_expected_endpoint(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-1",
            title="Add login endpoint with username and password validation",
            description="As a user, I want a login endpoint with username and password validation.",
            acceptance_criteria=["POST /api/v1/login authenticates a user with valid credentials"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/HelloWorldController.java": (
                    "package com.example.app.controller;\n"
                    "import org.springframework.web.bind.annotation.GetMapping;\n"
                    "import org.springframework.web.bind.annotation.RequestMapping;\n"
                    "import org.springframework.web.bind.annotation.RestController;\n"
                    "@RestController\n"
                    "@RequestMapping(\"/api\")\n"
                    "class HelloWorldController {\n"
                    "  @GetMapping(\"/hello\") String hello() { return \"ok\"; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        validation = pipeline._validate_generated_code_alignment(
            story,
            analysis,
            generated,
            relevant_paths={"src/main/java/com/example/app/controller/AuthController.java"},
        )

        self.assertFalse(validation["passed"])
        self.assertTrue(any("missing expected endpoints" in issue for issue in validation["issues"]))
        self.assertTrue(any("missing planned main files" in issue for issue in validation["issues"]))

    def test_generated_code_alignment_accepts_expected_composed_endpoint(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-1",
            title="Add login endpoint with username and password validation",
            description="As a user, I want a login endpoint with username and password validation.",
            acceptance_criteria=["POST /api/v1/login authenticates a user with valid credentials"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/AuthController.java": (
                    "package com.example.app.controller;\n"
                    "import org.springframework.web.bind.annotation.PostMapping;\n"
                    "import org.springframework.web.bind.annotation.RequestBody;\n"
                    "import org.springframework.web.bind.annotation.RequestMapping;\n"
                    "import org.springframework.web.bind.annotation.RestController;\n"
                    "@RestController\n"
                    "@RequestMapping(\"/api/v1\")\n"
                    "class AuthController {\n"
                    "  @PostMapping(\"/login\") String login(@RequestBody String body) { return body; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        validation = pipeline._validate_generated_code_alignment(
            story,
            analysis,
            generated,
            relevant_paths={"src/main/java/com/example/app/controller/AuthController.java"},
        )

        self.assertTrue(validation["passed"])

    def test_generated_code_alignment_accepts_canonical_request_dto_alias(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-2",
            title="Create user registration service with email validation",
            description="As an admin, I want a registration endpoint with email validation.",
            acceptance_criteria=["POST /api/users validates email before creating the user"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/users", description="Create user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="User",
            dependencies=[],
            business_rules=["Validate email format before persisting the user"],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/dto/UserRequest.java": (
                    "package com.example.app.dto;\n"
                    "public class UserRequest {}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        validation = pipeline._validate_generated_code_alignment(
            story,
            analysis,
            generated,
            relevant_paths={"src/main/java/com/example/app/dto/UserRegistrationRequest.java"},
        )

        self.assertTrue(validation["passed"])

    def test_generated_code_alignment_accepts_class_level_request_mapping_with_intermediate_annotations(self):
        pipeline = SDLCPipeline(self._settings())
        story = UserStory(
            id="TEST-1",
            title="Add login endpoint with username and password validation",
            description="As a user, I want a login endpoint with username and password validation.",
            acceptance_criteria=["POST /api/v1/login authenticates a user with valid credentials"],
            priority="Medium",
            story_points=None,
            labels=[],
            epic=None,
            raw={},
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/AuthenticationController.java": (
                    "package com.example.app.controller;\n"
                    "import lombok.RequiredArgsConstructor;\n"
                    "import io.swagger.v3.oas.annotations.tags.Tag;\n"
                    "import org.springframework.web.bind.annotation.PostMapping;\n"
                    "import org.springframework.web.bind.annotation.RequestMapping;\n"
                    "import org.springframework.web.bind.annotation.RestController;\n"
                    "@RestController\n"
                    "@RequestMapping(\"/api/v1/login\")\n"
                    "@RequiredArgsConstructor\n"
                    "@Tag(name = \"AuthenticationController\")\n"
                    "public class AuthenticationController {\n"
                    "  @PostMapping\n"
                    "  String login() { return \"ok\"; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        validation = pipeline._validate_generated_code_alignment(
            story,
            analysis,
            generated,
            relevant_paths={"src/main/java/com/example/app/controller/AuthenticationController.java"},
        )

        self.assertTrue(validation["passed"])

    def test_planner_specializes_status_lookup_story_toward_application_files(self):
        planner = PlannerAgent(self._settings().hf)
        repo_analysis = RepoAnalysis(
            repo_path=str(self.output_dir),
            languages=["java"],
            frameworks=["spring-boot"],
            build_system="maven",
            build_commands={"compile": "mvn compile", "test": "mvn test"},
            entry_points=["src/main/java/com/example/app/Application.java"],
            relevant_files=[
                "src/main/java/com/example/app/controller/ApplicationController.java",
                "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java",
            ],
            potentially_impacted=[],
            existing_patterns=[],
            change_map={
                "src/main/java/com/example/app/controller/ApplicationController.java": "status endpoint lives here",
            },
            risks=[],
            summary="Application status lookup in an existing Spring Boot service",
        )

        plan = planner._specialized_status_lookup_plan(
            "[SCRUM-9] Consultation du statut d'une candidature\nAcceptance criteria:\n- GET /api/applications/{id}/status returns the application status",
            repo_analysis,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        planned_paths = {
            path
            for task in plan.subtasks
            for path in (task.files_to_create + task.files_to_edit)
        }
        self.assertIn("src/main/java/com/example/app/controller/ApplicationController.java", planned_paths)
        self.assertNotIn("src/main/java/com/example/app/controller/CandidateController.java", planned_paths)

    async def test_generate_from_plan_seeds_required_business_dependencies_for_planned_controller(self):
        developer = DeveloperAgent(self._settings().hf)
        story = self._make_story()
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="GET", path="/api/demo/{id}/status", description="status only")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Demo",
            dependencies=[],
            business_rules=["Expose only status consultation"],
        )
        repo_analysis = self._make_repo_analysis()
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Controller",
                    description="Create the status endpoint only",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/controller/DemoController.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                )
            ],
            execution_groups=[["task-1"]],
            risks=[],
            summary="plan",
        )

        env_backup = os.environ.get("DEVELOPER_USE_LLM")
        os.environ["DEVELOPER_USE_LLM"] = "false"
        try:
            generated = await developer.generate_from_plan(
                user_story=story,
                analysis=analysis,
                repo_analysis=repo_analysis,
                plan=plan,
                docs={},
                existing_code=None,
            )
        finally:
            if env_backup is None:
                os.environ.pop("DEVELOPER_USE_LLM", None)
            else:
                os.environ["DEVELOPER_USE_LLM"] = env_backup

        business_paths = [
            path for path in generated.files
            if path.startswith("src/main/java/com/example/app/")
            and not path.endswith("Application.java")
            and "OpenApiConfig.java" not in path
            and "/exception/" not in path
            and "HealthCheckController.java" not in path
        ]
        self.assertEqual(
            sorted(business_paths),
            [
                "src/main/java/com/example/app/controller/DemoController.java",
                "src/main/java/com/example/app/dto/DemoRequest.java",
                "src/main/java/com/example/app/dto/DemoResponse.java",
                "src/main/java/com/example/app/entity/DemoEntity.java",
                "src/main/java/com/example/app/repository/DemoEntityRepository.java",
                "src/main/java/com/example/app/service/DemoService.java",
                "src/main/java/com/example/app/service/impl/DemoServiceImpl.java",
            ],
        )

    def test_expand_planned_paths_keeps_entity_and_repository_dependencies(self):
        developer = DeveloperAgent(self._settings().hf)
        deterministic_files = {
            "src/main/java/com/example/app/controller/AuthenticationController.java": "class AuthenticationController {}",
            "src/main/java/com/example/app/service/AuthenticationService.java": "interface AuthenticationService {}",
            "src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java": "class AuthenticationServiceImpl {}",
            "src/main/java/com/example/app/dto/AuthenticationRequest.java": "class AuthenticationRequest {}",
            "src/main/java/com/example/app/dto/AuthenticationResponse.java": "class AuthenticationResponse {}",
            "src/main/java/com/example/app/entity/User.java": "class User {}",
            "src/main/java/com/example/app/repository/UserRepository.java": "interface UserRepository {}",
        }

        expanded = developer._expand_planned_paths_with_required_business_dependencies(
            {
                "src/main/java/com/example/app/controller/AuthenticationController.java",
                "src/main/java/com/example/app/service/AuthenticationService.java",
            },
            deterministic_files,
        )

        self.assertIn("src/main/java/com/example/app/entity/User.java", expanded)
        self.assertIn("src/main/java/com/example/app/repository/UserRepository.java", expanded)

    def test_request_dto_builder_deduplicates_field_names(self):
        developer = DeveloperAgent(self._settings().hf)

        class Field:
            def __init__(self, name, field_type):
                self.name = name
                self.type = field_type

        dto = developer._build_request_dto(
            "com.example.app",
            "AuthenticationRequest",
            [Field("name", "String"), Field("username", "String"), Field("password", "String")],
        )

        self.assertEqual(dto.count("private String name;"), 1)

    def test_tester_prunes_shadowed_test_variants_when_deterministic_exists(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        test_files = {
            "src/test/java/com/example/app/repository/UserRepositoryTest.java": "class UserRepositoryTest {}",
            "src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java": "class UserRepositoryDeterministicTest {}",
            "src/test/java/com/example/app/service/AuthenticationServiceTest.java": "class AuthenticationServiceTest {}",
        }

        pruned = tester._prune_shadowed_test_variants(test_files)

        self.assertNotIn("src/test/java/com/example/app/repository/UserRepositoryTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/service/AuthenticationServiceTest.java", pruned)

    def test_tester_detects_invalid_optional_model_accessor_usage(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/entity/User.java": (
                    "package com.example.app.entity;\n"
                    "public class User {\n"
                    "  private Long id;\n"
                    "  private String username;\n"
                    "  public Long getId() { return id; }\n"
                    "  public String getUsername() { return username; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        symbol_index = tester._build_project_symbol_index(generated)
        content = (
            "package com.example.app.repository;\n"
            "import java.util.Optional;\n"
            "import com.example.app.entity.User;\n"
            "class UserRepositoryTest {\n"
            "  void sample() {\n"
            "    Optional<User> foundUser = Optional.empty();\n"
            "    foundUser.get().getEmail();\n"
            "  }\n"
            "}\n"
        )

        invalid = tester._find_invalid_model_usage(content, symbol_index)

        self.assertIn("User.getEmail", invalid)

    def test_tester_detects_invalid_local_model_accessor_usage(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/entity/User.java": (
                    "package com.example.app.entity;\n"
                    "public class User {\n"
                    "  private Long id;\n"
                    "  private String username;\n"
                    "  public Long getId() { return id; }\n"
                    "  public String getUsername() { return username; }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        symbol_index = tester._build_project_symbol_index(generated)
        content = (
            "package com.example.app.repository;\n"
            "import com.example.app.entity.User;\n"
            "class UserRepositoryTest {\n"
            "  void sample() {\n"
            "    User savedUser = load();\n"
            "    savedUser.getName();\n"
            "  }\n"
            "  User load() { return null; }\n"
            "}\n"
        )

        invalid = tester._find_invalid_model_usage(content, symbol_index)

        self.assertIn("User.getName", invalid)

    def test_tester_discovers_repository_from_service_dependency(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java": (
                    "package com.example.app.service.impl;\n"
                    "import com.example.app.repository.UserRepository;\n"
                    "public class AuthenticationServiceImpl {\n"
                    "  private final UserRepository userRepository;\n"
                    "  public AuthenticationServiceImpl(UserRepository userRepository) { this.userRepository = userRepository; }\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/repository/UserRepository.java": (
                    "package com.example.app.repository;\n"
                    "public interface UserRepository {}\n"
                ),
                "src/main/java/com/example/app/entity/User.java": (
                    "package com.example.app.entity;\n"
                    "public class User {\n"
                    "  private Long id;\n"
                    "  private String username;\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/controller/AuthenticationController.java": (
                    "package com.example.app.controller;\n"
                    "public class AuthenticationController {}\n"
                ),
                "src/main/java/com/example/app/dto/AuthenticationRequest.java": (
                    "package com.example.app.dto;\n"
                    "public class AuthenticationRequest {}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=[],
        )
        symbol_index = tester._build_project_symbol_index(generated)

        resources = tester._discover_project_resources(generated, analysis, symbol_index)

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["repository_name"], "UserRepository")
        self.assertEqual(resources[0]["entity_name"], "User")
        self.assertTrue(resources[0]["has_repository"])

    def test_tester_prunes_irrelevant_story_tests(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=["Validate username and password before authentication"],
        )
        test_files = {
            "src/test/java/com/example/app/service/HelloWorldServiceTest.java": "class HelloWorldServiceTest {}",
            "src/test/java/com/example/app/service/AuthenticationServiceTest.java": "class AuthenticationServiceTest {}",
            "src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java": "class UserRepositoryDeterministicTest {}",
        }

        pruned = tester._prune_irrelevant_story_tests(test_files, analysis)

        self.assertNotIn("src/test/java/com/example/app/service/HelloWorldServiceTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/service/AuthenticationServiceTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java", pruned)

    def test_tester_prunes_explicit_legacy_old_story_tests(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        analysis = AnalysisResult(
            entities=[Entity(name="User", fields=[])],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="User",
            dependencies=[],
            business_rules=["email validation"],
        )
        test_files = {
            "src/test/java/com/example/app/service/LegacyAuthenticationServiceTest.java": "class LegacyAuthenticationServiceTest {}",
            "src/test/java/com/example/app/service/OldStoryUserServiceTest.java": "class OldStoryUserServiceTest {}",
            "src/test/java/com/example/app/service/UserServiceTest.java": "class UserServiceTest {}",
        }

        pruned = tester._prune_irrelevant_story_tests(test_files, analysis)

        self.assertNotIn("src/test/java/com/example/app/service/LegacyAuthenticationServiceTest.java", pruned)
        self.assertNotIn("src/test/java/com/example/app/service/OldStoryUserServiceTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/service/UserServiceTest.java", pruned)

    def test_repository_deterministic_test_is_smoke_style(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        path, content = tester._build_repository_data_test(
            {
                "package_name": "com.example.app",
                "repository_name": "UserRepository",
                "entity_name": "User",
            }
        )

        self.assertEqual(path, "src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java")
        self.assertIn("repositoryType_isInterface", content)
        self.assertIn("JpaRepository.class.isAssignableFrom(UserRepository.class)", content)
        self.assertNotIn("@DataJpaTest", content)
        self.assertNotIn("repository.save(", content)
        self.assertNotIn("repository.delete(", content)

    def test_tester_safe_mode_blocks_heavy_spring_tests(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)

        self.assertTrue(tester._is_heavy_spring_test_content("@SpringBootTest class DemoTest {}"))
        self.assertTrue(tester._is_heavy_spring_test_content("@DataJpaTest class DemoRepositoryTest {}"))
        self.assertFalse(tester._is_heavy_spring_test_content("@WebMvcTest class DemoControllerTest {}"))

    def test_tester_safe_mode_adds_timeout_to_junit_tests(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        content = (
            "package com.example.app.service;\n\n"
            "import org.junit.jupiter.api.Test;\n\n"
            "class DemoServiceTest {\n"
            "    @Test\n"
            "    void create_returnsValue() {\n"
            "    }\n"
            "}\n"
        )

        normalized = tester._ensure_test_timeouts(content)

        self.assertIn("import org.junit.jupiter.api.Timeout;", normalized)
        self.assertIn("@Timeout(10)", normalized)

    def test_generate_deterministic_tests_for_resource_skips_repository_by_default(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        files = tester._generate_deterministic_tests_for_resource(
            {
                "package_name": "com.example.app",
                "service_impl_name": "UserServiceImpl",
                "service_name": "UserService",
                "request_name": "UserRequest",
                "response_name": "UserResponse",
                "entity_name": "User",
                "repository_name": "UserRepository",
                "dependencies": [{"type": "UserRepository", "name": "repository"}],
                "request_fields": [],
                "response_fields": [],
                "entity_fields": [("id", "Long")],
                "all_field_specs": {},
                "service_source": "public class UserServiceImpl { public java.util.List<UserResponse> findAll(){ return java.util.List.of(); } }",
                "service_methods": [],
                "repository_methods": [],
                "has_controller": False,
                "has_repository": True,
            }
        )

        self.assertIn("src/test/java/com/example/app/service/UserServiceImplTest.java", files)
        self.assertNotIn("src/test/java/com/example/app/repository/UserRepositoryDeterministicTest.java", files)

    def test_merge_preferred_tests_replaces_flaky_repository_test_with_deterministic_variant(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        merged = tester._merge_preferred_tests(
            {
                "src/test/java/com/example/app/repository/UserRepositoryTest.java": (
                    "@DataJpaTest class UserRepositoryTest {}"
                )
            },
            {
                "src/test/java/com/example/app/repository/UserRepositoryTest.java": (
                    "class UserRepositoryDeterministicReplacement { void repositoryType_isInterface() {} }"
                )
            },
        )

        self.assertIn("repositoryType_isInterface", merged["src/test/java/com/example/app/repository/UserRepositoryTest.java"])
        self.assertNotIn("@DataJpaTest", merged["src/test/java/com/example/app/repository/UserRepositoryTest.java"])

    def test_maven_test_failure_prefers_runtime_failure_over_testcompile_marker(self):
        from core.maven_compiler import MavenBuildRunner

        runner = MavenBuildRunner()
        failure_type = runner._classify_test_failure(
            output="[INFO] --- compiler:3.11.0:testCompile (default-testCompile) @ demo ---\n"
                   "[ERROR] Tests run: 2, Failures: 0, Errors: 2",
            returncode=1,
            failed_tests=0,
            error_tests=2,
            total_tests=2,
            surefire_report_issue=None,
        )

        self.assertEqual(failure_type, "test_execution_failure")

    def test_tester_generates_infrastructure_coverage_support_test(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="POST", path="/api/v1/login", description="Authenticate user")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Authentication",
            dependencies=[],
            business_rules=[],
        )
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/impl/HelloWorldServiceImpl.java": "package com.example.app.service.impl; class HelloWorldServiceImpl {}",
                "src/main/java/com/example/app/controller/HelloWorldController.java": "package com.example.app.controller; class HelloWorldController {}",
                "src/main/java/com/example/app/controller/HealthCheckController.java": "package com.example.app.controller; class HealthCheckController {}",
                "src/main/java/com/example/app/OpenApiConfig.java": "package com.example.app; class OpenApiConfig {}",
                "src/main/java/com/example/app/exception/GlobalExceptionHandler.java": "package com.example.app.exception; class GlobalExceptionHandler {}",
                "src/main/java/com/example/app/exception/BusinessException.java": "package com.example.app.exception; class BusinessException {}",
                "src/main/java/com/example/app/exception/ResourceNotFoundException.java": "package com.example.app.exception; class ResourceNotFoundException {}",
                "src/main/java/com/example/app/exception/ErrorResponse.java": "package com.example.app.exception; class ErrorResponse {}",
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        support_tests = tester._generate_infrastructure_coverage_tests(generated, analysis)

        self.assertIn(
            "src/test/java/com/example/app/support/InfrastructureCoverageDeterministicTest.java",
            support_tests,
        )
        self.assertIn("globalExceptionHandler_mapsGenericException", next(iter(support_tests.values())))

    def test_invalid_model_usage_ignores_controller_method_calls(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/HelloWorldController.java": (
                    "package com.example.app.controller;\n"
                    "public class HelloWorldController {\n"
                    "  private final Object helloWorldService;\n"
                    "  public HelloWorldController(Object helloWorldService) { this.helloWorldService = helloWorldService; }\n"
                    "  public Object getHelloMessage() { return null; }\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/exception/ErrorResponse.java": (
                    "package com.example.app.exception;\n"
                    "public class ErrorResponse {\n"
                    "  private int status;\n"
                    "  public int getStatus() { return status; }\n"
                    "  public void setStatus(int status) { this.status = status; }\n"
                    "}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        symbol_index = tester._build_project_symbol_index(generated)
        content = (
            "package com.example.app.support;\n"
            "import com.example.app.controller.HelloWorldController;\n"
            "class SampleTest {\n"
            "  void sample(HelloWorldController controller) {\n"
            "    controller.getHelloMessage();\n"
            "  }\n"
            "}\n"
        )

        invalid = tester._find_invalid_model_usage(content, symbol_index)

        self.assertNotIn("HelloWorldController.getHelloMessage", invalid)

    def test_invalid_model_usage_ignores_response_entity_wrapper_accessors(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/exception/ErrorResponse.java": (
                    "package com.example.app.exception;\n"
                    "public class ErrorResponse {\n"
                    "  private int status;\n"
                    "  public int getStatus() { return status; }\n"
                    "  public void setStatus(int status) { this.status = status; }\n"
                    "}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        symbol_index = tester._build_project_symbol_index(generated)
        content = (
            "package com.example.app.support;\n"
            "import org.springframework.http.ResponseEntity;\n"
            "import com.example.app.exception.ErrorResponse;\n"
            "class SampleTest {\n"
            "  void sample(ResponseEntity<ErrorResponse> response) {\n"
            "    response.getBody();\n"
            "    response.getStatusCode();\n"
            "  }\n"
            "}\n"
        )

        invalid = tester._find_invalid_model_usage(content, symbol_index)

        self.assertFalse(any("getBody" in item or "getStatusCode" in item for item in invalid))

    def test_invalid_model_usage_ignores_service_impl_constructor_dependencies(self):
        from agents.tester import TesterAgent

        tester = TesterAgent(self._settings().hf)
        generated = GeneratedCode(
            files={
                "src/main/java/com/example/app/service/AuthenticationService.java": (
                    "package com.example.app.service;\n"
                    "public interface AuthenticationService {}\n"
                ),
                "src/main/java/com/example/app/repository/UserRepository.java": (
                    "package com.example.app.repository;\n"
                    "public interface UserRepository {}\n"
                ),
                "src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java": (
                    "package com.example.app.service.impl;\n"
                    "import com.example.app.repository.UserRepository;\n"
                    "public class AuthenticationServiceImpl {\n"
                    "  private final UserRepository repository;\n"
                    "  public AuthenticationServiceImpl(UserRepository repository) { this.repository = repository; }\n"
                    "}\n"
                ),
                "src/main/java/com/example/app/dto/AuthenticationRequest.java": (
                    "package com.example.app.dto;\n"
                    "public class AuthenticationRequest {\n"
                    "  private String username;\n"
                    "  public String getUsername() { return username; }\n"
                    "}\n"
                ),
            },
            pom_xml="<project></project>",
            readme="demo",
        )
        symbol_index = tester._build_project_symbol_index(generated)
        content = (
            "package com.example.app.service;\n"
            "import com.example.app.service.AuthenticationService;\n"
            "import com.example.app.service.impl.AuthenticationServiceImpl;\n"
            "import com.example.app.repository.UserRepository;\n"
            "import org.mockito.InjectMocks;\n"
            "import org.mockito.Mock;\n"
            "class AuthenticationServiceTest {\n"
            "  @Mock private UserRepository repository;\n"
            "  @InjectMocks private AuthenticationServiceImpl authenticationService;\n"
            "}\n"
        )

        invalid = tester._find_invalid_model_usage(content, symbol_index)

        self.assertFalse(any("AuthenticationServiceImpl.repository" in item for item in invalid))

    async def test_generate_from_plan_ignores_non_developer_subtasks(self):
        developer = DeveloperAgent(self._settings().hf)
        story = self._make_story()
        analysis = AnalysisResult(
            entities=[],
            endpoints=[Endpoint(method="GET", path="/api/demo/{id}/status", description="status only")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Demo",
            dependencies=[],
            business_rules=["Expose only status consultation"],
        )
        repo_analysis = self._make_repo_analysis()
        plan = PlanResult(
            subtasks=[
                SubTask(
                    id="task-1",
                    title="Controller",
                    description="Create the status endpoint only",
                    files_to_edit=[],
                    files_to_create=["src/main/java/com/example/app/controller/DemoController.java"],
                    depends_on=[],
                    agent="developer",
                    priority=1,
                ),
                SubTask(
                    id="task-2",
                    title="Tests",
                    description="Write tests later",
                    files_to_edit=[],
                    files_to_create=["src/test/java/com/example/app/controller/DemoControllerTest.java"],
                    depends_on=["task-1"],
                    agent="tester",
                    priority=2,
                ),
            ],
            execution_groups=[["task-1"], ["task-2"]],
            risks=[],
            summary="plan",
        )

        env_backup = os.environ.get("DEVELOPER_USE_LLM")
        os.environ["DEVELOPER_USE_LLM"] = "false"
        try:
            generated = await developer.generate_from_plan(
                user_story=story,
                analysis=analysis,
                repo_analysis=repo_analysis,
                plan=plan,
                docs={},
                existing_code=None,
            )
        finally:
            if env_backup is None:
                os.environ.pop("DEVELOPER_USE_LLM", None)
            else:
                os.environ["DEVELOPER_USE_LLM"] = env_backup

        self.assertIn("src/main/java/com/example/app/controller/DemoController.java", generated.files)
        self.assertNotIn("src/test/java/com/example/app/controller/DemoControllerTest.java", generated.files)

    def test_sanitize_service_impl_removes_unknown_entity_accessors(self):
        developer = DeveloperAgent(self._settings().hf)
        files = {
            "src/main/java/com/example/app/entity/Application.java": (
                "package com.example.app.entity;\n\n"
                "public class Application {\n"
                "    private Long id;\n"
                "    private String jobTitle;\n"
                "    private String status;\n"
                "}\n"
            ),
            "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java": (
                "package com.example.app.service.impl;\n\n"
                "import com.example.app.entity.Application;\n\n"
                "public class ApplicationServiceImpl {\n"
                "    void sync(Application entity, ApplicationRequest request) {\n"
                "        entity.setJobTitle(request.getJobTitle());\n"
                "        entity.setCreationDate(request.getCreationDate());\n"
                "    }\n\n"
                "    ApplicationResponse toResponse(Application entity) {\n"
                "        return ApplicationResponse.builder()\n"
                "                .jobTitle(entity.getJobTitle())\n"
                "                .creationDate(entity.getCreationDate())\n"
                "                .build();\n"
                "    }\n"
                "}\n"
            ),
        }

        sanitized = developer._sanitize_service_impl_against_entity_schema(files)
        service_impl = sanitized["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"]

        self.assertIn("entity.setJobTitle(request.getJobTitle());", service_impl)
        self.assertIn(".jobTitle(entity.getJobTitle())", service_impl)
        self.assertNotIn("setCreationDate", service_impl)
        self.assertNotIn("getCreationDate", service_impl)

    def test_sanitize_service_impl_removes_unknown_entity_setter_with_conditional_expression(self):
        developer = DeveloperAgent(self._settings().hf)
        files = {
            "src/main/java/com/example/app/entity/Application.java": (
                "package com.example.app.entity;\n\n"
                "public class Application {\n"
                "    private Long id;\n"
                "    private String status;\n"
                "}\n"
            ),
            "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java": (
                "package com.example.app.service.impl;\n\n"
                "import com.example.app.entity.Application;\n"
                "import java.time.LocalDateTime;\n\n"
                "public class ApplicationServiceImpl {\n"
                "    void sync(Application entity, ApplicationRequest request) {\n"
                "        entity.setStatus(request.getStatus());\n"
                "        entity.setCreationDate(request.getCreationDate() != null ? request.getCreationDate() : LocalDateTime.now());\n"
                "    }\n"
                "}\n"
            ),
        }

        sanitized = developer._sanitize_service_impl_against_entity_schema(files)
        service_impl = sanitized["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"]

        self.assertIn("entity.setStatus(request.getStatus());", service_impl)
        self.assertNotIn("setCreationDate", service_impl)

    def test_sanitize_generated_java_files_replaces_known_wildcard_imports(self):
        developer = DeveloperAgent(self._settings().hf)
        files = {
            "src/main/java/com/example/app/controller/ApplicationController.java": (
                "package com.example.app.controller;\n\n"
                "import org.springframework.web.bind.annotation.*;\n\n"
                "@RestController\n"
                "@RequestMapping(\"/api/applications\")\n"
                "public class ApplicationController {\n"
                "    @GetMapping(\"/{id}\")\n"
                "    public String findById(@PathVariable Long id) {\n"
                "        return \"ok\";\n"
                "    }\n"
                "}\n"
            ),
            "src/main/java/com/example/app/entity/Application.java": (
                "package com.example.app.entity;\n\n"
                "import jakarta.persistence.*;\n\n"
                "@Entity\n"
                "@Table(name = \"application\")\n"
                "public class Application {\n"
                "    @Id\n"
                "    @GeneratedValue(strategy = GenerationType.IDENTITY)\n"
                "    private Long id;\n"
                "    @ManyToOne\n"
                "    @JoinColumn(name = \"candidate_id\")\n"
                "    private Candidate candidate;\n"
                "}\n"
            ),
        }

        sanitized = developer._sanitize_generated_java_files(files)
        controller = sanitized["src/main/java/com/example/app/controller/ApplicationController.java"]
        entity = sanitized["src/main/java/com/example/app/entity/Application.java"]

        self.assertNotIn("import org.springframework.web.bind.annotation.*;", controller)
        self.assertIn("import org.springframework.web.bind.annotation.GetMapping;", controller)
        self.assertIn("import org.springframework.web.bind.annotation.PathVariable;", controller)
        self.assertIn("import org.springframework.web.bind.annotation.RequestMapping;", controller)
        self.assertIn("import org.springframework.web.bind.annotation.RestController;", controller)

        self.assertNotIn("import jakarta.persistence.*;", entity)
        self.assertIn("import jakarta.persistence.Entity;", entity)
        self.assertIn("import jakarta.persistence.GeneratedValue;", entity)
        self.assertIn("import jakarta.persistence.GenerationType;", entity)
        self.assertIn("import jakarta.persistence.Id;", entity)
        self.assertIn("import jakarta.persistence.JoinColumn;", entity)
        self.assertIn("import jakarta.persistence.ManyToOne;", entity)
        self.assertIn("import jakarta.persistence.Table;", entity)

    def test_sanitize_generated_java_files_syncs_missing_model_fields_from_service_usage(self):
        developer = DeveloperAgent(self._settings().hf)
        files = {
            "src/main/java/com/example/app/entity/User.java": (
                "package com.example.app.entity;\n\n"
                "import lombok.AllArgsConstructor;\n"
                "import lombok.Builder;\n"
                "import lombok.Data;\n"
                "import lombok.NoArgsConstructor;\n\n"
                "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                "public class User {\n"
                "    private Long id;\n"
                "    private String name;\n"
                "}\n"
            ),
            "src/main/java/com/example/app/dto/UserResponse.java": (
                "package com.example.app.dto;\n\n"
                "import lombok.AllArgsConstructor;\n"
                "import lombok.Builder;\n"
                "import lombok.Data;\n"
                "import lombok.NoArgsConstructor;\n\n"
                "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                "public class UserResponse {\n"
                "    private String name;\n"
                "}\n"
            ),
            "src/main/java/com/example/app/dto/UserRequest.java": (
                "package com.example.app.dto;\n\n"
                "import lombok.AllArgsConstructor;\n"
                "import lombok.Builder;\n"
                "import lombok.Data;\n"
                "import lombok.NoArgsConstructor;\n\n"
                "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
                "public class UserRequest {\n"
                "    private String name;\n"
                "    private String username;\n"
                "    private String email;\n"
                "}\n"
            ),
            "src/main/java/com/example/app/service/impl/UserServiceImpl.java": (
                "package com.example.app.service.impl;\n\n"
                "import com.example.app.dto.UserRequest;\n"
                "import com.example.app.dto.UserResponse;\n"
                "import com.example.app.entity.User;\n\n"
                "public class UserServiceImpl {\n"
                "    public UserResponse mapToResponse(User user) {\n"
                "        return UserResponse.builder()\n"
                "            .id(user.getId())\n"
                "            .name(user.getName())\n"
                "            .username(user.getUsername())\n"
                "            .email(user.getEmail())\n"
                "            .build();\n"
                "    }\n\n"
                "    public User mapToEntity(UserRequest request) {\n"
                "        User user = new User();\n"
                "        user.setName(request.getName());\n"
                "        user.setUsername(request.getUsername());\n"
                "        user.setEmail(request.getEmail());\n"
                "        return user;\n"
                "    }\n"
                "}\n"
            ),
        }

        sanitized = developer._sanitize_generated_java_files(files)
        entity = sanitized["src/main/java/com/example/app/entity/User.java"]
        response = sanitized["src/main/java/com/example/app/dto/UserResponse.java"]
        service_impl = sanitized["src/main/java/com/example/app/service/impl/UserServiceImpl.java"]

        self.assertIn("private String username;", entity)
        self.assertIn("private String email;", entity)
        self.assertIn("private Long id;", response)
        self.assertIn("private String username;", response)
        self.assertIn("private String email;", response)
        self.assertIn("user.setUsername(request.getUsername());", service_impl)
        self.assertIn("user.setEmail(request.getEmail());", service_impl)


if __name__ == "__main__":
    unittest.main()
