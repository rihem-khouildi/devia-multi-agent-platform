"""
Orchestrateur principal du pipeline SDLC — plan-driven, checkpointed, measurable.

═══════════════════════════════════════════════════════════
ARCHITECTURE
═══════════════════════════════════════════════════════════

Workflow en 14 étapes:
  1.  resolve_user_story   — Jira ID ou texte brut → UserStory
  2.  load_docs            — Charge la documentation
  3.  advisor              — ImplementationAdvisorAgent → AnalysisResult
  4.  analyzer             — RepositoryAnalyzerAgent → RepoAnalysis (FAIL si repo absent)
  5.  planner              — PlannerAgent → PlanResult + SubTask[] ordonnés
  6.  developer            — generate_from_plan() (parallel groups, focused subtasks)
  7.  compile              — mvn compile (src/main uniquement)
  8.  fixer                — FixerAgent loop (max FIXER_MAX_ITERATIONS)
  9.  tester               — TesterAgent → test files (génération LLM ou déterministe)
  10. run_tests            — mvn test + JaCoCo → TestRunResult (métriques réelles)
  11. reviewer             — ReviewerAgent + correction auto (max MAX_REVIEW_LOOPS)
  12. write_files          — Écriture sur disque
  13. quality_gate         — Compilation + couverture réelle + review score
  14. commit               — GitHub commit + PR + MAJ Jira

Checkpointing:
  - PipelineState sauvegardée après chaque étape
  - resume=True + resume_from="step_name" → saute les étapes déjà complétées

Parallélisme:
  - generate_from_plan() exécute les groupes parallèles avec asyncio.gather()
  - La détection de conflits de fichiers force le séquentiel si nécessaire

Métriques réelles:
  - Couverture = JaCoCo line_coverage (pas une estimation LLM)
  - Tests = surefire pass/fail réels
  - Si mvn test échoue → le commit est bloqué

Error categories:
  - FATAL        → arrêt immédiat (repo manquant, Maven absent, exception critique)
  - RECOVERABLE  → retry via Fixer ou correction Developer
  - BLOCKING     → pipeline continue mais commit bloqué (quality gates)
"""

import json
import re
import shutil
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

from config.settings import Settings
from agents.jira_client import JiraClient
from agents.github_client import GitHubClient
from agents.local_git_client import LocalGitClient
from agents.implementation_advisor import ImplementationAdvisorAgent
from agents.analyzer import RepositoryAnalyzerAgent
from agents.planner import PlannerAgent
from agents.developer import DeveloperAgent
from agents.tester import TesterAgent
from agents.reviewer import ReviewerAgent, ReviewResult
from agents.fixer import FixerAgent
from core.maven_compiler import MavenBuildRunner, MavenCompiler, CompileResult, CompileError
from core.quality_analyzer import QualityAnalyzer
from core.doc_loader import DocumentationLoader
from core.graphrag_loader import GraphRAGContext, load_graphrag
from core.events import EventEmitter, get_emitter
from core.models import (
    UserStory, AnalysisResult, GeneratedCode, TestResult,
    PipelineState, PipelineStep, PIPELINE_STEPS, PlanResult, SubTask,
    StoryScope, StoryCoverageReport,
)
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_COMPILE_ATTEMPTS = 2
MAX_REVIEW_LOOPS = 1
ANALYSIS_CACHE_SCHEMA_VERSION = 2

_JIRA_ID_PATTERN = re.compile(r'^[A-Z][A-Z0-9]+-\d+$')


def _is_jira_id(value: str) -> bool:
    return bool(_JIRA_ID_PATTERN.match(value.strip()))


def _make_user_story_from_text(raw_text: str) -> UserStory:
    import hashlib
    text = raw_text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0][:120] if lines else "User Story"
    criteria: list = []
    body_lines: list = []
    in_ac = False
    for line in lines[1:]:
        lower = line.lower()
        if any(lower.startswith(p) for p in ("acceptance criteria", "ac:", "critères")):
            in_ac = True
            continue
        if in_ac and line[:1] in ("-", "*", "•"):
            criteria.append(line.lstrip("-*• "))
        else:
            body_lines.append(line)
    description = " ".join(body_lines) if body_lines else text
    story_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:6].upper()
    return UserStory(
        id=f"US-{story_hash}",
        title=title,
        description=description,
        acceptance_criteria=criteria,
        priority="Medium",
        story_points=None,
        labels=[],
        epic=None,
        raw={"source": "raw_text", "text": raw_text},
    )


class SDLCPipeline:

    def __init__(self, settings: Settings, emitter: Optional[EventEmitter] = None):
        self.settings = settings
        self.emitter = emitter or get_emitter()
        self.jira = JiraClient(settings.jira)
        self.github = GitHubClient(settings.github)
        self.doc_loader = DocumentationLoader(settings.pipeline.docs_dir)

        self.advisor = ImplementationAdvisorAgent(settings.hf)
        self.analyzer = RepositoryAnalyzerAgent(settings.hf)
        self.planner = PlannerAgent(settings.hf)
        self.developer = DeveloperAgent(settings.hf)
        self.tester = TesterAgent(settings.hf)
        self.reviewer = ReviewerAgent(settings.hf)
        self.build_runner = MavenBuildRunner(timeout=180)
        self.quality_analyzer = QualityAnalyzer(settings.pipeline)
        # MavenCompiler alias kept for fixer
        self.compiler = MavenCompiler(timeout=120)
        self.fixer = FixerAgent(settings.hf, self.developer, self.compiler)

        # GraphRAG context (loaded on demand)
        self._graphrag_context: Optional[GraphRAGContext] = None

        global logger
        logger = get_logger(__name__, settings.pipeline.logs_dir)

    # ──────────────────────────────────────────────────────────────
    #  GraphRAG
    # ──────────────────────────────────────────────────────────────

    def load_graphrag(self, path: str) -> GraphRAGContext:
        """Load a GraphRAG JSON export and cache it in the pipeline instance."""
        ctx = load_graphrag(path)
        self._graphrag_context = ctx
        self.emitter.emit(
            "graphrag_loaded",
            status="success",
            message=f"GraphRAG loaded: {ctx.summary()}",
            source_file=str(path),
            entity_count=len(ctx.entities),
            relation_count=len(ctx.relations),
        )
        logger.info(f"GraphRAG loaded: {ctx.summary()}")
        return ctx

    def _get_graphrag_snippet(self, story_id: str) -> str:
        """Return a compact prompt snippet filtered for the given story."""
        if self._graphrag_context is None:
            return ""
        filtered = self._graphrag_context.filter_for_story(story_id)
        return filtered.to_prompt_snippet(max_entities=25, max_relations=30)

    def _step_emit(self, event_type: str, step: str, message: str = "", **data) -> None:
        """Convenience wrapper to emit structured pipeline events."""
        self.emitter.emit(event_type, step=step, message=message, **data)

    # ──────────────────────────────────────────────────────────────
    #  Entry point
    # ──────────────────────────────────────────────────────────────

    async def run(
        self,
        user_story_input: str,
        dry_run: bool = False,
        repo_path: Optional[str] = None,
        resume: bool = False,
        resume_from: Optional[str] = None,
        files_approved: bool = True,
        fallback_output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full multi-agent SDLC pipeline for any user story.

        Args:
            user_story_input:
                Jira ticket ID (e.g. "SCRUM-7") or raw user story text.

            dry_run:
                Skip GitHub commit and Jira status update.

            repo_path:
                Path to the local clone of the target repository for the Analyzer.
                REQUIRED for the Analyzer step — raises ValueError if missing.

            resume:
                If True, load existing PipelineState and skip completed steps.

            resume_from:
                Name of the step to resume from (overrides the last failed step).
                Valid values: see PIPELINE_STEPS in core/models.py.
        """
        reuse_analysis = os.getenv("PIPELINE_REUSE_ANALYSIS", "true").lower() in ("1", "true", "yes", "on")
        reuse_code = os.getenv("PIPELINE_REUSE_CODE", "false").lower() in ("1", "true", "yes", "on")
        reuse_tests = os.getenv("PIPELINE_REUSE_TESTS", "false").lower() in ("1", "true", "yes", "on")

        if repo_path:
            normalized_repo_path = repo_path.replace("\\", "/").lower()
            if "output/generated" in normalized_repo_path:
                # This path should have been redirected to output/bases/ by safe_source_repo_path.
                # If it still reaches here, fall back to the configured base project.
                logger.warning(
                    "repo_path points to output/generated — expected output/bases redirect. "
                    "Falling back to base project. selected_base_project=%s",
                    Path(repo_path).name,
                )
                repo_path = str(self.settings.pipeline.target_repo_path)
            else:
                logger.info("resolved_base_project_path=%s", repo_path)

        self.emitter.emit("pipeline_started", message=f"Pipeline started for: {user_story_input[:60]}")

        state: Optional[PipelineState] = None
        try:
            # ── Load or create checkpoint state ───────────────────────
            state = self._load_or_create_state(
                user_story_input, resume, resume_from,
                fallback_output_path=fallback_output_path,
            )
            state.attach_emitter(self.emitter)

            # ── Step 1: resolve user story ────────────────────────────
            if self._should_run(state, "resolve_user_story", resume_from):
                self.emitter.emit("step_started", step="resolve_user_story", message="Resolving user story")
                logger.info("📥 [STEP 1] Résolution de la User Story")
                state.mark_running("resolve_user_story")
                user_story = await self._resolve_user_story(user_story_input)
                state.artifacts["user_story"] = {
                    "id": user_story.id, "title": user_story.title,
                    "description": user_story.description,
                    "acceptance_criteria": user_story.acceptance_criteria,
                    "priority": user_story.priority, "story_points": user_story.story_points,
                    "labels": user_story.labels, "epic": user_story.epic, "raw": user_story.raw,
                }
                state.mark_completed("resolve_user_story", "user_story")
                self._save_state(state)
                logger.info(f"  ✓ US: [{user_story.id}] {user_story.title}")
            else:
                user_story = self._restore_user_story(state)
                logger.info(f"  ♻️ US restaurée depuis checkpoint: [{user_story.id}]")

            # ── Step 2: documentation ─────────────────────────────────
            if self._should_run(state, "load_docs", resume_from):
                logger.info("📚 [STEP 2] Chargement documentation")
                state.mark_running("load_docs")
                docs = await self.doc_loader.load_all()
                state.artifacts["docs_count"] = len(docs)
                state.mark_completed("load_docs")
                self._save_state(state)
                logger.info(f"  ✓ {len(docs)} document(s)")
            else:
                docs = await self.doc_loader.load_all()
                logger.info(f"  ♻️ Docs rechargés ({len(docs)})")

            # ── Step 3: advisor ───────────────────────────────────────
            if self._should_run(state, "advisor", resume_from):
                logger.info("🧠 [STEP 3] Implementation Advisor")
                state.mark_running("advisor")
                analysis_cache = self.settings.pipeline.artifacts_dir / f"analysis_{user_story.id}.json"
                cached_analysis = (
                    self._load_analysis_cache(analysis_cache, user_story, docs)
                    if reuse_analysis and analysis_cache.exists()
                    else None
                )
                if cached_analysis is not None:
                    analysis = cached_analysis
                    logger.info("  ♻️ Analyse depuis cache")
                else:
                    analysis = await self.advisor.analyze(user_story, docs)
                    self._save_analysis_cache(analysis_cache, user_story, docs, analysis)
                self._save_artifact("analysis.json", analysis.to_dict())
                state.artifacts["analysis"] = analysis.to_dict()
                state.mark_completed("advisor", "analysis")
                self._save_state(state)
                logger.info(f"  ✓ {len(analysis.entities)} entité(s), {len(analysis.endpoints)} endpoint(s)")
            else:
                analysis = AnalysisResult.from_dict(state.artifacts["analysis"])
                logger.info(f"  ♻️ Analyse restaurée depuis checkpoint")

            us_intent = self._build_intent_summary(user_story, analysis)

            # ── Step 4: analyzer (optional in bootstrap mode) ─────────
            if self._should_run(state, "analyzer", resume_from):
                logger.info("🔍 [STEP 4] Repository Analyzer")
                state.mark_running("analyzer")
                if repo_path:
                    try:
                        repo_analysis = await self.analyzer.analyze(
                            repo_path=repo_path,
                            us_intent=us_intent,
                        )
                    except ValueError as e:
                        state.mark_failed("analyzer", str(e))
                        self._save_state(state)
                        raise  # FATAL — stop pipeline
                else:
                    repo_analysis = self._empty_repo_analysis()
                    logger.info("  ⏭️ Analyzer ignoré — aucun repo_path fourni (mode bootstrap)")
                self._save_artifact("repo_analysis.json", repo_analysis.to_dict())
                state.artifacts["repo_analysis"] = repo_analysis.to_dict()
                state.mark_completed("analyzer", "repo_analysis")
                self._save_state(state)
                logger.info(f"  ✓ {len(repo_analysis.relevant_files)} fichier(s) pertinent(s)")
            else:
                from core.models import RepoAnalysis
                ra = state.artifacts.get("repo_analysis", {})
                repo_analysis = RepoAnalysis(
                    repo_path=ra.get("repo_path", repo_path or ""),
                    languages=ra.get("languages", []),
                    frameworks=ra.get("frameworks", []),
                    build_system=ra.get("build_system", "maven"),
                    build_commands=ra.get("build_commands", {}),
                    entry_points=ra.get("entry_points", []),
                    relevant_files=ra.get("relevant_files", []),
                    potentially_impacted=ra.get("potentially_impacted", []),
                    existing_patterns=ra.get("existing_patterns", []),
                    change_map=ra.get("change_map", {}),
                    risks=ra.get("risks", []),
                    summary=ra.get("summary", ""),
                )
                logger.info("  ♻️ RepoAnalysis restaurée depuis checkpoint")

            # ── Step 5: planner ───────────────────────────────────────
            if self._should_run(state, "planner", resume_from):
                logger.info("📋 [STEP 5] Planner")
                state.mark_running("planner")
                graphrag_snippet = self._get_graphrag_snippet(user_story.id)

                # ── Attempt 1 ────────────────────────────────────────
                plan = await self.planner.plan(
                    us_intent=us_intent,
                    repo_analysis=repo_analysis,
                    graphrag_snippet=graphrag_snippet,
                )
                plan = self._normalize_plan_paths_against_analysis(user_story, analysis, plan)
                plan, rejected = self._sanitize_plan(plan, user_story, analysis)

                if rejected:
                    logger.warning(f"  ⚠ Sanitization removed {len(rejected)} out-of-scope file(s): {rejected}")
                    logger.warning("  ↻ Retrying planner with explicit forbidden list...")
                    forbidden_hint = (
                        f"\n## FORBIDDEN RESOURCES — DO NOT INCLUDE\n"
                        f"The following resources were detected as out-of-scope in your previous plan.\n"
                        f"You MUST NOT include them again:\n"
                        + "\n".join(f"  - {r}" for r in rejected)
                    )
                    plan2 = await self.planner.plan(
                        us_intent=us_intent,
                        repo_analysis=repo_analysis,
                        graphrag_snippet=graphrag_snippet,
                        extra_context=forbidden_hint,
                    )
                    plan2 = self._normalize_plan_paths_against_analysis(user_story, analysis, plan2)
                    plan2, rejected2 = self._sanitize_plan(plan2, user_story, analysis)
                    if rejected2:
                        logger.error(f"  ✗ Retry still produced out-of-scope resources: {rejected2}")
                    plan = plan2
                    rejected = rejected2

                plan_validation = self._validate_plan_alignment(user_story, analysis, plan)
                state.artifacts["plan_validation"] = plan_validation
                state.artifacts["plan_rejected_resources"] = rejected

                if not plan_validation["passed"]:
                    message = " | ".join(plan_validation["issues"])
                    allowed = self._allowed_domain_tokens(user_story, analysis)
                    found = {
                        token
                        for task in plan.subtasks
                        for path in (task.files_to_create + task.files_to_edit)
                        for token in self._extract_resource_tokens_from_path(path)
                    }
                    unexpected = sorted(t for t in found if t not in allowed and t not in self._generic_resource_tokens())
                    logger.error("  ✗ Plan rejected after sanitization — misalignment detected")
                    logger.error(f"    Allowed tokens        : {sorted(allowed)}")
                    logger.error(f"    Found tokens          : {sorted(found)}")
                    logger.error(f"    Unexpected tokens     : {unexpected}")
                    logger.error(f"    Rejected (sanitized)  : {rejected}")
                    state.artifacts["decision_route"] = "story_alignment_failure"
                    state.artifacts["recommended_next_action"] = "refine_plan_against_acceptance_criteria"
                    state.artifacts["pipeline_blocked"] = True
                    state.mark_failed("planner", message)
                    self._save_state(state)
                    raise ValueError(f"Planner output misaligned with user story: {message}")

                self._save_artifact("plan.json", plan.to_dict())
                state.artifacts["plan"] = plan.to_dict()
                state.mark_completed("planner", "plan")
                self._save_state(state)
                logger.info(f"  ✓ {len(plan.subtasks)} subtask(s), {len(plan.execution_groups)} groupe(s)")
            else:
                from core.models import PlanResult, SubTask
                pd = state.artifacts.get("plan", {})
                plan = PlanResult(
                    subtasks=[SubTask(**t) for t in pd.get("subtasks", [])],
                    execution_groups=pd.get("execution_groups", []),
                    risks=pd.get("risks", []),
                    summary=pd.get("summary", ""),
                )
                logger.info("  ♻️ Plan restauré depuis checkpoint")

            # ── Step 6: developer (plan-driven) ───────────────────────
            if self._should_run(state, "developer", resume_from):
                logger.info("👨‍💻 [STEP 6] Developer (plan-driven)")
                state.mark_running("developer")
                existing_code = self._load_existing_project_code(repo_path) if repo_path else None
                if existing_code:
                    logger.info(
                        f"  ♻️ Base projet chargée depuis repo_path "
                        f"({len(existing_code.files)} fichiers texte)"
                    )
                if reuse_code:
                    cached = self._load_generated_code_from_output(user_story.id)
                    if cached:
                        generated_code = cached
                        logger.info("  ♻️ Code depuis cache output/")
                    else:
                        generated_code = await self.developer.generate_from_plan(
                            user_story, analysis, repo_analysis, plan, docs, existing_code=existing_code
                        )
                else:
                    generated_code = await self.developer.generate_from_plan(
                        user_story, analysis, repo_analysis, plan, docs, existing_code=existing_code
                    )
                generated_code = self._fix_application_java(
                    generated_code,
                    analysis,
                    preserve_existing=bool(existing_code),
                )
                planned_paths = {
                    path.replace("\\", "/")
                    for task in plan.subtasks
                    for path in (task.files_to_create + task.files_to_edit)
                }
                code_validation = self._validate_generated_code_alignment(
                    user_story,
                    analysis,
                    generated_code,
                    relevant_paths=planned_paths,
                )
                state.artifacts["code_validation"] = code_validation
                if not code_validation["passed"]:
                    message = " | ".join(code_validation["issues"])
                    state.artifacts["code_validation_warning"] = message
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "Code alignment warning (non-blocking): %s", message
                    )
                self._save_generated_code_artifact(user_story.id, generated_code)
                state.artifacts["generated_code"] = self._generated_code_to_dict(generated_code)
                # Persist generated code in state artifacts (file list only for size)
                state.artifacts["generated_files"] = list(generated_code.files.keys())
                state.mark_completed("developer")
                self._save_state(state)
                self._debug_maybe_crash_after("developer")
                logger.info(f"  ✓ {len(generated_code.files)} fichier(s) générés")
            else:
                generated_code = self._restore_generated_code(state, user_story.id)
                logger.info(f"  ♻️ Code restauré ({len(generated_code.files)} fichiers)")

            # ── Step 7: compile ───────────────────────────────────────
            if self._should_run(state, "compile", resume_from):
                logger.info("⚙️  [STEP 7] Compilation Maven")
                state.mark_running("compile")
                generated_code, compile_result = await self._compile_with_precheck(
                    generated_code, analysis, user_story
                )
                self._save_artifact("compile_report.json", compile_result.to_dict())
                state.artifacts["compile_report"] = compile_result.to_dict()
                state.artifacts["compile_success"] = compile_result.success
                state.artifacts["compile_errors"] = compile_result.error_count
                state.mark_completed("compile")
                self._save_state(state)
            else:
                compile_result = self._restore_compile_result(state)
                logger.info("  ♻️ Résultat compilation depuis checkpoint")

            # ── Step 8: fixer ─────────────────────────────────────────
            fix_result = None
            pre_fixer_generated_code = generated_code
            if self._should_run(state, "fixer", resume_from):
                state.mark_running("fixer")
                if not compile_result.success:
                    compile_failure_type = getattr(compile_result, "failure_type", None)
                    # Trigger fixer on java_compilation_failure OR on
                    # maven_or_build_tool_failure that contains Java error signals.
                    java_signals = (
                        "error:", "cannot find symbol", "package does not exist",
                        "incompatible types", ".java:",
                    )
                    has_java_errors_in_output = any(
                        s in (compile_result.output or "").lower() for s in java_signals
                    )
                    should_fix = (
                        compile_failure_type == "java_compilation_failure"
                        or (compile_failure_type == "maven_or_build_tool_failure" and has_java_errors_in_output)
                    )

                    if should_fix:
                        if compile_failure_type != "java_compilation_failure":
                            logger.info(
                                "🔧 [STEP 8] FixerAgent — triggered on maven_or_build_tool_failure "
                                "with Java error signals in output"
                            )
                        else:
                            logger.info("🔧 [STEP 8] FixerAgent")
                        fix_result = await self.fixer.fix(
                            user_story=user_story,
                            analysis=analysis,
                            generated_code=generated_code,
                            compile_result=compile_result,
                        )
                        if fix_result.fixed_code:
                            generated_code = fix_result.fixed_code
                            compile_result = await self.build_runner.compile_main(generated_code)
                            logger.info(
                                f"  {'✅' if compile_result.success else '⚠️ '} "
                                f"Post-fixer: {compile_result.error_count} erreur(s) | "
                                f"{fix_result.iterations} itération(s)"
                            )
                        self._save_artifact("fix_report.json", fix_result.to_dict())
                    else:
                        state.artifacts["decision_route"] = compile_failure_type or "build_failure"
                        state.artifacts["recommended_next_action"] = self._action_for_compile_failure(
                            compile_failure_type
                        )
                        state.artifacts["pipeline_blocked"] = self._is_infrastructure_failure(
                            compile_failure_type
                        )
                        logger.warning(
                            "⏭️  [STEP 8] Fixer skipped due to non-code compile failure: "
                            f"{compile_failure_type or 'unknown'}"
                        )
                else:
                    logger.info("⏭️  [STEP 8] Fixer — skipped (compilation OK)")
                state.mark_completed("fixer")
                self._save_state(state)

            # Track whether production sources are frozen (immutable after this point)
            production_frozen = compile_result.success
            if production_frozen:
                logger.info("🔒 Production sources frozen after successful compilation")

            # ── Step 9: tester (generates test files) ─────────────────
            fixer_touched_files = self._detect_changed_file_paths(pre_fixer_generated_code, generated_code)
            story_scope = self._build_story_scope(
                user_story=user_story,
                analysis=analysis,
                repo_analysis=repo_analysis,
                plan=plan,
                generated_code=generated_code,
                fixer_touched_files=fixer_touched_files,
            )
            state.artifacts["story_scope"] = story_scope.to_dict()
            self._save_artifact(f"story_scope_{user_story.id}.json", story_scope.to_dict())
            self._save_artifact("story_scope.json", story_scope.to_dict())
            self._save_state(state)

            if self._should_run(state, "tester", resume_from):
                logger.info("🧪 [STEP 9] Developer generates tests + TesterAgent validates")
                state.mark_running("tester")

                if reuse_tests:
                    test_result = self._load_test_result_from_cache(user_story.id)
                    if test_result:
                        logger.info("  ♻️ Tests depuis cache")
                    else:
                        test_result = await self._contract_driven_test_generation(
                            user_story, analysis, generated_code, story_scope
                        )
                else:
                    test_result = await self._contract_driven_test_generation(
                        user_story, analysis, generated_code, story_scope
                    )

                logger.info(f"  ✓ {len(test_result.test_files)} fichier(s) de test validés")
                self._save_test_generation_artifact(user_story.id, test_result)
                state.artifacts["test_result"] = test_result.to_dict()
                state.artifacts["test_files_count"] = len(test_result.test_files)
                state.mark_completed("tester")
                self._save_state(state)
            else:
                story_scope_data = state.artifacts.get("story_scope")
                if story_scope_data:
                    story_scope = StoryScope.from_dict(story_scope_data)
                test_result = self._restore_generated_tests(state, user_story.id)
                logger.info("  ♻️ Tests restaurés")

            # ── Step 10: run_tests (mvn test + JaCoCo — REAL metrics) ─
            if self._should_run(state, "run_tests", resume_from):
                logger.info("🧪 [STEP 10] mvn test + JaCoCo (métriques réelles)")
                state.mark_running("run_tests")
                test_fix_retry_attempted = False
                zero_tests_retry_attempted = False
                coverage_retry_attempted = False
                coverage_retry_attempts = 0
                coverage_target_classes: list[str] = []
                coverage_retry_diagnostics: list[dict[str, Any]] = []
                story_coverage_report = StoryCoverageReport(
                    story_id=user_story.id,
                    line_coverage=None,
                    branch_coverage=None,
                )
                last_valid_story_coverage_report = StoryCoverageReport(
                    story_id=user_story.id,
                    line_coverage=None,
                    branch_coverage=None,
                )
                global_coverage = None
                global_branch_coverage = None
                last_valid_global_coverage = None
                last_valid_global_branch_coverage = None
                if compile_result.success:
                    execution_test_files = self._prepare_test_files_for_execution(
                        generated_code,
                        test_result,
                        analysis,
                        story_scope,
                    )
                    run_result = await self.build_runner.run_tests(
                        generated_code,
                        execution_test_files,
                    )
                    run_failure_type = getattr(run_result, "failure_type", None)
                    if run_failure_type in ("test_assertion_failure", "test_compilation_failure"):
                        test_fix_retry_attempted = True
                        if run_failure_type == "test_assertion_failure":
                            logger.info("  Test assertion failure detected — repairing tests only")
                        else:
                            logger.info("  Test compilation failure detected — repairing test sources only")
                        repaired_test_files = await self.tester.validate_and_repair_tests(
                            test_result.test_files,
                            analysis.test_contract,
                            generated_code,
                            analysis,
                            errors=(run_result.output or "")[:3000],
                            error_type=run_failure_type,
                        )
                        if repaired_test_files:
                            test_result = TestResult(
                                coverage=0.0,
                                passed=False,
                                test_files=repaired_test_files,
                                test_summary=(
                                    f"Test repair ({run_failure_type}) — "
                                    f"{len(repaired_test_files)} file(s)"
                                ),
                                generation_mode="test_fix",
                            )
                            logger.info("  Test-only repair applied")
                            # Production code is frozen — no recompile needed
                            execution_test_files = self._prepare_test_files_for_execution(
                                generated_code,
                                test_result,
                                analysis,
                                story_scope,
                            )
                            run_result = await self.build_runner.run_tests(
                                generated_code,
                                execution_test_files,
                            )
                    if getattr(run_result, "success", False) and int(getattr(run_result, "total_tests", 0) or 0) == 0:
                        zero_tests_retry_attempted = True
                        logger.warning("  Zero tests discovered - regenerating tests from contract once")
                        regenerated_tests = await self._contract_driven_test_generation(
                            user_story, analysis, generated_code, story_scope
                        )
                        test_result = regenerated_tests
                        self._save_test_generation_artifact(user_story.id, regenerated_tests)
                        state.artifacts["test_files_count"] = len(regenerated_tests.test_files)
                        state.artifacts["run_tests_skipped"] = False
                        state.artifacts["run_tests_skip_reason"] = None
                        execution_test_files = self._prepare_test_files_for_execution(
                            generated_code,
                            regenerated_tests,
                            analysis,
                            story_scope,
                        )
                        run_result = await self.build_runner.run_tests(
                            generated_code,
                            execution_test_files,
                        )
                    global_coverage = getattr(run_result, "line_coverage", None)
                    global_branch_coverage = getattr(run_result, "branch_coverage", None)
                    story_coverage_report = self.compute_story_scoped_coverage(run_result, story_scope)
                    if getattr(run_result, "coverage_source", None) == "jacoco" and story_coverage_report.line_coverage is not None:
                        last_valid_story_coverage_report = story_coverage_report
                        last_valid_global_coverage = global_coverage
                        last_valid_global_branch_coverage = global_branch_coverage
                    measured_coverage = story_coverage_report.line_coverage
                    _auto_retry_enabled = os.getenv(
                        "AUTO_COVERAGE_RETRY_ENABLED", "false"
                    ).lower() in ("1", "true", "yes", "on")

                    if (
                        not _auto_retry_enabled
                        and getattr(run_result, "success", False)
                        and int(getattr(run_result, "total_tests", 0) or 0) > 0
                        and getattr(run_result, "coverage_source", None) == "jacoco"
                        and measured_coverage is not None
                        and measured_coverage < self.settings.pipeline.min_test_coverage
                    ):
                        logger.warning(
                            "  Coverage below threshold: story=%.1f%%, required=%.1f%%. "
                            "Automatic coverage retry is disabled. "
                            "Manual test improvement required.",
                            measured_coverage,
                            self.settings.pipeline.min_test_coverage,
                        )
                        coverage_retry_diagnostics.append({
                            "attempt": 0,
                            "status": "retry_disabled",
                            "story_coverage": measured_coverage,
                            "required_coverage": self.settings.pipeline.min_test_coverage,
                            "message": "AUTO_COVERAGE_RETRY_ENABLED=false — manual improvement required",
                        })

                    elif _auto_retry_enabled:
                        while (
                            getattr(run_result, "success", False)
                            and int(getattr(run_result, "total_tests", 0) or 0) > 0
                            and getattr(run_result, "coverage_source", None) == "jacoco"
                            and measured_coverage is not None
                            and measured_coverage < self.settings.pipeline.min_test_coverage
                            and coverage_retry_attempts < 2
                        ):
                            coverage_target_classes = self._select_low_coverage_targets(
                                generated_code,
                                run_result,
                                story_scope=story_scope,
                            )
                            coverage_retry_attempted = True
                            coverage_retry_attempts += 1
                            if not coverage_target_classes:
                                logger.warning(
                                    "  Story-scoped coverage below threshold but no scoped JaCoCo targets were found"
                                )
                                coverage_retry_diagnostics.append({
                                    "attempt": coverage_retry_attempts,
                                    "status": "no_targets",
                                    "story_coverage": measured_coverage,
                                })
                                break

                            logger.warning(
                                "  Story coverage below threshold - regenerating targeted tests "
                                f"(attempt {coverage_retry_attempts}/2) for "
                                + ", ".join(coverage_target_classes[:5])
                            )
                            previous_tests = dict(test_result.test_files)
                            improved_tests = await self.tester.test(
                                generated_code,
                                analysis,
                                story_scope=story_scope,
                                mode="coverage_retry_targeted",
                                target_classes=coverage_target_classes,
                                retry_reason=f"jacoco_low_coverage_attempt_{coverage_retry_attempts}",
                                retry_attempt=coverage_retry_attempts,
                                existing_test_files=test_result.test_files,
                            )
                            material_delta = self.has_material_test_change(
                                previous_tests,
                                improved_tests.test_files,
                                target_classes=coverage_target_classes,
                            )
                            coverage_retry_diagnostics.append({
                                "attempt": coverage_retry_attempts,
                                "status": "generated",
                                "target_classes": coverage_target_classes,
                                "material_delta": material_delta,
                                "weak_test_files": improved_tests.metadata.get("weak_test_files", []),
                                "diagnostics": improved_tests.metadata.get("diagnostics", []),
                            })
                            test_result = improved_tests
                            if not material_delta.get("changed", False):
                                logger.warning("  Coverage retry stopped early: no material test delta was produced")
                                break
                            self._save_test_generation_artifact(user_story.id, improved_tests)
                            state.artifacts["test_files_count"] = len(improved_tests.test_files)
                            state.artifacts["run_tests_skipped"] = False
                            state.artifacts["run_tests_skip_reason"] = None
                            execution_test_files = self._prepare_test_files_for_execution(
                                generated_code,
                                improved_tests,
                                analysis,
                                story_scope,
                            )
                            run_result = await self.build_runner.run_tests(
                                generated_code,
                                execution_test_files,
                            )
                            global_coverage = getattr(run_result, "line_coverage", None)
                            global_branch_coverage = getattr(run_result, "branch_coverage", None)
                            story_coverage_report = self.compute_story_scoped_coverage(run_result, story_scope)
                            if getattr(run_result, "coverage_source", None) == "jacoco" and story_coverage_report.line_coverage is not None:
                                last_valid_story_coverage_report = story_coverage_report
                                last_valid_global_coverage = global_coverage
                                last_valid_global_branch_coverage = global_branch_coverage
                            elif getattr(run_result, "failure_type", None) == "test_compilation_failure":
                                coverage_retry_diagnostics.append({
                                    "attempt": coverage_retry_attempts,
                                    "status": "retry_test_compilation_failure",
                                    "target_classes": coverage_target_classes,
                                    "failure_type": getattr(run_result, "failure_type", None),
                                })
                            measured_coverage = story_coverage_report.line_coverage

                    self._save_artifact(f"test_run_{user_story.id}.json", run_result.to_dict())
                else:
                    compile_failure_type = getattr(compile_result, "failure_type", None) or "build_failure"
                    logger.warning(
                        "  mvn test skipped because compilation is still failing "
                        f"(type={compile_failure_type})"
                    )
                    run_result = {
                        "success": False,
                        "total_tests": 0,
                        "passed_tests": 0,
                        "failed_tests": 0,
                        "error_tests": 0,
                        "skipped_tests": 0,
                        "failed_test_names": [],
                        "coverage_source": "fallback",
                        "failure_type": "skipped_due_to_compile_failure",
                        "return_code": None,
                        "surefire_report_issue": None,
                        "workspace_path": None,
                        "written_test_files": list(test_result.test_files.keys()),
                        "effective_pom_has_jacoco": False,
                    }
                    state.artifacts["run_tests_skipped"] = True
                    state.artifacts["run_tests_skip_reason"] = compile_failure_type
                    self._save_artifact(f"test_run_{user_story.id}.json", run_result)

                # Preserve the last valid JaCoCo measurement if a retry broke test compilation.
                if (
                    getattr(run_result, "coverage_source", None) != "jacoco"
                    and last_valid_story_coverage_report.line_coverage is not None
                ):
                    story_coverage_report = last_valid_story_coverage_report
                    global_coverage = last_valid_global_coverage
                    global_branch_coverage = last_valid_global_branch_coverage

                # Override TestResult with real metrics
                real_coverage = story_coverage_report.line_coverage
                if real_coverage is not None:
                    logger.info(
                        f"  ✅ Couverture réelle story-scope (JaCoCo): {real_coverage}%"
                        f" | globale: {global_coverage if global_coverage is not None else 'n/a'}%"
                    )
                    test_result = TestResult(
                        coverage=real_coverage,
                        passed=run_result.success if hasattr(run_result, "success") else False,
                        test_files=test_result.test_files,
                        test_summary=(
                            f"mvn test: {run_result.passed_tests if hasattr(run_result, 'passed_tests') else 0}/{run_result.total_tests if hasattr(run_result, 'total_tests') else 0} passed "
                            f"| story line coverage: {real_coverage}%"
                        ),
                        failed_tests=run_result.failed_test_names() if hasattr(run_result, "failed_test_names") else [],
                        coverage_details={
                            "line": real_coverage,
                            "branch": story_coverage_report.branch_coverage if story_coverage_report.branch_coverage is not None else 0.0,
                            "global_line": global_coverage if global_coverage is not None else 0.0,
                            "global_branch": global_branch_coverage if global_branch_coverage is not None else 0.0,
                        },
                        coverage_source="jacoco",
                        coverage_gate_mode="strict",
                        generation_mode=test_result.generation_mode,
                        metadata={
                            **dict(test_result.metadata or {}),
                            "story_scope": story_scope.to_dict(),
                            "story_coverage": story_coverage_report.to_dict(),
                            "global_coverage": {
                                "line_coverage": global_coverage,
                                "branch_coverage": global_branch_coverage,
                            },
                            "coverage_retry_diagnostics": coverage_retry_diagnostics,
                        },
                    )
                else:
                    # JaCoCo not available — keep estimated coverage, mark failed
                    logger.warning("  ⚠️  JaCoCo non disponible — couverture estimée conservée")
                    test_result = TestResult(
                        coverage=test_result.coverage,
                        passed=run_result.success if hasattr(run_result, "success") else False,
                        test_files=test_result.test_files,
                        test_summary=(
                            f"mvn test: {run_result.passed_tests if hasattr(run_result, 'passed_tests') else 0}/{run_result.total_tests if hasattr(run_result, 'total_tests') else 0} passed "
                            f"| coverage estimated: {test_result.coverage}% (JaCoCo missing)"
                        ),
                        failed_tests=run_result.failed_test_names() if hasattr(run_result, "failed_test_names") else [],
                        coverage_details=test_result.coverage_details,
                        coverage_source="fallback",
                        coverage_gate_mode="degraded",
                        generation_mode=test_result.generation_mode,
                        metadata={
                            **dict(test_result.metadata or {}),
                            "story_scope": story_scope.to_dict(),
                            "story_coverage": story_coverage_report.to_dict(),
                            "global_coverage": {
                                "line_coverage": global_coverage,
                                "branch_coverage": global_branch_coverage,
                            },
                            "coverage_retry_diagnostics": coverage_retry_diagnostics,
                        },
                    )

                self._save_artifact(f"test_report_{user_story.id}.json", test_result.to_dict())
                self._save_artifact(f"story_coverage_{user_story.id}.json", story_coverage_report.to_dict())
                state.artifacts["test_run"] = run_result.to_dict() if hasattr(run_result, "to_dict") else run_result
                state.artifacts["test_result"] = test_result.to_dict()
                state.artifacts["test_coverage"] = test_result.coverage
                state.artifacts["tests_passed"] = test_result.passed
                state.artifacts["coverage_source"] = test_result.coverage_source
                state.artifacts["coverage_gate_mode"] = test_result.coverage_gate_mode
                state.artifacts["story_coverage"] = story_coverage_report.to_dict()
                state.artifacts["story_coverage_line"] = story_coverage_report.line_coverage
                state.artifacts["story_coverage_branch"] = story_coverage_report.branch_coverage
                state.artifacts["global_coverage_line"] = global_coverage
                state.artifacts["global_coverage_branch"] = global_branch_coverage
                state.artifacts["test_fix_retry_attempted"] = test_fix_retry_attempted
                state.artifacts["zero_tests_retry_attempted"] = zero_tests_retry_attempted
                state.artifacts["coverage_retry_attempted"] = coverage_retry_attempted
                state.artifacts["coverage_retry_attempts"] = coverage_retry_attempts
                state.artifacts["coverage_target_classes"] = coverage_target_classes
                state.artifacts["coverage_retry_diagnostics"] = coverage_retry_diagnostics
                state.mark_completed("run_tests")
                self._save_state(state)
            else:
                test_result = self._restore_test_result(state, user_story.id)
                logger.info(f"  ♻️ Résultat tests depuis checkpoint (coverage={test_result.coverage}%)")

            # ── Step 11: reviewer ─────────────────────────────────────
            if self._should_run(state, "reviewer", resume_from):
                logger.info("🔍 [STEP 11] Reviewer")
                state.mark_running("reviewer")
                review_result, generated_code = await self._review_and_correct(
                    generated_code, analysis, user_story, docs
                )
                self._save_artifact("review_report.json", review_result.to_dict())
                review_ok = self._is_review_accepted(review_result)
                state.artifacts["review_score"] = review_result.score
                state.artifacts["review_approved"] = review_ok
                state.mark_completed("reviewer")
                self._save_state(state)
            else:
                review_result = ReviewResult(
                    score=state.artifacts.get("review_score", 0),
                    approved=state.artifacts.get("review_approved", False),
                    summary="Restauré depuis checkpoint",
                    issues=[], positives=[], correction_prompt="",
                )
                logger.info(f"  ♻️ Review depuis checkpoint (score={review_result.score})")

            # ── Step 12: write_files ──────────────────────────────────
            if self._should_run(state, "write_files", resume_from):
                logger.info("💾 [STEP 12] Écriture des fichiers")
                state.mark_running("write_files")
                output_path = self._write_all(generated_code, test_result, user_story.id)
                state.artifacts["output_path"] = str(output_path)
                state.mark_completed("write_files")
                self._save_state(state)
                logger.info(f"  ✓ Fichiers dans: {output_path}")
            else:
                output_path = Path(state.artifacts.get("output_path", str(
                    self.settings.pipeline.output_dir / user_story.id
                )))
                logger.info(f"  ♻️ Output path depuis checkpoint: {output_path}")

            # ── Step 13: quality_gate ─────────────────────────────────
            compile_ok = compile_result.success
            test_run_data = state.artifacts.get("test_run", {})
            total_tests_run = int(test_run_data.get("total_tests", 0) or 0)
            test_run_success = bool(test_run_data.get("success", False))
            zero_tests_discovered = test_run_success and total_tests_run == 0
            story_coverage_data = state.artifacts.get("story_coverage", {}) or {}
            story_line_coverage = story_coverage_data.get("line_coverage", test_result.coverage)
            story_branch_coverage = story_coverage_data.get("branch_coverage")
            global_line_coverage = state.artifacts.get("global_coverage_line")
            global_branch_coverage = state.artifacts.get("global_coverage_branch")
            coverage_measured = test_result.coverage_source == "jacoco"
            coverage_gate_mode = "strict" if coverage_measured else "degraded"
            coverage_below_threshold = (
                story_line_coverage < self.settings.pipeline.min_test_coverage
                if coverage_measured else False
            )
            coverage_ok = coverage_measured and not coverage_below_threshold
            tests_ok = test_result.passed and not zero_tests_discovered
            review_ok = self._is_review_accepted(review_result)
            quality_report = self.quality_analyzer.analyze(generated_code, test_run_data)
            quality_scan_ok = quality_report.passed
            self._save_artifact("quality_report.json", quality_report.to_dict())
            failure_types = self._build_failure_types(
                compile_result,
                test_result,
                coverage_ok,
                zero_tests_discovered,
            )
            if not quality_scan_ok:
                failure_types.append("quality_policy_failure")
            primary_failure_type = failure_types[0] if failure_types else None
            test_failure_type = test_run_data.get("failure_type")
            decision_route, recommended_next_action, pipeline_blocked = self._determine_next_action(
                compile_failure_type=getattr(compile_result, "failure_type", None),
                test_failure_type=test_failure_type,
                zero_tests_discovered=zero_tests_discovered,
                coverage_below_threshold=coverage_below_threshold,
                primary_failure_type=primary_failure_type,
                quality_scan_failed=not quality_scan_ok,
            )

            logger.info("📊 [STEP 13] Bilan qualité:")
            logger.info(f"  Compilation   : {'✅' if compile_ok else '❌'}")
            logger.info(f"  Tests passent : {'✅' if tests_ok else '❌'}")
            logger.info(
                f"  Validation    : {'FAIL' if (zero_tests_discovered or not test_run_success) else 'PASS'} "
                f"tests_detected={total_tests_run}"
            )
            logger.info(
                f"  Couverture    : {'PASS' if coverage_ok else 'FAIL'} "
                f"story={story_line_coverage}% branch={story_branch_coverage if story_branch_coverage is not None else 'n/a'} "
                f"| global={global_line_coverage if global_line_coverage is not None else 'n/a'}% "
                f"({test_result.coverage_source}, mode={coverage_gate_mode})"
            )
            if not coverage_measured:
                logger.warning("  Couverture degradee: JaCoCo absent, la gate couverture echoue explicitement")
            logger.info(f"  Review        : {'PASS' if review_ok else 'FAIL'} {review_result.score}/100")
            logger.info(
                f"  Qualite       : {'PASS' if quality_scan_ok else 'FAIL'} "
                f"dup={quality_report.metrics.get('duplication_percent', 0)}% "
                f"complexity={quality_report.metrics.get('max_cyclomatic_complexity', 0)} "
                f"skipped={quality_report.metrics.get('skipped_tests', 0)}"
            )
            logger.info(
                f"  Next action   : {recommended_next_action} "
                f"(route={decision_route}, blocked={pipeline_blocked})"
            )

            state.artifacts["coverage_source"] = test_result.coverage_source
            state.artifacts["coverage_gate_mode"] = coverage_gate_mode
            state.artifacts["coverage_ok"] = coverage_ok
            state.artifacts["coverage_below_threshold"] = coverage_below_threshold
            state.artifacts["zero_tests_discovered"] = zero_tests_discovered
            state.artifacts["total_tests_run"] = total_tests_run
            state.artifacts["quality_report"] = quality_report.to_dict()
            state.artifacts["quality_scan_passed"] = quality_scan_ok
            state.artifacts["failure_types"] = failure_types
            state.artifacts["primary_failure_type"] = primary_failure_type
            state.artifacts["decision_route"] = decision_route
            state.artifacts["recommended_next_action"] = recommended_next_action
            state.artifacts["pipeline_blocked"] = pipeline_blocked
            state.mark_completed("quality_gate")
            self._save_state(state)

            # ── Step 14: commit ───────────────────────────────────────
            commit_sha = None
            # Require: compile + tests pass + coverage + review + deterministic quality checks
            all_ok = compile_ok and tests_ok and coverage_ok and review_ok and quality_scan_ok

            if self._should_run(state, "commit", resume_from):
                state.mark_running("commit")
                # ── File-review gate ──────────────────────────────────
                if not files_approved:
                    logger.warning(
                        "⛔ [STEP 14] GitHub push blocked — generated files not fully accepted"
                    )
                    self.emitter.emit(
                        "step_failed",
                        step="git_push",
                        status="skipped",
                        message="GitHub push blocked: generated files are not fully accepted by reviewer",
                    )
                    state.mark_failed(
                        "commit",
                        "GitHub push blocked: generated files are not fully accepted",
                    )
                    self._save_state(state)
                    # Inject blocking reason into artifacts so result dict captures it
                    state.artifacts.setdefault("decision_route", "file_review_blocked")
                    state.artifacts.setdefault("recommended_next_action", "accept_all_files_then_commit")
                    state.artifacts["pipeline_blocked"] = True
                elif all_ok:
                    if not dry_run:
                        if repo_path and self._is_local_git_repo(repo_path):
                            logger.info("🚀 [STEP 14] Commit Git local")
                            commit_sha = await LocalGitClient(repo_path).commit_code(
                                user_story=user_story,
                                generated_code=generated_code,
                                test_result=test_result,
                            )
                        else:
                            logger.info("🚀 [STEP 14] Commit GitHub")
                            commit_sha = await self.github.commit_code(
                                user_story=user_story,
                                generated_code=generated_code,
                                test_result=test_result,
                                branch=f"feature/{user_story.id.lower()}",
                                base_branch=(
                                    self.settings.github.base_branch
                                    or self.settings.github.default_branch
                                ),
                            )
                        logger.info(f"  ✓ Commit: {commit_sha}")
                        if _is_jira_id(user_story_input):
                            await self.jira.update_status(user_story.id, "In Review")
                            logger.info("  ✓ Jira → 'In Review'")
                    else:
                        logger.info("🔍 [STEP 14] DRY RUN — commit simulé")
                    state.artifacts["commit_sha"] = commit_sha
                    state.mark_completed("commit")
                else:
                    reasons = []
                    if not compile_ok:
                        reasons.append(f"compilation: {compile_result.error_count} erreur(s)")
                    if not tests_ok:
                        if zero_tests_discovered:
                            reasons.append("validation insuffisante: zero test execute")
                        else:
                            reasons.append("tests échouent (mvn test)")
                    if not coverage_ok:
                        if coverage_measured:
                            reasons.append(
                                f"couverture: {test_result.coverage}% < "
                                f"{self.settings.pipeline.min_test_coverage}%"
                            )
                        else:
                            reasons.append(
                                f"couverture non mesuree: source={test_result.coverage_source}"
                            )
                    if not review_ok:
                        min_rs = self.settings.pipeline.min_review_score
                        reasons.append(f"review: {review_result.score}/100 < {min_rs}")
                    if not quality_scan_ok:
                        quality_issue = quality_report.issues[0].message if quality_report.issues else "quality policy failure"
                        reasons.append(f"quality: {quality_issue}")
                    logger.warning(f"⚠️  Commit bloqué — {' | '.join(reasons)}")
                    state.mark_failed("commit", " | ".join(reasons))
                self._save_state(state)

            execution_summary = self._build_execution_summary(
                state=state,
                final_status="succeeded" if all_ok else "blocked",
            )
            state.artifacts["execution_summary"] = execution_summary
            self._save_artifact(f"execution_summary_{user_story.id}.json", execution_summary)
            self._save_artifact("execution_summary.json", execution_summary)
            # Redundant copy in output_path (persistent volume on Azure) so
            # commit-only reconstruction works after container restarts.
            try:
                out_summary_dir = Path(state.artifacts.get("output_path", "")) or output_path
                if out_summary_dir and Path(str(out_summary_dir)).exists():
                    out_s = Path(str(out_summary_dir)) / f"execution_summary_{user_story.id}.json"
                    out_s.write_text(
                        json.dumps(execution_summary, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
            except Exception as _es_err:
                logger.debug("  Could not write redundant execution_summary to output_path: %s", _es_err)
            self._save_state(state)

            self.emitter.emit(
                "pipeline_completed",
                status="success",
                message=f"Pipeline completed for [{user_story.id}]",
                all_gates_passed=all_ok,
                coverage=test_result.coverage,
                compile_success=compile_result.success,
            )
            return {
                "user_story":      {"id": user_story.id, "title": user_story.title},
                "analysis":        {"entities": len(analysis.entities), "endpoints": len(analysis.endpoints)},
                "repo_analysis":   {"relevant_files": len(repo_analysis.relevant_files), "summary": repo_analysis.summary},
                "plan":            {"subtasks": len(plan.subtasks), "groups": len(plan.execution_groups)},
                "files_generated": len(generated_code.files),
                "compile_success": compile_result.success,
                "compile_errors":  compile_result.error_count,
                "fix_iterations":  fix_result.iterations if fix_result else 0,
                "tests_passed":    test_result.passed,
                "tests_validation_ok": tests_ok,
                "zero_tests_discovered": zero_tests_discovered,
                "total_tests_run": total_tests_run,
                "test_coverage":   test_result.coverage,
                "story_coverage_line": state.artifacts.get("story_coverage_line"),
                "story_coverage_branch": state.artifacts.get("story_coverage_branch"),
                "global_coverage_line": state.artifacts.get("global_coverage_line"),
                "global_coverage_branch": state.artifacts.get("global_coverage_branch"),
                "coverage_source": test_result.coverage_source,
                "coverage_gate_mode": coverage_gate_mode,
                "coverage_ok": coverage_ok,
                "coverage_below_threshold": coverage_below_threshold,
                "coverage_retry_attempts": int(state.artifacts.get("coverage_retry_attempts", 0) or 0),
                "coverage_target_classes": state.artifacts.get("coverage_target_classes", []),
                "coverage_retry_diagnostics": state.artifacts.get("coverage_retry_diagnostics", []),
                "story_scope": state.artifacts.get("story_scope"),
                "failure_types": failure_types,
                "primary_failure_type": primary_failure_type,
                "decision_route": decision_route,
                "recommended_next_action": recommended_next_action,
                "pipeline_blocked": pipeline_blocked,
                "review_score":    review_result.score,
                "review_approved": review_ok,
                "quality_scan_passed": quality_scan_ok,
                "quality_metrics": quality_report.metrics,
                "quality_issues": [issue.to_dict() for issue in quality_report.issues[:10]],
                "all_gates_passed": all_ok,
                "repo_path":       str(repo_path) if repo_path else None,
                "output_path":     str(output_path),
                "commit_sha":      commit_sha,
            }
        except Exception as e:
            if state is not None:
                failed_step = self._current_running_step(state) or "pipeline"
                state.artifacts["failure_types"] = ["internal_pipeline_failure"]
                state.artifacts["primary_failure_type"] = "internal_pipeline_failure"
                state.artifacts["failed_step"] = failed_step
                if failed_step in state.steps:
                    state.mark_failed(failed_step, str(e))
                else:
                    state.artifacts["pipeline_error"] = str(e)
                execution_summary = self._build_execution_summary(
                    state=state,
                    final_status="failed",
                )
                state.artifacts["execution_summary"] = execution_summary
                self._save_artifact(f"execution_summary_{state.user_story_id}.json", execution_summary)
                self._save_artifact("execution_summary.json", execution_summary)
                self._save_state(state)
            self.emitter.emit(
                "pipeline_failed",
                status="failed",
                message=str(e),
            )
            raise

    # ──────────────────────────────────────────────────────────────
    #  Checkpoint helpers
    # ──────────────────────────────────────────────────────────────

    def _state_file(self, user_story_input: str) -> Path:
        key = hashlib.md5(user_story_input.encode()).hexdigest()[:8]
        return self.settings.pipeline.artifacts_dir / f"pipeline_state_{key}.json"

    def _load_or_create_state(
        self,
        user_story_input: str,
        resume: bool,
        resume_from: Optional[str] = None,
        fallback_output_path: Optional[str] = None,
    ) -> PipelineState:
        state_file = self._state_file(user_story_input)
        logger.info(
            "  [checkpoint] key=%r | path=%s | exists=%s | resume=%s | resume_from=%s",
            user_story_input[:60], state_file, state_file.exists(), resume, resume_from,
        )
        if resume:
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    state = PipelineState.from_dict(data)
                    logger.info("  [checkpoint] loaded: %s", state_file)
                    return state
                except Exception as e:
                    raise ValueError(
                        f"Checkpoint incompatible or unreadable: {state_file} | {e}"
                    ) from e

            # ── Checkpoint missing ────────────────────────────────────
            logger.warning("  [checkpoint] MISSING: %s", state_file)
            if resume_from == "commit":
                logger.info("  [checkpoint] Attempting state reconstruction for commit-only resume")
                reconstructed = self._reconstruct_state_for_commit(
                    user_story_input,
                    fallback_output_path=fallback_output_path,
                )
                if reconstructed:
                    logger.info("  [checkpoint] State reconstructed — writing to %s", state_file)
                    self._save_state(reconstructed)
                    return reconstructed
                raise FileNotFoundError(
                    f"Checkpoint missing and reconstruction failed — cannot resume commit. "
                    f"Expected: {state_file}. "
                    f"Ensure /app/output is on a persistent volume or re-run the full pipeline."
                )
            raise FileNotFoundError(
                f"Resume requested but checkpoint is missing: {state_file}"
            )
        return PipelineState(user_story_id=user_story_input)

    def _reconstruct_state_for_commit(
        self,
        user_story_input: str,
        fallback_output_path: Optional[str] = None,
    ) -> Optional[PipelineState]:
        """
        When the checkpoint file is missing (Azure container restart / ephemeral
        artifacts dir), try to rebuild enough pipeline state to allow commit-only
        to proceed.  We look for execution_summary and generated_code artifacts
        in the artifacts dir first, then in the persistent output_path dir.
        """
        from core.models import PipelineState, PipelineStep, PIPELINE_STEPS

        stripped = user_story_input.strip()
        m = re.match(r'^([A-Z][A-Z0-9]+-\d+)', stripped)
        story_id = m.group(1) if m else stripped[:30]

        artifacts_dir = self.settings.pipeline.artifacts_dir
        output_dir = Path(self.settings.pipeline.output_dir) / story_id
        fallback_dir = Path(fallback_output_path) if fallback_output_path else None

        # ── 1. Load execution_summary ─────────────────────────────────────────
        summary = None
        summary_candidates = [
            artifacts_dir / f"execution_summary_{story_id}.json",
            artifacts_dir / "execution_summary.json",
            output_dir / f"execution_summary_{story_id}.json",
            output_dir / "execution_summary.json",
        ]
        if fallback_dir:
            summary_candidates += [
                fallback_dir / f"execution_summary_{story_id}.json",
                fallback_dir / "execution_summary.json",
            ]
        for path in summary_candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    us_id = (data.get("user_story") or {}).get("id", "")
                    if us_id == story_id or not us_id:
                        summary = data
                        logger.info("  [reconstruct] execution_summary: %s", path)
                        break
                except Exception:
                    pass

        if not summary:
            logger.warning("  [reconstruct] No execution_summary found for story_id=%s", story_id)
            return None

        validation = summary.get("validation", {})
        pipeline_blocked = validation.get("pipeline_blocked", True)
        if pipeline_blocked:
            logger.warning(
                "  [reconstruct] execution_summary shows pipeline_blocked=True — "
                "refusing to reconstruct state for commit"
            )
            return None

        # ── 2. Build synthetic PipelineState ─────────────────────────────────
        state = PipelineState(user_story_id=user_story_input)
        for step_name in PIPELINE_STEPS:
            if step_name == "commit":
                break
            state.steps[step_name] = PipelineStep(name=step_name, status="completed")

        # ── 3. Inject mandatory artifacts ─────────────────────────────────────
        us = summary.get("user_story") or {}
        if us:
            state.artifacts["user_story"] = us

        resolved_output = summary.get("output_path") or str(output_dir)
        state.artifacts["output_path"] = resolved_output

        state.artifacts["compile_success"] = validation.get("compile_success", True)
        state.artifacts["compile_report"] = {
            "success": validation.get("compile_success", True),
            "error_count": 0, "errors": [], "warnings": [],
            "duration_seconds": 0.0, "failure_type": None, "return_code": 0,
        }
        state.artifacts["tests_passed"] = validation.get("tests_passed", True)
        state.artifacts["coverage_ok"] = True
        state.artifacts["pipeline_blocked"] = False
        state.artifacts["all_gates_passed"] = True
        state.artifacts["review_score"] = summary.get("review_score", 75)
        state.artifacts["review_approved"] = True
        state.artifacts["test_run"] = {
            "success": True, "total_tests": 1, "passed_tests": 1,
            "failed_tests": 0, "error_tests": 0,
        }
        coverage_value = summary.get("test_coverage") or 50.0
        coverage_source = validation.get("coverage_source", "jacoco")
        state.artifacts["test_result"] = {
            "coverage": coverage_value,
            "passed": True, "test_summary": "Reconstructed from execution_summary",
            "failed_tests": [], "coverage_source": coverage_source,
            "coverage_gate_mode": "strict", "generation_mode": "initial_full", "metadata": {},
        }
        # Inject story_coverage so quality_gate's story_line_coverage is correct
        state.artifacts["story_coverage"] = {
            "story_id": story_id,
            "line_coverage": coverage_value,
            "branch_coverage": None,
            "scoped_classes": [],
            "considered_files": [],
        }

        # ── 4. Load generated_code (needed for GitHub commit) ─────────────────
        gen_candidates = [
            artifacts_dir / f"generated_code_{story_id}.json",
            output_dir / f"generated_code_{story_id}.json",
        ]
        if fallback_dir:
            gen_candidates.append(fallback_dir / f"generated_code_{story_id}.json")

        gen_data = None
        for path in gen_candidates:
            if path.exists():
                try:
                    gen_data = json.loads(path.read_text(encoding="utf-8"))
                    logger.info("  [reconstruct] generated_code artifact: %s", path)
                    break
                except Exception:
                    pass

        if gen_data:
            state.artifacts["generated_code"] = gen_data
        else:
            # Last resort: read source files from output_path directory
            out_dir = Path(resolved_output)
            if out_dir.exists():
                logger.info("  [reconstruct] Loading generated_code from output dir: %s", out_dir)
                state.artifacts["generated_code"] = self._scan_output_dir_to_code_dict(out_dir)
            else:
                logger.warning(
                    "  [reconstruct] Cannot find generated_code — commit will likely fail"
                )

        logger.info(
            "  [reconstruct] State built | story_id=%s | output_path=%s | "
            "has_generated_code=%s",
            story_id, resolved_output,
            bool(state.artifacts.get("generated_code")),
        )
        return state

    def _scan_output_dir_to_code_dict(self, output_dir: Path) -> dict:
        """Read .java + pom.xml from an output directory into the generated_code dict format."""
        files: dict = {}
        pom_xml = ""
        for p in output_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(output_dir).as_posix()
            if p.name == "pom.xml" and not pom_xml:
                pom_xml = p.read_text(encoding="utf-8", errors="replace")
            elif rel.endswith(".java"):
                files[rel] = p.read_text(encoding="utf-8", errors="replace")
        return {"files": files, "pom_xml": pom_xml, "readme": ""}

    def _save_state(self, state: PipelineState) -> None:
        state_file = self._state_file(state.user_story_id)
        self.settings.pipeline.artifacts_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug("  [checkpoint] saved: %s", state_file)

    def _should_run(self, state: PipelineState, step: str, resume_from: Optional[str]) -> bool:
        """
        Returns True if this step should be executed.

        Logic:
        - If resume_from is set: rerun steps at and after resume_from (in order),
          even if they were previously completed.
        - Otherwise: run if not already completed.
        """
        if resume_from:
            steps_list = PIPELINE_STEPS
            if step in steps_list and resume_from in steps_list:
                resume_idx = steps_list.index(resume_from)
                step_idx = steps_list.index(step)
                if step_idx < resume_idx:
                    return False  # before resume point
                return True  # force rerun from the requested resume point onward
        return not state.is_completed(step)

    def _restore_user_story(self, state: PipelineState) -> UserStory:
        data = state.artifacts.get("user_story", {})
        return UserStory(
            id=data.get("id", "UNKNOWN"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            acceptance_criteria=data.get("acceptance_criteria", []),
            priority=data.get("priority", "Medium"),
            story_points=data.get("story_points"),
            labels=data.get("labels", []),
            epic=data.get("epic"),
            raw=data.get("raw", {}),
        )

    # ──────────────────────────────────────────────────────────────
    def _current_running_step(self, state: PipelineState) -> Optional[str]:
        for step_name in PIPELINE_STEPS:
            if state.steps[step_name].status == "running":
                return step_name
        return None

    def _build_failure_types(
        self,
        compile_result: CompileResult,
        test_result: TestResult,
        coverage_ok: bool,
        zero_tests_discovered: bool = False,
    ) -> list[str]:
        failure_types: list[str] = []
        if not compile_result.success:
            failure_types.append(getattr(compile_result, "failure_type", None) or "build_tooling_failure")
        if not test_result.passed:
            test_run_data = getattr(test_result, "test_run", None)
            failure_types.append("test_execution_failure")
        if zero_tests_discovered:
            failure_types.append("zero_tests_discovered")
        if not coverage_ok:
            failure_types.append("coverage_below_threshold")
        return failure_types

    def _is_infrastructure_failure(self, failure_type: Optional[str]) -> bool:
        return failure_type in {
            "environment_or_dependency_failure",
            "maven_or_build_tool_failure",
            "test_environment_or_dependency_failure",
            "test_tooling_failure",
            "maven_test_timeout",
        }

    def _action_for_compile_failure(self, failure_type: Optional[str]) -> str:
        if failure_type == "java_compilation_failure":
            return "compilation_fix_path"
        if self._is_infrastructure_failure(failure_type):
            return "surface_infrastructure_blockage"
        return "investigate_build_failure"

    def _determine_next_action(
        self,
        compile_failure_type: Optional[str],
        test_failure_type: Optional[str],
        zero_tests_discovered: bool,
        coverage_below_threshold: bool,
        primary_failure_type: Optional[str],
        quality_scan_failed: bool,
    ) -> tuple[str, str, bool]:
        if primary_failure_type == "internal_pipeline_failure":
            return "internal_pipeline_failure", "report_pipeline_issue", True
        if quality_scan_failed and primary_failure_type == "quality_policy_failure":
            return "quality_policy_failure", "quality_remediation_path", False
        if compile_failure_type:
            return (
                compile_failure_type,
                self._action_for_compile_failure(compile_failure_type),
                self._is_infrastructure_failure(compile_failure_type),
            )
        if zero_tests_discovered:
            return "zero_tests_discovered", "minimum_test_footprint_path", False
        if test_failure_type in {
            "no_test_sources_written",
            "test_assertion_failure",
            "test_execution_failure",
            "test_compilation_failure",
        }:
            return test_failure_type, "test_logic_fix_path", False
        if coverage_below_threshold:
            auto_coverage_retry_enabled = os.getenv(
                "AUTO_COVERAGE_RETRY_ENABLED", "false"
            ).lower() in ("1", "true", "yes", "on")
            next_action = (
                "coverage_improvement_path"
                if auto_coverage_retry_enabled
                else "manual_test_improvement_required"
            )
            return "coverage_below_threshold", next_action, False
        if test_failure_type == "missing_or_unreadable_test_report":
            return test_failure_type, "test_discovery_reporting_path", False
        if self._is_infrastructure_failure(test_failure_type):
            return test_failure_type, "surface_infrastructure_blockage", True
        return "success", "proceed", False

    def _normalize_story_scope_paths(self, paths: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for path in paths:
            value = str(path or "").replace("\\", "/").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    # ── Contract-driven test generation ──────────────────────────────────────

    async def _contract_driven_test_generation(
        self,
        user_story: "UserStory",
        analysis: "AnalysisResult",
        generated_code: "GeneratedCode",
        story_scope: "StoryScope",
    ) -> "TestResult":
        """
        New step 9 flow:
          1. DeveloperAgent generates src/test/java from test_contract (knows real constructors)
          2. TesterAgent validates and filters (no free generation)

        Falls back to legacy tester.test() if no test_contract is available.
        """
        test_contract = getattr(analysis, "test_contract", None) or []

        if not test_contract:
            logger.warning(
                "  ⚠️  No test contract in analysis — falling back to legacy test generation"
            )
            return await self.tester.test(
                generated_code,
                analysis,
                story_scope=story_scope,
                mode="initial_full",
            )

        # Step A: Developer generates test files from contract
        raw_test_files = await self.developer.generate_test_files_from_contract(
            user_story=user_story,
            analysis=analysis,
            test_contract_dicts=test_contract,
            generated_code=generated_code,
        )
        logger.info(
            "  Developer generated %d production file(s) and %d test file(s)",
            sum(1 for p in generated_code.files if "src/main" in p.replace("\\", "/")),
            len(raw_test_files),
        )
        logger.info("  Developer generated tests from test contract")

        # Step B: TesterAgent validates (filters, sanitizes — never generates freely)
        validated_test_files = await self.tester.validate_and_repair_tests(
            test_files=raw_test_files,
            test_contract_dicts=test_contract,
            generated_code=generated_code,
            analysis=analysis,
        )

        estimated_coverage = 0.0
        return TestResult(
            coverage=estimated_coverage,
            passed=False,       # overwritten by real mvn test results
            test_files=validated_test_files,
            test_summary=(
                f"Contract-driven tests: {len(validated_test_files)} file(s) "
                f"from {len(test_contract)} test case(s)"
            ),
            generation_mode="contract_driven",
            metadata={
                "test_contract_cases": len(test_contract),
                "story_scope": story_scope.to_dict(),
            },
        )

    # ── Phase-based change filtering ─────────────────────────────────────────
    #
    # After a successful compilation, production sources (src/main/java) must
    # not be touched by test-repair or coverage-fix agents.  This helper is
    # the single enforcement point: apply it to any dict of path→content that
    # comes from an LLM agent before merging it back into generated_code.
    #
    # Phases and their allowed prefixes:
    #   implementation   → src/main/java, src/main/resources, pom.xml
    #   compile_fix      → src/main/java, src/main/resources, pom.xml
    #   test_generation  → src/test/java
    #   test_fix         → src/test/java
    #   coverage_fix     → src/test/java

    _PHASE_ALLOWED_PREFIXES: Dict[str, tuple] = {
        "implementation":  ("src/main/java/", "src/main/resources/", "pom.xml"),
        "compile_fix":     ("src/main/java/", "src/main/resources/", "pom.xml"),
        "test_generation": ("src/test/java/",),
        "test_fix":        ("src/test/java/",),
        "coverage_fix":    ("src/test/java/",),
    }

    def _filter_changes_for_phase(
        self,
        changes: Dict[str, str],
        phase: str,
    ) -> Dict[str, str]:
        """Return only the changes whose paths are allowed for *phase*.

        Silently drops any path outside the allowed set and logs a warning
        so the issue is visible in the run log without crashing the pipeline.
        """
        allowed = self._PHASE_ALLOWED_PREFIXES.get(phase)
        if not allowed:
            return changes

        filtered: Dict[str, str] = {}
        for path, content in changes.items():
            normalized = path.replace("\\", "/")
            if any(normalized.startswith(p) or normalized == p for p in allowed):
                filtered[path] = content
            else:
                logger.warning(
                    "Ignored forbidden change during %s: %s", phase, path
                )
        return filtered

    def _detect_changed_file_paths(
        self,
        previous_code: Optional[GeneratedCode],
        current_code: GeneratedCode,
    ) -> list[str]:
        if previous_code is None:
            return []
        changed: list[str] = []
        previous_files = previous_code.files if previous_code else {}
        for path, content in current_code.files.items():
            normalized = path.replace("\\", "/")
            if previous_files.get(path) != content:
                changed.append(normalized)
        return self._normalize_story_scope_paths(changed)

    def _infer_story_file_role(self, path: str, content: str = "") -> str:
        normalized = path.replace("\\", "/")
        lower = normalized.lower()
        if "/controller/" in lower or normalized.endswith("Controller.java"):
            return "controller"
        if "/service/" in lower or normalized.endswith("Service.java") or normalized.endswith("ServiceImpl.java"):
            return "service"
        if "/repository/" in lower or normalized.endswith("Repository.java"):
            return "repository"
        if "/dto/" in lower or normalized.endswith("Request.java") or normalized.endswith("Response.java"):
            return "dto"
        if "/entity/" in lower or "@Entity" in content:
            return "entity"
        if "/mapper/" in lower or normalized.endswith("Mapper.java"):
            return "mapper"
        if "/validator/" in lower or normalized.endswith("Validator.java"):
            return "validator"
        if "/exception/" in lower or "ExceptionHandler" in normalized:
            return "support"
        if "/config/" in lower or normalized.endswith("Config.java"):
            return "config"
        if normalized.endswith("Application.java"):
            return "bootstrap"
        return "other"

    def _has_meaningful_direct_test_value(self, path: str, content: str) -> bool:
        normalized = path.replace("\\", "/")
        role = self._infer_story_file_role(normalized, content)
        if role in {"controller", "service", "repository", "validator", "mapper"}:
            return True
        if role == "dto":
            validation_markers = ("@NotNull", "@NotBlank", "@Size", "@Pattern", "@Email", "@Min", "@Max")
            return any(marker in content for marker in validation_markers)
        if role == "entity":
            entity_markers = ("@PrePersist", "@PreUpdate", "equals(", "hashCode(", "toBuilder(", "@Version")
            return any(marker in content for marker in entity_markers)
        return False

    def _build_story_scope(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        repo_analysis: Any,
        plan: PlanResult,
        generated_code: GeneratedCode,
        fixer_touched_files: Optional[list[str]] = None,
    ) -> StoryScope:
        del repo_analysis
        planned_create: list[str] = []
        planned_edit: list[str] = []
        for task in getattr(plan, "subtasks", []) or []:
            planned_create.extend(getattr(task, "files_to_create", []) or [])
            planned_edit.extend(getattr(task, "files_to_edit", []) or [])

        existing_main_files = {
            path.replace("\\", "/"): content
            for path, content in generated_code.files.items()
            if path.replace("\\", "/").startswith("src/main/")
        }
        candidate_business = self._normalize_story_scope_paths(
            planned_create + planned_edit + list(fixer_touched_files or [])
        )
        candidate_business = [
            path for path in candidate_business
            if path in existing_main_files
        ]
        if not candidate_business:
            candidate_business = list(existing_main_files.keys())

        file_roles = {
            path: self._infer_story_file_role(path, existing_main_files.get(path, ""))
            for path in existing_main_files
        }
        entrypoints = [
            path for path in candidate_business
            if file_roles.get(path) == "controller"
        ]
        dependencies = [
            path for path in candidate_business
            if file_roles.get(path) in {"repository", "entity", "dto", "mapper", "validator", "support"}
        ]
        business_files = [
            path for path in candidate_business
            if file_roles.get(path) not in {"bootstrap", "config"}
        ]
        if not business_files:
            business_files = candidate_business[:]

        test_targets = [
            path for path in business_files
            if self._has_meaningful_direct_test_value(path, existing_main_files.get(path, ""))
        ]
        if not test_targets:
            test_targets = [
                path for path in business_files
                if file_roles.get(path) in {"controller", "service", "repository", "mapper", "validator"}
            ] or business_files[:]

        excluded_files = [
            path for path in existing_main_files
            if path not in business_files and path not in dependencies and path not in entrypoints
        ]

        return StoryScope(
            story_id=user_story.id,
            business_files=self._normalize_story_scope_paths(business_files),
            test_targets=self._normalize_story_scope_paths(test_targets),
            entrypoints=self._normalize_story_scope_paths(entrypoints),
            dependencies=self._normalize_story_scope_paths(dependencies),
            excluded_files=self._normalize_story_scope_paths(excluded_files),
            new_files=self._normalize_story_scope_paths(planned_create),
            modified_files=self._normalize_story_scope_paths(planned_edit),
            fixer_touched_files=self._normalize_story_scope_paths(list(fixer_touched_files or [])),
            file_roles={path: role for path, role in file_roles.items() if path in existing_main_files},
        )

    def _story_scope_class_index(self, story_scope: StoryScope) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for path in story_scope.business_files + story_scope.dependencies + story_scope.entrypoints + story_scope.test_targets:
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java"):
                continue
            index[Path(normalized).stem] = normalized
        return index

    def compute_story_scoped_coverage(
        self,
        run_result: Any,
        story_scope: StoryScope,
    ) -> StoryCoverageReport:
        class_index = self._story_scope_class_index(story_scope)
        scoped_classes: list[Dict[str, Any]] = []
        uncovered_classes: list[Dict[str, Any]] = []
        uncovered_methods: list[Dict[str, Any]] = []
        covered_files: set[str] = set()
        covered_lines = 0
        missed_lines = 0
        covered_branches = 0
        missed_branches = 0

        for item in getattr(run_result, "class_coverage", []) or []:
            class_name = str(item.get("class_name", "") or "").strip()
            target_path = class_index.get(class_name)
            if not target_path:
                continue
            enriched = dict(item)
            enriched["path"] = target_path
            scoped_classes.append(enriched)
            covered = int(item.get("covered_lines", 0) or 0)
            missed = int(item.get("missed_lines", 0) or 0)
            branch_cov = int(item.get("covered_branches", 0) or 0)
            branch_missed = int(item.get("missed_branches", 0) or 0)
            if covered == 0 and missed == 0 and item.get("line_coverage") is not None:
                inferred_line = max(0.0, min(100.0, float(item.get("line_coverage", 0.0) or 0.0)))
                covered = int(round(inferred_line))
                missed = int(round(100.0 - inferred_line))
            if branch_cov == 0 and branch_missed == 0 and item.get("branch_coverage") is not None:
                inferred_branch = max(0.0, min(100.0, float(item.get("branch_coverage", 0.0) or 0.0)))
                branch_cov = int(round(inferred_branch))
                branch_missed = int(round(100.0 - inferred_branch))
            covered_lines += covered
            missed_lines += missed
            covered_branches += branch_cov
            missed_branches += branch_missed
            if covered > 0:
                covered_files.add(target_path)
            line_cov_value = item.get("line_coverage")
            branch_cov_value = item.get("branch_coverage")
            has_uncovered_work = (
                missed > 0
                or branch_missed > 0
                or (line_cov_value is not None and float(line_cov_value) < 100.0)
                or (branch_cov_value is not None and float(branch_cov_value) < 100.0)
            )
            if has_uncovered_work:
                uncovered_classes.append(enriched)

        scoped_class_names = {str(item.get("class_name", "") or "").strip() for item in scoped_classes}
        for item in getattr(run_result, "method_coverage", []) or []:
            class_name = str(item.get("class_name", "") or "").strip()
            if class_name not in scoped_class_names:
                continue
            if (
                int(item.get("missed_lines", 0) or 0) <= 0
                and int(item.get("missed_branches", 0) or 0) <= 0
                and not (
                    item.get("line_coverage") is not None and float(item.get("line_coverage")) < 100.0
                )
                and not (
                    item.get("branch_coverage") is not None and float(item.get("branch_coverage")) < 100.0
                )
            ):
                continue
            enriched = dict(item)
            enriched["path"] = class_index.get(class_name)
            uncovered_methods.append(enriched)

        if not scoped_classes:
            fallback_line = getattr(run_result, "line_coverage", None)
            fallback_branch = getattr(run_result, "branch_coverage", None)
            return StoryCoverageReport(
                story_id=story_scope.story_id,
                line_coverage=fallback_line,
                branch_coverage=fallback_branch,
                scoped_classes=[],
                covered_files=[],
                uncovered_classes=[],
                uncovered_methods=[],
                considered_files=self._normalize_story_scope_paths(story_scope.business_files),
            )

        total_lines = covered_lines + missed_lines
        total_branches = covered_branches + missed_branches
        return StoryCoverageReport(
            story_id=story_scope.story_id,
            line_coverage=round((covered_lines / total_lines) * 100, 1) if total_lines else None,
            branch_coverage=round((covered_branches / total_branches) * 100, 1) if total_branches else None,
            covered_lines=covered_lines,
            missed_lines=missed_lines,
            covered_branches=covered_branches,
            missed_branches=missed_branches,
            covered_files=sorted(covered_files),
            uncovered_classes=sorted(
                uncovered_classes,
                key=lambda item: (
                    -(int(item.get("missed_branches", 0) or 0)),
                    -(int(item.get("missed_lines", 0) or 0)),
                    str(item.get("class_name", "") or ""),
                ),
            ),
            uncovered_methods=sorted(
                uncovered_methods,
                key=lambda item: (
                    -(int(item.get("missed_branches", 0) or 0)),
                    -(int(item.get("missed_lines", 0) or 0)),
                    str(item.get("class_name", "") or ""),
                    str(item.get("method_name", "") or ""),
                ),
            ),
            scoped_classes=sorted(scoped_classes, key=lambda item: str(item.get("class_name", "") or "")),
            considered_files=sorted(class_index.values()),
        )

    def extract_uncovered_story_targets(
        self,
        story_scope: StoryScope,
        story_coverage: StoryCoverageReport,
        limit: int = 4,
    ) -> list[str]:
        class_to_path = self._story_scope_class_index(story_scope)
        if not class_to_path:
            return []
        scored: list[tuple[int, str]] = []
        seen: set[str] = set()
        for item in story_coverage.uncovered_classes:
            class_name = str(item.get("class_name", "") or "").strip()
            if not class_name or class_name in seen:
                continue
            seen.add(class_name)
            path = class_to_path.get(class_name, str(item.get("path", "") or ""))
            role = story_scope.file_roles.get(path, "other")
            score = 0
            score += 200 if path in story_scope.new_files else 0
            score += 150 if path in story_scope.modified_files else 0
            score += 120 if path in story_scope.entrypoints else 0
            score += 110 if path in story_scope.fixer_touched_files else 0
            score += {
                "service": 100,
                "controller": 90,
                "repository": 60,
                "validator": 70,
                "mapper": 65,
                "entity": 20,
                "dto": 10,
            }.get(role, 10)
            score += int(item.get("missed_branches", 0) or 0) * 10
            score += int(item.get("missed_lines", 0) or 0)
            scored.append((score, class_name))

        reported_classes = {
            str(item.get("class_name", "") or "").strip()
            for item in story_coverage.scoped_classes
        }
        for class_name, path in class_to_path.items():
            if class_name in reported_classes or class_name in seen:
                continue
            role = story_scope.file_roles.get(path, "other")
            score = 250
            score += 200 if path in story_scope.new_files else 0
            score += 150 if path in story_scope.modified_files else 0
            score += {
                "service": 100,
                "controller": 90,
                "repository": 60,
                "validator": 70,
                "mapper": 65,
                "entity": 20,
                "dto": 10,
            }.get(role, 10)
            scored.append((score, class_name))

        scored.sort(key=lambda item: (-item[0], item[1]))
        prioritized_names = [class_name for _, class_name in scored]
        role_by_class = {
            class_name: story_scope.file_roles.get(class_to_path.get(class_name, ""), "other")
            for class_name in prioritized_names
        }

        service_controller = [
            class_name for class_name in prioritized_names
            if role_by_class.get(class_name) in {"service", "controller"}
        ]
        if service_controller:
            return service_controller[:limit]

        repository_like = [
            class_name for class_name in prioritized_names
            if role_by_class.get(class_name) in {"repository", "validator", "mapper"}
        ]
        if repository_like:
            return repository_like[:limit]

        meaningful_model = [
            class_name for class_name in prioritized_names
            if role_by_class.get(class_name) in {"entity", "dto"}
        ]
        if meaningful_model:
            return meaningful_model[:limit]

        return prioritized_names[:limit]

    def has_material_test_change(
        self,
        previous_tests: Dict[str, str],
        new_tests: Dict[str, str],
        target_classes: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        reasons: list[str] = []
        previous_paths = {path.replace("\\", "/") for path in previous_tests}
        new_paths = {path.replace("\\", "/") for path in new_tests}
        added_files = sorted(new_paths - previous_paths)
        if added_files:
            reasons.append("new_test_file")

        changed_paths = [
            path for path in new_paths & previous_paths
            if (previous_tests.get(path) or previous_tests.get(path.replace("/", "\\"), "")) !=
               (new_tests.get(path) or new_tests.get(path.replace("/", "\\"), ""))
        ]
        if changed_paths:
            reasons.append("content_changed")

        def _count_occurrences(files: Dict[str, str], token: str) -> int:
            return sum(content.count(token) for content in files.values())

        if _count_occurrences(new_tests, "@Test") > _count_occurrences(previous_tests, "@Test"):
            reasons.append("test_count_increased")
        if _count_occurrences(new_tests, "assert") > _count_occurrences(previous_tests, "assert"):
            reasons.append("assertions_increased")

        targets = [name.lower() for name in (target_classes or []) if name]
        if targets:
            previous_blob = "\n".join(previous_tests.values()).lower()
            new_blob = "\n".join(new_tests.values()).lower()
            if any(target in new_blob and target not in previous_blob for target in targets):
                reasons.append("references_new_targets")

        return {
            "changed": bool(reasons),
            "reasons": reasons,
            "added_files": added_files,
            "changed_paths": sorted(changed_paths),
        }

    def _select_low_coverage_targets(
        self,
        generated_code: GeneratedCode,
        run_result: Any,
        story_scope: Optional[StoryScope] = None,
        limit: int = 4,
    ) -> list[str]:
        if story_scope is not None:
            story_coverage = self.compute_story_scoped_coverage(run_result, story_scope)
            story_targets = self.extract_uncovered_story_targets(story_scope, story_coverage, limit=limit)
            if story_targets:
                return story_targets
        source_classes = self._collect_generated_source_classes(generated_code)
        if not source_classes:
            return []

        ranked: list[tuple[int, float, str]] = []
        seen: set[str] = set()
        for item in getattr(run_result, "class_coverage", []) or []:
            class_name = str(item.get("class_name", "") or "").strip()
            if not class_name or class_name not in source_classes or class_name in seen:
                continue
            seen.add(class_name)
            line_coverage = item.get("line_coverage")
            normalized_coverage = float(line_coverage) if line_coverage is not None else -1.0
            ranked.append((self._coverage_target_priority(class_name), normalized_coverage, class_name))

        missing_classes = [name for name in source_classes if name not in seen]
        ranked.extend((self._coverage_target_priority(name), -1.0, name) for name in missing_classes)
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))

        targets: list[str] = []
        for _, line_coverage, class_name in ranked:
            if line_coverage > 0.0:
                continue
            targets.append(class_name)
            if len(targets) >= limit:
                return targets

        if targets:
            return targets

        for _, _, class_name in ranked:
            if class_name in targets:
                continue
            targets.append(class_name)
            if len(targets) >= limit:
                break

        return targets

    def _collect_generated_source_classes(self, generated_code: GeneratedCode) -> set[str]:
        classes: set[str] = set()
        type_pattern = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Z][A-Za-z0-9_]*)\b")
        for path, content in generated_code.all_source_files().items():
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java"):
                continue
            for class_name in type_pattern.findall(content):
                if class_name == "Application":
                    continue
                classes.add(class_name)
        return classes

    def _coverage_target_priority(self, class_name: str) -> int:
        priorities = (
            ("ServiceImpl", 0),
            ("Service", 1),
            ("Controller", 2),
            ("Repository", 3),
            ("ExceptionHandler", 4),
            ("Exception", 5),
            ("Config", 6),
        )
        for suffix, priority in priorities:
            if class_name.endswith(suffix):
                return priority
        return 10

    def _require_state_artifact(self, state: PipelineState, key: str) -> Any:
        if key not in state.artifacts:
            raise FileNotFoundError(f"Required checkpoint artifact is missing: {key}")
        return state.artifacts[key]

    def _build_execution_summary(
        self,
        state: PipelineState,
        final_status: str,
    ) -> Dict[str, Any]:
        return {
            "user_story_id": state.user_story_id,
            "final_status": final_status,
            "decision_route": state.artifacts.get("decision_route"),
            "recommended_next_action": state.artifacts.get("recommended_next_action"),
            "primary_failure_type": state.artifacts.get("primary_failure_type"),
            "failure_types": state.artifacts.get("failure_types", []),
            "retry_attempts": {
                "test_fix_retry_attempted": bool(state.artifacts.get("test_fix_retry_attempted", False)),
                "zero_tests_retry_attempted": bool(state.artifacts.get("zero_tests_retry_attempted", False)),
                "coverage_retry_attempted": bool(state.artifacts.get("coverage_retry_attempted", False)),
                "coverage_retry_attempts": int(state.artifacts.get("coverage_retry_attempts", 0) or 0),
            },
            "validation": {
                "compile_success": state.artifacts.get("compile_success"),
                "tests_passed": state.artifacts.get("tests_passed"),
                "coverage_source": state.artifacts.get("coverage_source"),
                "coverage_gate_mode": state.artifacts.get("coverage_gate_mode"),
                "coverage_ok": state.artifacts.get("coverage_ok"),
                "coverage_below_threshold": state.artifacts.get("coverage_below_threshold"),
                "story_coverage_line": state.artifacts.get("story_coverage_line"),
                "story_coverage_branch": state.artifacts.get("story_coverage_branch"),
                "global_coverage_line": state.artifacts.get("global_coverage_line"),
                "global_coverage_branch": state.artifacts.get("global_coverage_branch"),
                "zero_tests_discovered": state.artifacts.get("zero_tests_discovered"),
                "total_tests_run": state.artifacts.get("total_tests_run"),
                "review_approved": state.artifacts.get("review_approved"),
                "quality_scan_passed": state.artifacts.get("quality_scan_passed"),
                "pipeline_blocked": state.artifacts.get("pipeline_blocked"),
                "coverage_target_classes": state.artifacts.get("coverage_target_classes", []),
                "coverage_retry_diagnostics": state.artifacts.get("coverage_retry_diagnostics", []),
            },
            "steps": {
                name: {
                    "status": step.status,
                    "error": step.error,
                    "artifact_key": step.artifact_key,
                }
                for name, step in state.steps.items()
            },
        }

    def _generated_code_to_dict(self, generated_code: GeneratedCode) -> Dict[str, Any]:
        return {
            "files": generated_code.files,
            "pom_xml": generated_code.pom_xml,
            "readme": generated_code.readme,
        }

    def _save_generated_code_artifact(self, story_id: str, generated_code: GeneratedCode) -> None:
        self._save_artifact(
            f"generated_code_{story_id}.json",
            self._generated_code_to_dict(generated_code),
        )

    def _restore_generated_code(self, state: PipelineState, story_id: str) -> GeneratedCode:
        data = state.artifacts.get("generated_code")
        if not data:
            artifact = self.settings.pipeline.artifacts_dir / f"generated_code_{story_id}.json"
            if artifact.exists():
                data = json.loads(artifact.read_text(encoding="utf-8"))
            else:
                raise FileNotFoundError(
                    f"Resume requires generated code artifact for {story_id}, but none was found"
                )
        return GeneratedCode(
            files=data.get("files", {}),
            pom_xml=data.get("pom_xml", ""),
            readme=data.get("readme", ""),
        )

    def _save_test_generation_artifact(self, story_id: str, test_result: TestResult) -> None:
        payload = test_result.to_dict()
        payload["test_files"] = test_result.test_files
        self._save_artifact(f"generated_tests_{story_id}.json", payload)

    def _restore_generated_tests(self, state: PipelineState, story_id: str) -> TestResult:
        data = state.artifacts.get("test_result")
        if not data or state.steps["run_tests"].status == "completed":
            artifact = self.settings.pipeline.artifacts_dir / f"generated_tests_{story_id}.json"
            if not artifact.exists():
                raise FileNotFoundError(
                    f"Resume requires generated tests artifact for {story_id}, but none was found"
                )
            data = json.loads(artifact.read_text(encoding="utf-8"))
        return TestResult.from_dict(data, test_files=data.get("test_files", {}))

    def _restore_test_result(self, state: PipelineState, story_id: str) -> TestResult:
        data = state.artifacts.get("test_result")
        if not data:
            report = self.settings.pipeline.artifacts_dir / f"test_report_{story_id}.json"
            generated = self.settings.pipeline.artifacts_dir / f"generated_tests_{story_id}.json"
            if not report.exists() or not generated.exists():
                raise FileNotFoundError(
                    f"Resume requires test report artifacts for {story_id}, but they are missing"
                )
            data = json.loads(report.read_text(encoding="utf-8"))
            generated_data = json.loads(generated.read_text(encoding="utf-8"))
            data["test_files"] = generated_data.get("test_files", {})
        return TestResult.from_dict(data, test_files=data.get("test_files", {}))

    def _restore_compile_result(self, state: PipelineState) -> CompileResult:
        data = state.artifacts.get("compile_report")
        if not data:
            report = self.settings.pipeline.artifacts_dir / "compile_report.json"
            if not report.exists():
                raise FileNotFoundError("Resume requires compile_report.json, but it is missing")
            data = json.loads(report.read_text(encoding="utf-8"))
        errors = [CompileError(**err) for err in data.get("errors", [])]
        return CompileResult(
            success=bool(data.get("success", False)),
            errors=errors,
            warnings=data.get("warnings", []),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
        )

    def _debug_maybe_crash_after(self, step: str) -> None:
        target = os.getenv("PIPELINE_DEBUG_CRASH_AFTER", "").strip().lower()
        if target and target == step.lower():
            raise RuntimeError(f"Debug crash injected after step: {step}")

    #  User story resolution
    # ──────────────────────────────────────────────────────────────

    async def _resolve_user_story(self, user_story_input: str) -> UserStory:
        value = user_story_input.strip()
        if _is_jira_id(value):
            logger.info(f"  → Récupération Jira: {value}")
            return await self.jira.get_user_story(value)
        logger.info("  → User Story en texte brut")
        return _make_user_story_from_text(value)

    # ──────────────────────────────────────────────────────────────
    #  Intent summary
    # ──────────────────────────────────────────────────────────────

    def _build_intent_summary(self, user_story: UserStory, analysis: AnalysisResult) -> str:
        entities = ", ".join(e.name for e in analysis.entities[:5])
        endpoints = ", ".join(f"{ep.method} {ep.path}" for ep in analysis.endpoints[:5])
        rules = " | ".join(analysis.business_rules[:3])
        acceptance = "\n".join(f"- {c}" for c in user_story.acceptance_criteria[:10]) or "- none provided"
        return (
            f"[{user_story.id}] {user_story.title}\n"
            f"Description: {user_story.description[:500]}\n"
            f"Acceptance criteria:\n{acceptance}\n"
            f"Package: {analysis.package_base} | Service: {analysis.service_name}\n"
            f"Entities: {entities or 'none'}\n"
            f"Endpoints: {endpoints or 'none'}\n"
            f"Business rules: {rules or 'none'}\n"
            f"Architecture: {analysis.architecture_notes[:300]}\n"
            "Implementation rule: implement the minimum code needed to satisfy the acceptance criteria exactly; "
            "do not add generic CRUD operations unless they are explicitly required."
        )

    def _analysis_cache_fingerprint(self, user_story: UserStory, docs: Dict[str, str]) -> str:
        payload = {
            "schema_version": ANALYSIS_CACHE_SCHEMA_VERSION,
            "user_story": {
                "id": user_story.id,
                "title": user_story.title,
                "description": user_story.description,
                "acceptance_criteria": user_story.acceptance_criteria,
            },
            "docs": {path: docs[path] for path in sorted(docs)},
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_analysis_cache(
        self,
        cache_path: Path,
        user_story: UserStory,
        docs: Dict[str, str],
    ) -> Optional[AnalysisResult]:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if "analysis" not in payload or "_meta" not in payload:
            return None

        meta = payload.get("_meta", {})
        expected = self._analysis_cache_fingerprint(user_story, docs)
        if meta.get("schema_version") != ANALYSIS_CACHE_SCHEMA_VERSION:
            return None
        if meta.get("fingerprint") != expected:
            return None
        return AnalysisResult.from_dict(payload["analysis"])

    def _save_analysis_cache(
        self,
        cache_path: Path,
        user_story: UserStory,
        docs: Dict[str, str],
        analysis: AnalysisResult,
    ) -> None:
        payload = {
            "_meta": {
                "schema_version": ANALYSIS_CACHE_SCHEMA_VERSION,
                "fingerprint": self._analysis_cache_fingerprint(user_story, docs),
            },
            "analysis": analysis.to_dict(),
        }
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _sanitize_plan(
        self,
        plan,
        user_story: UserStory,
        analysis: AnalysisResult,
    ):
        """
        Remove any file from the plan whose domain tokens are NOT in the allowed set.

        Returns (sanitized_plan, rejected_files) where rejected_files is the list
        of paths that were stripped out.  The sanitized plan is always returned —
        even if all files of a subtask were removed (the subtask is then dropped).
        """
        from core.models import PlanResult, SubTask

        allowed_tokens = self._allowed_domain_tokens(user_story, analysis)
        generic_tokens = self._generic_resource_tokens()
        rejected: list[str] = []

        sanitized_subtasks = []
        for task in plan.subtasks:
            clean_create: list[str] = []
            clean_edit: list[str] = []

            for path in task.files_to_create:
                path_tokens = self._extract_resource_tokens_from_path(path)
                if not path_tokens or path_tokens & allowed_tokens or path_tokens <= generic_tokens:
                    clean_create.append(path)
                else:
                    logger.warning(f"    [sanitize] REMOVE (create) {path} — tokens {path_tokens} not in allowed")
                    rejected.append(path)

            for path in task.files_to_edit:
                path_tokens = self._extract_resource_tokens_from_path(path)
                if not path_tokens or path_tokens & allowed_tokens or path_tokens <= generic_tokens:
                    clean_edit.append(path)
                else:
                    logger.warning(f"    [sanitize] REMOVE (edit)   {path} — tokens {path_tokens} not in allowed")
                    rejected.append(path)

            # Drop the subtask entirely if it has no files left after sanitization
            if clean_create or clean_edit:
                sanitized_subtasks.append(SubTask(
                    id=task.id,
                    title=task.title,
                    description=task.description,
                    files_to_create=clean_create,
                    files_to_edit=clean_edit,
                    depends_on=task.depends_on,
                    agent=task.agent,
                    priority=task.priority,
                ))
            else:
                logger.warning(f"    [sanitize] DROP subtask {task.id} '{task.title}' — no files left after sanitization")

        # Rebuild execution_groups keeping only subtask ids that survived
        surviving_ids = {t.id for t in sanitized_subtasks}
        clean_groups = [
            [tid for tid in group if tid in surviving_ids]
            for group in plan.execution_groups
        ]
        clean_groups = [g for g in clean_groups if g]

        sanitized = PlanResult(
            subtasks=sanitized_subtasks,
            execution_groups=clean_groups or [[t.id] for t in sanitized_subtasks],
            risks=plan.risks,
            summary=plan.summary,
        )

        if rejected:
            logger.info(f"  [sanitize] allowed_tokens     : {sorted(allowed_tokens)}")
            logger.info(f"  [sanitize] rejected_resources : {rejected}")
        else:
            logger.info("  [sanitize] Plan is clean — no out-of-scope resources found")

        return sanitized, rejected

    def _validate_plan_alignment(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        plan,
    ) -> Dict[str, Any]:
        issues: list[str] = []
        allowed_tokens = self._allowed_domain_tokens(user_story, analysis)
        found_tokens = {
            token
            for task in plan.subtasks
            for path in (task.files_to_create + task.files_to_edit)
            for token in self._extract_resource_tokens_from_path(path)
        }
        unexpected = sorted(token for token in found_tokens if token not in allowed_tokens and token not in self._generic_resource_tokens())
        if unexpected:
            issues.append(f"unexpected planned resources: {', '.join(unexpected)}")

        if self._story_is_read_only_status_flow(analysis):
            crud_words = []
            for task in plan.subtasks:
                text = f"{task.title} {task.description}".lower()
                if any(word in text for word in ("create", "post", "update", "put", "delete", "patch", "list all", "find all")):
                    crud_words.append(task.id)
            if crud_words:
                issues.append(f"plan introduces CRUD-oriented tasks for a status consultation story: {', '.join(crud_words)}")

        return {"passed": not issues, "issues": issues}

    def _validate_generated_code_alignment(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        generated_code: GeneratedCode,
        relevant_paths: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        issues: list[str] = []
        allowed_tokens = self._allowed_domain_tokens(user_story, analysis)
        main_files = {
            path.replace("\\", "/"): content
            for path, content in generated_code.files.items()
            if path.replace("\\", "/").startswith("src/main/java/")
        }
        if relevant_paths:
            main_files = {
                path: content
                for path, content in main_files.items()
                if path in relevant_paths
            }
            planned_main_paths = sorted(
                path.replace("\\", "/")
                for path in relevant_paths
                if path.replace("\\", "/").startswith("src/main/java/")
            )
            missing_planned = [
                path for path in planned_main_paths
                if (
                    path not in main_files
                    and not Path(path).name.startswith("package-info.")
                    and not any(
                        self._paths_match_by_canonical_story_resource(path, actual_path, analysis)
                        for actual_path in generated_code.files
                    )
                )
            ]
            if missing_planned:
                issues.append(
                    "missing planned main files: " + ", ".join(missing_planned[:5])
                )
        found_tokens = {
            token
            for path in main_files
            for token in self._extract_resource_tokens_from_path(path)
        }
        unexpected = sorted(token for token in found_tokens if token not in allowed_tokens and token not in self._generic_resource_tokens())
        if unexpected:
            issues.append(f"generated unexpected resources: {', '.join(unexpected)}")

        if self._story_is_read_only_status_flow(analysis):
            forbidden_patterns = (
                "@PostMapping",
                "@PutMapping",
                "@DeleteMapping",
                "@PatchMapping",
                " findAll(",
                " create(",
                " update(",
                " delete(",
            )
            offending_files = sorted(
                path for path, content in main_files.items()
                if any(pattern in content for pattern in forbidden_patterns)
            )
            if offending_files:
                issues.append(
                    "generated CRUD behavior for a status consultation story: "
                    + ", ".join(offending_files[:5])
                )

        should_validate_endpoints = True
        if relevant_paths:
            normalized_relevant = {
                path.replace("\\", "/")
                for path in relevant_paths
                if path.replace("\\", "/").startswith("src/main/java/")
            }
            should_validate_endpoints = any(
                "/controller/" in path or path.endswith("Controller.java")
                for path in normalized_relevant
            )

        if should_validate_endpoints:
            actual_endpoints = self._extract_declared_endpoints_from_main_files(main_files)
            missing_endpoints = []
            for endpoint in analysis.endpoints:
                expected_method = (endpoint.method or "").upper()
                expected_path = self._normalize_endpoint_path(endpoint.path or "")
                if not expected_method or not expected_path:
                    continue
                if (expected_method, expected_path) not in actual_endpoints:
                    missing_endpoints.append(f"{expected_method} {endpoint.path}")
            if missing_endpoints:
                issues.append(
                    "missing expected endpoints: " + ", ".join(missing_endpoints[:5])
                )

        return {"passed": not issues, "issues": issues}

    def _extract_declared_endpoints_from_main_files(
        self,
        main_files: Dict[str, str],
    ) -> set[tuple[str, str]]:
        endpoints: set[tuple[str, str]] = set()
        mapping_methods = ("GET", "POST", "PUT", "DELETE", "PATCH")

        for _, content in main_files.items():
            class_prefix, class_mapping_span = self._extract_class_request_mapping(content)

            pattern = re.compile(
                r"@(?:(Get|Post|Put|Delete|Patch)Mapping(?:\s*\((.*?)\))?|RequestMapping\s*\((.*?)\))",
                re.DOTALL,
            )
            for match in pattern.finditer(content):
                if class_mapping_span and match.span() == class_mapping_span:
                    continue
                annotation_method = match.group(1)
                annotation_args = match.group(2) if annotation_method else match.group(3)

                methods: set[str] = set()
                if annotation_method:
                    methods.add(annotation_method.upper())
                else:
                    method_match = re.search(
                        r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH)",
                        annotation_args,
                    )
                    if method_match:
                        methods.add(method_match.group(1).upper())
                    elif "method" not in annotation_args:
                        methods.update(mapping_methods)

                path = self._extract_mapping_value(annotation_args)
                full_path = self._join_mapping_paths(class_prefix, path)
                normalized = self._normalize_endpoint_path(full_path)
                if not normalized:
                    continue

                for method in methods:
                    endpoints.add((method, normalized))

        return endpoints

    def _extract_request_mapping_path(self, content: str) -> str:
        path, _ = self._extract_class_request_mapping(content)
        return path

    def _extract_class_request_mapping(self, content: str) -> tuple[str, Optional[tuple[int, int]]]:
        class_match = re.search(
            r"@RequestMapping\s*\((.*?)\)\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?class\s+[A-Z][A-Za-z0-9_]*",
            content,
            re.DOTALL,
        )
        if not class_match:
            return "", None
        annotation_match = re.search(r"@RequestMapping\s*\((.*?)\)", class_match.group(0), re.DOTALL)
        annotation_span = None
        if annotation_match:
            annotation_span = (
                class_match.start() + annotation_match.start(),
                class_match.start() + annotation_match.end(),
            )
        return self._extract_mapping_value(class_match.group(1)), annotation_span

    def _extract_mapping_value(self, annotation_args: str) -> str:
        if not annotation_args:
            return ""
        match = re.search(r'(?:"([^"]+)")', annotation_args)
        if match:
            return match.group(1)
        named = re.search(r'(?:value|path)\s*=\s*"([^"]+)"', annotation_args)
        if named:
            return named.group(1)
        return ""

    def _join_mapping_paths(self, prefix: str, suffix: str) -> str:
        left = (prefix or "").strip()
        right = (suffix or "").strip()
        if not left and not right:
            return ""
        if not left:
            return right
        if not right:
            return left
        return f"{left.rstrip('/')}/{right.lstrip('/')}"

    def _normalize_endpoint_path(self, path: str) -> str:
        cleaned = (path or "").strip()
        if not cleaned:
            return ""
        if not cleaned.startswith("/"):
            cleaned = "/" + cleaned
        cleaned = re.sub(r"/{2,}", "/", cleaned)
        cleaned = re.sub(r"\{[^}]+\}", "{}", cleaned)
        if len(cleaned) > 1:
            cleaned = cleaned.rstrip("/")
        return cleaned

    def _story_is_read_only_status_flow(self, analysis: AnalysisResult) -> bool:
        methods = {ep.method.upper() for ep in analysis.endpoints}
        endpoint_text = " ".join(f"{ep.method} {ep.path} {ep.description}".lower() for ep in analysis.endpoints)
        return methods == {"GET"} and "status" in endpoint_text

    def _normalize_plan_paths_against_analysis(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        plan: PlanResult,
    ) -> PlanResult:
        normalized_subtasks = []
        changed_paths = 0

        for task in plan.subtasks:
            create_paths, create_count = self._normalize_plan_path_list_against_analysis(
                task.files_to_create,
                user_story,
                analysis,
            )
            edit_paths, edit_count = self._normalize_plan_path_list_against_analysis(
                task.files_to_edit,
                user_story,
                analysis,
            )
            changed_paths += create_count + edit_count
            normalized_subtasks.append(
                SubTask(
                    id=task.id,
                    title=task.title,
                    description=task.description,
                    files_to_edit=edit_paths,
                    files_to_create=create_paths,
                    depends_on=task.depends_on,
                    agent=task.agent,
                    priority=task.priority,
                )
            )

        if changed_paths:
            logger.info(f"  🩹 Plan path normalization applied: {changed_paths} canonical rename(s)")

        return PlanResult(
            subtasks=normalized_subtasks,
            execution_groups=plan.execution_groups,
            risks=plan.risks,
            summary=plan.summary,
        )

    def _normalize_plan_path_list_against_analysis(
        self,
        paths: list[str],
        user_story: UserStory,
        analysis: AnalysisResult,
    ) -> tuple[list[str], int]:
        normalized = []
        changed = 0
        for path in paths:
            rewritten = self._normalize_single_plan_path_against_analysis(path, user_story, analysis)
            if rewritten != path:
                changed += 1
            normalized.append(rewritten)
        return normalized, changed

    def _normalize_single_plan_path_against_analysis(
        self,
        path: str,
        user_story: UserStory,
        analysis: AnalysisResult,
    ) -> str:
        normalized = (path or "").replace("\\", "/")
        if not normalized.endswith(".java"):
            return normalized

        canonical = self._canonical_plan_filename_for_path(normalized, analysis)
        if not canonical:
            return normalized

        current_name = Path(normalized).name
        current_stem = current_name[:-5]
        canonical_stem = canonical[:-5]
        current_base, suffix = self._split_java_type_suffix(current_stem)
        canonical_base, canonical_suffix = self._split_java_type_suffix(canonical_stem)
        if not suffix or suffix != canonical_suffix or not current_base or not canonical_base:
            return normalized
        if current_stem == canonical_stem:
            return normalized

        allowed_tokens = self._allowed_domain_tokens(user_story, analysis)
        current_tokens = self._tokenize_domain_text(current_base)
        canonical_tokens = self._tokenize_domain_text(canonical_base)
        if not current_tokens or not canonical_tokens:
            return normalized
        if not (current_tokens & allowed_tokens and canonical_tokens & allowed_tokens):
            return normalized

        parent = normalized.rsplit("/", 1)[0]
        return f"{parent}/{canonical}"

    def _canonical_plan_filename_for_path(self, path: str, analysis: AnalysisResult) -> Optional[str]:
        normalized = path.replace("\\", "/")
        filename = Path(normalized).name
        service_name = analysis.service_name or "Resource"
        entity_name = analysis.entities[0].name if analysis.entities else f"{service_name}Entity"

        canonical_by_suffix = {
            "Controller": f"{service_name}Controller.java",
            "Service": f"{service_name}Service.java",
            "ServiceImpl": f"{service_name}ServiceImpl.java",
            "Request": f"{service_name}Request.java",
            "Response": f"{service_name}Response.java",
            "Repository": f"{entity_name}Repository.java",
            "Entity": f"{entity_name}.java",
            "ControllerTest": f"{service_name}ControllerTest.java",
            "ServiceTest": f"{service_name}ServiceTest.java",
            "ServiceImplTest": f"{service_name}ServiceImplTest.java",
            "RepositoryTest": f"{entity_name}RepositoryTest.java",
            "IntegrationTest": f"{service_name}IntegrationTest.java",
        }

        for suffix, canonical in canonical_by_suffix.items():
            if filename.endswith(f"{suffix}.java"):
                return canonical
        return None

    def _paths_match_by_canonical_story_resource(
        self,
        planned_path: str,
        actual_path: str,
        analysis: AnalysisResult,
    ) -> bool:
        planned = planned_path.replace("\\", "/")
        actual = actual_path.replace("\\", "/")
        if not planned.endswith(".java") or not actual.endswith(".java"):
            return False
        if not actual.startswith("src/main/java/"):
            return False

        planned_canonical = self._canonical_plan_filename_for_path(planned, analysis)
        actual_canonical = self._canonical_plan_filename_for_path(actual, analysis)
        if not planned_canonical or not actual_canonical:
            return False
        if planned_canonical != actual_canonical:
            return False

        planned_parent = planned.rsplit("/", 1)[0]
        actual_parent = actual.rsplit("/", 1)[0]
        return planned_parent == actual_parent

    def _split_java_type_suffix(self, stem: str) -> tuple[str, str]:
        for suffix in (
            "ControllerTest",
            "ServiceImplTest",
            "ServiceTest",
            "RepositoryTest",
            "IntegrationTest",
            "ServiceImpl",
            "Controller",
            "Repository",
            "Request",
            "Response",
            "Service",
            "Entity",
        ):
            if stem.endswith(suffix):
                return stem[: -len(suffix)], suffix
        return stem, ""

    def _allowed_domain_tokens(self, user_story: UserStory, analysis: AnalysisResult) -> set[str]:
        tokens = set()
        candidates = [analysis.service_name, user_story.title, user_story.description]
        candidates.extend(user_story.acceptance_criteria)
        candidates.extend(e.name for e in analysis.entities)
        candidates.extend(ep.path for ep in analysis.endpoints)
        for value in candidates:
            tokens.update(self._tokenize_domain_text(value))

        # Enrich with GraphRAG entities and file names for this story
        if self._graphrag_context is not None:
            try:
                relevant = self._graphrag_context.filter_for_story(user_story.id)
                for entity in relevant.entities:
                    if entity.name:
                        tokens.update(self._tokenize_domain_text(entity.name))
                for rel in relevant.relations:
                    if rel.source:
                        tokens.update(self._tokenize_domain_text(rel.source))
                    if rel.target:
                        tokens.update(self._tokenize_domain_text(rel.target))
                for doc in getattr(relevant, "documents", []):
                    name = getattr(doc, "title", None) or getattr(doc, "name", None)
                    if name:
                        tokens.update(self._tokenize_domain_text(str(name)))
            except Exception:
                pass

        expanded = set(tokens)
        for token in list(tokens):
            expanded.update(self._domain_token_aliases(token))
        return {token for token in expanded if token}

    def _tokenize_domain_text(self, value: Optional[str]) -> set[str]:
        if not value:
            return set()
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
        cleaned = camel_split.replace("{", " ").replace("}", " ").replace("/", " ").replace("-", " ")
        raw_tokens = re.findall(r"[A-Za-zÀ-ÿ]+", cleaned)
        stopwords = {
            "api", "status", "statut", "consultation", "consulter", "story", "user", "ised",
            "pour", "avec", "dans", "une", "des", "the", "and", "for", "from", "that",
            "controller", "service", "repository", "entity", "request", "response", "impl", "test",
        }
        tokens = set()
        for raw in raw_tokens:
            token = raw.lower()
            if len(token) <= 2 or token in stopwords:
                continue
            tokens.add(token)
            if token.endswith("s") and len(token) > 4:
                tokens.add(token[:-1])
        return tokens

    def _domain_token_aliases(self, token: str) -> set[str]:
        normalized = (token or "").strip().lower()
        if not normalized:
            return set()

        aliases = {normalized}

        # Conservative abbreviation support for long domain words.
        # This keeps validation useful while avoiding one-off story-specific aliases.
        if len(normalized) >= 8:
            aliases.add(normalized[:4])
        if len(normalized) >= 10:
            aliases.add(normalized[:5])

        # Basic morphological normalization for common English/French suffixes.
        for suffix in ("tion", "ing", "ed", "eur", "ique", "ment"):
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 4:
                aliases.add(normalized[: -len(suffix)])

        return aliases

    def _extract_resource_tokens_from_path(self, path: str) -> set[str]:
        normalized = path.replace("\\", "/")
        filename = Path(normalized).name.replace(".java", "")
        for suffix in ("Controller", "ServiceImpl", "Service", "Repository", "Request", "Response", "Entity", "Test"):
            if filename.endswith(suffix):
                filename = filename[: -len(suffix)]
                break
        return self._tokenize_domain_text(filename)

    def _story_scope_impacted_paths(self, story_scope: StoryScope) -> list[str]:
        preferred = (
            list(story_scope.new_files)
            + list(story_scope.modified_files)
            + list(story_scope.fixer_touched_files)
            + list(story_scope.test_targets)
            + list(story_scope.entrypoints)
            + list(story_scope.business_files)
            + list(story_scope.dependencies)
        )
        excluded = {path.replace("\\", "/") for path in story_scope.excluded_files}
        return [
            path for path in self._normalize_story_scope_paths(preferred)
            if path not in excluded
        ]

    def _story_scope_test_anchors(
        self,
        analysis: AnalysisResult,
        story_scope: StoryScope,
    ) -> tuple[set[str], set[str]]:
        class_names: set[str] = set()
        tokens: set[str] = set(self._generic_resource_tokens())

        for path in self._story_scope_impacted_paths(story_scope):
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java"):
                continue
            stem = Path(normalized).stem
            class_names.add(stem)
            tokens.update(self._extract_resource_tokens_from_path(normalized))

        service_name = (analysis.service_name or "").strip()
        if service_name:
            class_names.add(service_name)
            tokens.update(self._tokenize_domain_text(service_name))

        for entity in analysis.entities:
            if entity.name:
                class_names.add(entity.name)
                tokens.update(self._tokenize_domain_text(entity.name))

        for endpoint in analysis.endpoints:
            tokens.update(self._tokenize_domain_text(endpoint.path))
            tokens.update(self._tokenize_domain_text(endpoint.description))

        if self._graphrag_context is not None:
            try:
                relevant = self._graphrag_context.filter_for_story(story_scope.story_id)
                for entity in relevant.entities:
                    if entity.name:
                        class_names.add(entity.name)
                        tokens.update(self._tokenize_domain_text(entity.name))
            except Exception:
                pass

        return class_names, {token for token in tokens if token}

    def _test_file_matches_story_scope(
        self,
        path: str,
        content: str,
        analysis: AnalysisResult,
        story_scope: StoryScope,
    ) -> bool:
        normalized = path.replace("\\", "/")
        if "/support/" in normalized or normalized.endswith("/CoverageSafetyNetTest.java"):
            return True

        class_names, tokens = self._story_scope_test_anchors(analysis, story_scope)
        stem = Path(normalized).stem
        stem_tokens = self._extract_resource_tokens_from_path(normalized)
        if stem in class_names or stem_tokens.intersection(tokens):
            return True

        blocked_markers = ("helloworld", "legacy", "oldstory", "old_story", "old")
        if any(marker in stem.lower() for marker in blocked_markers):
            return False

        imported_project_classes = {
            fqcn.rsplit(".", 1)[-1]
            for fqcn in re.findall(r"^\s*import\s+([a-zA-Z0-9_.]+)\s*;", content or "", re.MULTILINE)
            if fqcn.startswith((analysis.package_base or "com.example.app") + ".")
        }
        if imported_project_classes and imported_project_classes.intersection(class_names):
            return True

        return False

    def _build_story_scoped_smoke_test(
        self,
        generated_code: GeneratedCode,
        analysis: AnalysisResult,
        story_scope: StoryScope,
    ) -> tuple[str, str]:
        package_name = analysis.package_base or "com.example.app"
        package_path = package_name.replace(".", "/")
        impacted_paths = [
            path for path in self._story_scope_impacted_paths(story_scope)
            if path.startswith("src/main/java/") and path.endswith(".java")
        ]
        imports: list[str] = []
        assertions: list[str] = []

        for path in impacted_paths[:5]:
            rel = path[len("src/main/java/") :].replace("/", ".").replace(".java", "")
            class_name = Path(path).stem
            imports.append(f"import {rel};")
            assertions.append(f"        assertThat({class_name}.class).isNotNull();")

        if not assertions:
            assertions.append('        assertThat("story-scope").isEqualTo("story-scope");')

        path = f"src/test/java/{package_path}/StoryScopeSmokeTest.java"
        content = (
            f"package {package_name};\n\n"
            + ("\n".join(imports) + "\n\n" if imports else "")
            + "import org.junit.jupiter.api.Test;\n"
            + "import static org.assertj.core.api.Assertions.assertThat;\n\n"
            + "class StoryScopeSmokeTest {\n\n"
            + "    @Test\n"
            + "    void smokeTest_storyScopedClassesCompile() {\n"
            + "\n".join(assertions)
            + "\n    }\n"
            + "}\n"
        )
        return path, content

    def _generic_resource_tokens(self) -> set[str]:
        generic_names = {
            "Application",
            "OpenApiConfig",
            "HealthCheck",
            "ErrorResponse",
            "ResourceNotFoundException",
            "BusinessException",
            "GlobalExceptionHandler",
        }
        tokens: set[str] = set()
        for name in generic_names:
            tokens.add(name.lower())
            tokens.update(self._tokenize_domain_text(name))
        return tokens

    def _empty_repo_analysis(self):
        from core.models import RepoAnalysis

        return RepoAnalysis(
            repo_path="",
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
            summary="No existing repository provided; bootstrap a new project from scratch.",
        )

    def _load_existing_project_code(self, repo_path: Optional[str]) -> Optional[GeneratedCode]:
        if not repo_path:
            return None

        root = Path(repo_path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repository path does not exist: {root}")

        skip_dirs = {
            ".git", ".idea", ".vscode", ".gradle", ".mvn", "target",
            "build", "node_modules", "__pycache__", ".venv", "venv",
        }
        files: Dict[str, str] = {}
        pom_xml = ""
        readme = ""

        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(root).as_posix()
            if any(part in skip_dirs for part in rel.split("/")):
                continue
            filename = Path(rel).name
            if rel.startswith("src/main/java/") and (
                filename.endswith("Test.java") or filename.endswith("Tests.java")
            ):
                continue
            try:
                content = fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if rel == "pom.xml":
                pom_xml = content
            elif rel.lower() == "readme.md":
                readme = content
            else:
                files[rel] = content

        if not files and not pom_xml and not readme:
            return None

        return GeneratedCode(files=files, pom_xml=pom_xml, readme=readme)

    # ──────────────────────────────────────────────────────────────
    #  Compile with pre-checks (structural validation)
    # ──────────────────────────────────────────────────────────────

    async def _compile_with_precheck(
        self,
        generated_code: GeneratedCode,
        analysis: AnalysisResult,
        user_story: UserStory,
    ):
        """Apply deterministic fixes, structural pre-checks, then mvn compile."""
        generated_code, det_fixes = self._apply_deterministic_compile_fixes(generated_code)
        if det_fixes:
            logger.info(f"  🩹 Corrections déterministes pré-compilation: {det_fixes}")

        duplicates = self._detect_duplicate_classes(generated_code)
        malformed = self._detect_malformed_java_sources(generated_code, analysis.package_base)
        violations = self._detect_convention_violations(generated_code)

        if duplicates or malformed or violations:
            synthetic = []
            for fqcn, paths in duplicates.items():
                for p in paths:
                    synthetic.append(CompileError(file=Path(p).name, line=1,
                                                   message=f"duplicate class: {fqcn}", code_snippet=p))
            for file_path, issue in malformed:
                synthetic.append(CompileError(file=Path(file_path).name, line=1,
                                               message=f"source invalide: {issue}", code_snippet=file_path))
            for file_path, vtype, lnum in violations:
                synthetic.append(CompileError(file=Path(file_path).name, line=lnum,
                                               message=f"violation: {vtype}", code_snippet=file_path))
            logger.warning(f"  ⚠️  {len(synthetic)} problème(s) structurel(s)")
            precheck = CompileResult(success=False, errors=synthetic)
            try:
                generated_code = await self.developer.fix_compile_errors(
                    user_story, analysis, generated_code, precheck
                )
                generated_code, _ = self._apply_deterministic_compile_fixes(generated_code)
            except Exception as e:
                logger.warning(f"  ⚠️  Pré-correction ignorée: {e}")

        result = await self.build_runner.compile_main(generated_code)
        logger.info(f"  {'✅' if result.success else '❌'} Compilation: {result.error_count} erreur(s)")
        return generated_code, result

    # ──────────────────────────────────────────────────────────────
    #  Review loop
    # ──────────────────────────────────────────────────────────────

    async def _review_and_correct(
        self,
        generated_code: GeneratedCode,
        analysis: AnalysisResult,
        user_story: UserStory,
        docs: dict,
    ):
        """Review + auto-correct (max MAX_REVIEW_LOOPS)."""
        for attempt in range(1, MAX_REVIEW_LOOPS + 1):
            try:
                review = await self.reviewer.review(generated_code, analysis)
            except Exception as e:
                logger.warning(f"  ⚠️  Review indisponible: {e}")
                return ReviewResult(
                    score=0, approved=False,
                    summary="Review indisponible", issues=[], positives=[], correction_prompt="",
                ), generated_code

            logger.info(
                f"  📋 Review #{attempt}: {review.score}/100 | "
                f"CRITICAL={review.critical_count} MAJOR={review.major_count}"
            )
            if self._is_review_accepted(review):
                logger.info(f"  ✅ Code approuvé au round {attempt}")
                return review, generated_code

            if attempt < MAX_REVIEW_LOOPS:
                try:
                    generated_code = await self.developer.correct(
                        user_story=user_story, analysis=analysis, docs=docs,
                        previous_code=generated_code,
                        correction_prompt=review.correction_prompt,
                        review_issues=[vars(i) for i in review.issues],
                    )
                except Exception as e:
                    logger.warning(f"  ⚠️  Correction post-review ignorée: {e}")
                    break

        logger.warning(f"  ⚠️  Score insuffisant après {MAX_REVIEW_LOOPS} round(s)")
        return review, generated_code

    # ──────────────────────────────────────────────────────────────
    #  Deterministic compile fixes (unchanged from previous version)
    # ──────────────────────────────────────────────────────────────

    def _is_review_accepted(self, review: ReviewResult) -> bool:
        min_score = self.settings.pipeline.min_review_score
        return bool(review.approved or review.score >= min_score)

    def _detect_duplicate_classes(self, generated_code: GeneratedCode) -> Dict[str, list]:
        declarations: Dict[str, list] = {}
        package_pattern = re.compile(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;", re.MULTILINE)
        type_pattern = re.compile(r"\b(class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)")
        for file_path, content in generated_code.files.items():
            normalized = file_path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue
            pm = package_pattern.search(content)
            pkg = pm.group(1) if pm else ""
            tm = type_pattern.search(content)
            if not tm:
                continue
            fqcn = f"{pkg}.{tm.group(2)}" if pkg else tm.group(2)
            declarations.setdefault(fqcn, []).append(normalized)
        return {k: v for k, v in declarations.items() if len(v) > 1}

    def _apply_deterministic_compile_fixes(self, generated_code: GeneratedCode) -> tuple:
        fixed_files: Dict[str, str] = {}
        renamed_files: Dict[str, str] = {}
        fixes = 0

        for file_path, content in generated_code.files.items():
            normalized = file_path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue
            updated = content
            ff = 0
            if self._is_misplaced_test_source(normalized, updated):
                new_path = normalized.replace("src/main/java/", "src/test/java/", 1)
                if new_path not in generated_code.files and new_path not in fixed_files:
                    renamed_files[new_path] = updated
                    fixes += 1
                    continue
            if re.search(r"\binterface\b", updated) and "@RequiredArgsConstructor" in updated:
                updated = re.sub(r"^\s*@RequiredArgsConstructor\s*\n", "", updated, flags=re.MULTILINE)
                updated = re.sub(r"^\s*import\s+lombok\.RequiredArgsConstructor\s*;\s*\n", "", updated, flags=re.MULTILINE)
                ff += 1
            if "@Operation" in updated and "import io.swagger.v3.oas.annotations.Operation;" not in updated:
                updated, ins = self._insert_java_import(updated, "import io.swagger.v3.oas.annotations.Operation;")
                if ins: ff += 1
            if "@Tag" in updated and "import io.swagger.v3.oas.annotations.tags.Tag;" not in updated:
                updated, ins = self._insert_java_import(updated, "import io.swagger.v3.oas.annotations.tags.Tag;")
                if ins: ff += 1
            if ff > 0:
                fixed_files[file_path] = updated
                fixes += ff
            pt = re.search(r"\bpublic\s+(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)", updated)
            if pt:
                expected = f"{pt.group(1)}.java"
                if Path(normalized).name != expected:
                    new_path = str(Path(normalized).with_name(expected)).replace("\\", "/")
                    if new_path not in generated_code.files and new_path not in fixed_files:
                        renamed_files[new_path] = updated
                        fixes += 1
                        continue
            fixed_files[file_path] = updated

        updated_pom = generated_code.pom_xml
        needs_tx = any(
            "org.springframework.transaction.annotation.Transactional" in c
            for p, c in fixed_files.items() if p.replace("\\", "/").endswith(".java")
        )
        needs_jpa = any(
            "import jakarta.persistence." in c or "@Entity" in c or "@Table(" in c
            for p, c in fixed_files.items() if p.replace("\\", "/").endswith(".java")
        )
        if (needs_tx or needs_jpa) and updated_pom and "spring-boot-starter-data-jpa" not in updated_pom:
            dep = (
                "        <dependency>\n"
                "            <groupId>org.springframework.boot</groupId>\n"
                "            <artifactId>spring-boot-starter-data-jpa</artifactId>\n"
                "        </dependency>\n"
            )
            updated_pom = updated_pom.replace("    </dependencies>", f"{dep}    </dependencies>")
            fixes += 1

        for path, content in list(fixed_files.items()):
            n = path.replace("\\", "/")
            if n.endswith("/exception/GlobalExceptionHandler.java"):
                p = content
                if "import lombok.extern.slf4j.Slf4j;" in p:
                    p = p.replace("import lombok.extern.slf4j.Slf4j;\n", ""); fixes += 1
                if "@Slf4j\n" in p:
                    p = p.replace("@Slf4j\n", ""); fixes += 1
                if "import org.slf4j.Logger;" not in p:
                    p, ins = self._insert_java_import(p, "import org.slf4j.Logger;")
                    if ins: fixes += 1
                if "import org.slf4j.LoggerFactory;" not in p:
                    p, ins = self._insert_java_import(p, "import org.slf4j.LoggerFactory;")
                    if ins: fixes += 1
                if "private static final Logger log" not in p:
                    p = p.replace(
                        "public class GlobalExceptionHandler {",
                        "public class GlobalExceptionHandler {\n\n    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);"
                    ); fixes += 1
                builder_call = (
                    "return ErrorResponse.builder()\n"
                    "                .status(status)\n"
                    "                .message(message)\n"
                    "                .timestamp(LocalDateTime.now().toString())\n"
                    "                .build();"
                )
                constructor_call = "return new ErrorResponse(status, message, LocalDateTime.now().toString());"
                if builder_call in p:
                    p = p.replace(builder_call, constructor_call); fixes += 1
                fixed_files[path] = p

        for path, content in list(fixed_files.items()):
            if path.replace("\\", "/").endswith("/exception/ErrorResponse.java") and "@Builder" in content:
                package_name = "com.example.app.exception"
                package_match = re.search(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;", content, re.MULTILINE)
                if package_match:
                    package_name = package_match.group(1)
                fixed_files[path] = (
                    f"package {package_name};\n\n"
                    "public class ErrorResponse {\n"
                    "    private int status;\n    private String message;\n    private String timestamp;\n\n"
                    "    public ErrorResponse() {}\n\n"
                    "    public ErrorResponse(int status, String message, String timestamp) {\n"
                    "        this.status = status; this.message = message; this.timestamp = timestamp;\n    }\n\n"
                    "    public int getStatus() { return status; }\n"
                    "    public void setStatus(int s) { this.status = s; }\n"
                    "    public String getMessage() { return message; }\n"
                    "    public void setMessage(String m) { this.message = m; }\n"
                    "    public String getTimestamp() { return timestamp; }\n"
                    "    public void setTimestamp(String t) { this.timestamp = t; }\n"
                    "}\n"
                ); fixes += 1

        fixed_files, model_fix_count = self._apply_model_consistency_fixes(fixed_files)
        fixes += model_fix_count

        if fixes == 0:
            return generated_code, 0
        merged = dict(generated_code.files)
        merged.update(fixed_files)
        for new_path, content in renamed_files.items():
            old = [k for k, v in merged.items() if v == content and k != new_path]
            for o in old:
                merged.pop(o, None)
            merged[new_path] = content
        return GeneratedCode(files=merged, pom_xml=updated_pom, readme=generated_code.readme), fixes

    def _apply_model_consistency_fixes(self, files: Dict[str, str]) -> tuple[Dict[str, str], int]:
        specs = self._build_model_class_specs(files)
        if not specs:
            return files, 0

        expected_fields = self._collect_expected_model_fields(files, specs)
        updated = dict(files)
        fixes = 0

        for class_name, requested_fields in expected_fields.items():
            spec = specs.get(class_name)
            if not spec:
                continue
            existing_fields = spec["field_types"]
            if not self._class_supports_generated_model_fields(spec["content"]):
                continue

            additions: list[tuple[str, str]] = []
            for field_name, candidate_types in requested_fields.items():
                if field_name in existing_fields:
                    continue
                inferred_type = self._choose_model_field_type(field_name, candidate_types, specs)
                additions.append((field_name, inferred_type))

            if not additions:
                continue

            new_content = spec["content"]
            for field_name, inferred_type in additions:
                new_content = self._insert_field_into_java_class(new_content, field_name, inferred_type)
                existing_fields[field_name] = inferred_type
                fixes += 1

            updated[spec["path"]] = new_content

        return updated, fixes

    def _build_model_class_specs(self, files: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        specs: Dict[str, Dict[str, Any]] = {}
        field_pattern = re.compile(
            r"^\s*(?:private|protected|public)\s+(?!static\b)(?:final\s+)?([A-Z][A-Za-z0-9_<>,.\[\]? ]*|int|long|double|float|boolean|Integer|Long|Double|Float|Boolean|String)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*;\s*$",
            re.MULTILINE,
        )
        for path, content in files.items():
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue
            if not any(token in normalized for token in ("/entity/", "/dto/", "/model/")):
                continue
            type_match = re.search(r"\b(?:class|record)\s+([A-Z][A-Za-z0-9_]*)\b", content)
            if not type_match:
                continue
            field_types = {
                field_name: " ".join(field_type.split())
                for field_type, field_name in field_pattern.findall(content)
            }
            specs[type_match.group(1)] = {
                "path": path,
                "content": content,
                "field_types": field_types,
            }
        return specs

    def _collect_expected_model_fields(
        self,
        files: Dict[str, str],
        specs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, set[str]]]:
        expected: Dict[str, Dict[str, set[str]]] = {}
        known_classes = set(specs.keys())

        for path, content in files.items():
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue

            variable_types = self._extract_java_variable_types(content)
            current_builder_class: Optional[str] = None
            for raw_line in content.splitlines():
                line = raw_line.strip()
                builder_start = re.search(r"\b([A-Z][A-Za-z0-9_]*)\.builder\(\)", line)
                if builder_start:
                    candidate_class = builder_start.group(1)
                    current_builder_class = candidate_class if candidate_class in known_classes else None
                elif current_builder_class and ".build()" in line:
                    current_builder_class = None

                if current_builder_class:
                    builder_line = re.match(r"\.([a-zA-Z_][A-Za-z0-9_]*)\((.*)\)\s*$", line)
                    if builder_line:
                        field_name, arg_expr = builder_line.groups()
                        expected.setdefault(current_builder_class, {}).setdefault(field_name, set()).add(
                            self._infer_java_expression_type(arg_expr.strip(), variable_types, specs)
                        )

                for accessor_match in re.finditer(
                    r"\b([a-zA-Z_][A-Za-z0-9_]*)\.(get|set)([A-Z][A-Za-z0-9_]*)\((.*)\)",
                    line,
                ):
                    var_name, accessor_kind, suffix, args = accessor_match.groups()
                    class_name = variable_types.get(var_name, "").replace("java.lang.", "").strip()
                    if class_name not in known_classes:
                        continue
                    field_name = suffix[0].lower() + suffix[1:]
                    inferred = "String"
                    if accessor_kind == "set":
                        inferred = self._infer_java_expression_type(args.strip(), variable_types, specs)
                    else:
                        inferred = specs.get(class_name, {}).get("field_types", {}).get(field_name, "String")
                    expected.setdefault(class_name, {}).setdefault(field_name, set()).add(inferred)

        return expected

    def _extract_java_variable_types(self, content: str) -> Dict[str, str]:
        variable_types: Dict[str, str] = {}
        declaration_patterns = (
            re.compile(
                r"\b(?:private|protected|public|final)\s+([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*(?:=[^;]*)?;"
            ),
            re.compile(
                r"\b([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*=\s*[^;]+;"
            ),
        )
        for pattern in declaration_patterns:
            for type_name, var_name in pattern.findall(content):
                variable_types[var_name] = " ".join(type_name.split())

        for params in re.findall(r"\(([^)]*)\)", content):
            for raw_param in params.split(","):
                param = raw_param.strip()
                match = re.match(r"([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)$", param)
                if match:
                    variable_types[match.group(2)] = " ".join(match.group(1).split())

        return variable_types

    def _infer_java_expression_type(
        self,
        expr: str,
        variable_types: Dict[str, str],
        specs: Dict[str, Dict[str, Any]],
    ) -> str:
        candidate = expr.strip()
        if not candidate:
            return "String"
        if candidate == "null":
            return "String"
        if candidate in {"true", "false"}:
            return "Boolean"
        if re.fullmatch(r'"[^"]*"', candidate):
            return "String"
        if re.fullmatch(r"-?\d+[lL]", candidate):
            return "Long"
        if re.fullmatch(r"-?\d+", candidate):
            return "Integer"
        if re.fullmatch(r"-?\d+\.\d+[dD]?", candidate):
            return "Double"
        if re.fullmatch(r"-?\d+\.\d+[fF]", candidate):
            return "Float"

        getter_match = re.fullmatch(r"([a-zA-Z_][A-Za-z0-9_]*)\.get([A-Z][A-Za-z0-9_]*)\(\)", candidate)
        if getter_match:
            var_name, suffix = getter_match.groups()
            class_name = variable_types.get(var_name, "").replace("java.lang.", "").strip()
            field_name = suffix[0].lower() + suffix[1:]
            if class_name in specs:
                return specs[class_name]["field_types"].get(field_name, "String")

        return variable_types.get(candidate, "String").replace("java.lang.", "").strip() or "String"

    def _choose_model_field_type(
        self,
        field_name: str,
        candidate_types: set[str],
        specs: Dict[str, Dict[str, Any]],
    ) -> str:
        normalized_candidates = [
            candidate.replace("java.lang.", "").strip()
            for candidate in candidate_types
            if candidate and candidate != "unknown"
        ]
        for candidate in normalized_candidates:
            if candidate:
                return candidate

        for spec in specs.values():
            inferred = spec["field_types"].get(field_name)
            if inferred:
                return inferred

        return "String"

    def _class_supports_generated_model_fields(self, content: str) -> bool:
        if any(annotation in content for annotation in ("@Data", "@Getter", "@Setter", "@Builder")):
            return True
        return bool(re.search(r"\b(?:get|set)[A-Z][A-Za-z0-9_]*\s*\(", content))

    def _insert_field_into_java_class(self, content: str, field_name: str, field_type: str) -> str:
        field_line = f"    private {field_type} {field_name};\n"
        if field_line in content:
            return content

        lines = content.splitlines()
        insert_at = None
        method_or_ctor_pattern = re.compile(
            r"^\s*(?:public|protected|private)\s+(?:[A-Z][A-Za-z0-9_]*\s*\(|[\w<>\[\],.? ]+\s+[a-zA-Z_][A-Za-z0-9_]*\s*\()"
        )

        for idx, line in enumerate(lines):
            if method_or_ctor_pattern.match(line):
                insert_at = idx
                break

        if insert_at is None:
            for idx in range(len(lines) - 1, -1, -1):
                if lines[idx].strip() == "}":
                    insert_at = idx
                    break

        if insert_at is None:
            return content

        if insert_at > 0 and lines[insert_at - 1].strip():
            lines.insert(insert_at, "")
            insert_at += 1
        lines.insert(insert_at, field_line.rstrip("\n"))
        return "\n".join(lines) + "\n"

    def _is_misplaced_test_source(self, path: str, content: str) -> bool:
        normalized = path.replace("\\", "/")
        if not normalized.startswith("src/main/java/"):
            return False
        filename = Path(normalized).name
        if filename.endswith("Test.java") or filename.endswith("Tests.java"):
            return True
        test_markers = (
            "org.junit.",
            "org.mockito.",
            "org.springframework.test.",
            "org.springframework.boot.test.",
            "@Test",
            "@WebMvcTest",
            "@SpringBootTest",
            "@DataJpaTest",
        )
        return any(marker in content for marker in test_markers)

    def _insert_java_import(self, content: str, import_line: str) -> tuple:
        if import_line in content:
            return content, False
        lines = content.splitlines()
        idxs = [i for i, l in enumerate(lines) if l.strip().startswith("import ")]
        if idxs:
            lines.insert(idxs[-1] + 1, import_line)
            return "\n".join(lines) + "\n", True
        pidxs = [i for i, l in enumerate(lines) if l.strip().startswith("package ")]
        if pidxs:
            lines.insert(pidxs[0] + 1, ""); lines.insert(pidxs[0] + 2, import_line)
            return "\n".join(lines) + "\n", True
        lines.insert(0, import_line)
        return "\n".join(lines) + "\n", True

    def _detect_malformed_java_sources(self, generated_code: GeneratedCode, pkg_base: str) -> list:
        issues = []
        pp = re.compile(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;", re.MULTILINE)
        tp = re.compile(r"\b(class|interface|enum|record)\s+[A-Za-z_][A-Za-z0-9_]*")
        for file_path, content in generated_code.files.items():
            n = file_path.replace("\\", "/")
            if not n.endswith(".java") or n.startswith("src/test/"):
                continue
            src = (content or "").strip()
            if not src:
                issues.append((n, "fichier vide")); continue
            pm = pp.search(src)
            if not pm:
                issues.append((n, "package manquant")); continue
            if pkg_base and not pm.group(1).startswith(pkg_base):
                issues.append((n, f"package inattendu: {pm.group(1)}"))
            if not tp.search(src):
                issues.append((n, "déclaration de type manquante"))
        return issues

    def _detect_convention_violations(self, generated_code: GeneratedCode) -> list:
        violations = []
        forbidden = [
            (r'import\s+javax\.persistence\.', "INTERDIT: javax.persistence.* → jakarta.*"),
            (r'import\s+javax\.validation\.', "INTERDIT: javax.validation.* → jakarta.*"),
            (r'import\s+javax\.', "INTERDIT: javax.* → jakarta.*"),
            (r'import\s+jakarta\.ws\.rs\.', "INTERDIT: jakarta.ws.rs.* → Spring MVC"),
            (r'@Path\s*\(', "INTERDIT: @Path (JAX-RS)"),
            (r'import\s+springfox\.', "INTERDIT: springfox.* → springdoc-openapi"),
            (r'@Autowired\s+private\s+', "INTERDIT: @Autowired → @RequiredArgsConstructor"),
        ]
        for file_path, content in generated_code.files.items():
            n = file_path.replace("\\", "/")
            if not n.endswith(".java") or n.startswith("src/test/"):
                continue
            for lnum, line in enumerate(content.split('\n'), 1):
                for pat, msg in forbidden:
                    if re.search(pat, line):
                        violations.append((n, msg, lnum))
        return violations

    def _fix_application_java(
        self,
        generated_code: GeneratedCode,
        analysis: AnalysisResult,
        preserve_existing: bool = False,
    ) -> GeneratedCode:
        fixed = dict(generated_code.files)
        changed = False
        forced = (
            f"package {analysis.package_base};\n\n"
            "import org.springframework.boot.SpringApplication;\n"
            "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
            "@SpringBootApplication\n"
            "public class Application {\n\n"
            "    public static void main(String[] args) {\n"
            "        SpringApplication.run(Application.class, args);\n"
            "    }\n}\n"
        )
        for path in list(fixed.keys()):
            if path.replace("\\", "/").endswith("Application.java"):
                if preserve_existing:
                    continue
                fixed[path] = forced
                changed = True
        if changed:
            logger.info("  🛠️ Application.java forcé (déterministe)")
        return GeneratedCode(files=fixed, pom_xml=generated_code.pom_xml, readme=generated_code.readme)

    # ──────────────────────────────────────────────────────────────
    #  File I/O + artefacts
    # ──────────────────────────────────────────────────────────────

    def _write_all(self, generated_code: GeneratedCode, test_result: TestResult, story_id: str) -> Path:
        output_path = self.settings.pipeline.output_dir / story_id
        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        for file_path, content in generated_code.files.items():
            full = output_path / file_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
        for file_path, content in test_result.test_files.items():
            full = output_path / file_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
        if generated_code.pom_xml:
            (output_path / "pom.xml").write_text(generated_code.pom_xml, encoding="utf-8")
        if generated_code.readme:
            (output_path / "README.md").write_text(generated_code.readme, encoding="utf-8")
        return output_path

    def _is_local_git_repo(self, repo_path: str) -> bool:
        return (Path(repo_path).resolve() / ".git").exists()

    def _save_artifact(self, filename: str, data: dict):
        d = self.settings.pipeline.artifacts_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_generated_code_from_output(self, story_id: str) -> Optional[GeneratedCode]:
        output_path = self.settings.pipeline.output_dir / story_id
        if not output_path.exists():
            return None
        files: Dict[str, str] = {}
        for fp in output_path.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(output_path).as_posix()
            if rel in ("pom.xml", "README.md"):
                continue
            files[rel] = fp.read_text(encoding="utf-8")
        pom = (output_path / "pom.xml").read_text(encoding="utf-8") if (output_path / "pom.xml").exists() else ""
        readme = (output_path / "README.md").read_text(encoding="utf-8") if (output_path / "README.md").exists() else ""
        return GeneratedCode(files=files, pom_xml=pom, readme=readme) if files else None

    def _combine_test_files(
        self,
        generated_code: GeneratedCode,
        test_result: TestResult,
        story_scope: Optional[StoryScope] = None,
    ) -> Dict[str, str]:
        combined = {
            path.replace("\\", "/"): content
            for path, content in generated_code.files.items()
            if path.replace("\\", "/").startswith("src/test/")
        }
        combined.update(self._extract_test_files_from_result(test_result))
        if story_scope is None:
            return combined

        allowed_tokens = {
            token
            for path in self._story_scope_impacted_paths(story_scope)
            for token in self._extract_resource_tokens_from_path(path)
        }
        if not allowed_tokens:
            return combined

        filtered: Dict[str, str] = {}
        for path, content in combined.items():
            normalized = path.replace("\\", "/")
            if "/support/" in normalized:
                filtered[path] = content
                continue
            path_tokens = self._extract_resource_tokens_from_path(normalized)
            if not path_tokens or allowed_tokens.intersection(path_tokens):
                filtered[path] = content
        return filtered

    def _extract_test_files_from_result(self, test_result: TestResult) -> Dict[str, str]:
        extracted: Dict[str, str] = {}
        for path, content in (test_result.test_files or {}).items():
            extracted[path.replace("\\", "/")] = content

        generated_files = (test_result.metadata or {}).get("generated_files")
        if isinstance(generated_files, dict):
            for path, content in generated_files.items():
                if isinstance(path, str) and isinstance(content, str):
                    extracted[path.replace("\\", "/")] = content
            return extracted

        if isinstance(generated_files, list):
            for entry in generated_files:
                path = None
                content = None
                if isinstance(entry, dict):
                    path = entry.get("path")
                    content = entry.get("content")
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    path, content = entry[0], entry[1]
                else:
                    path = getattr(entry, "path", None)
                    content = getattr(entry, "content", None)
                if isinstance(path, str) and isinstance(content, str):
                    extracted[path.replace("\\", "/")] = content
        return extracted

    def _normalize_test_execution_path(self, path: str) -> str:
        normalized = (path or "").strip().replace("\\", "/")
        if not normalized:
            return normalized
        if normalized.startswith("src/test/java/"):
            return normalized
        if normalized.startswith("src/test/"):
            return f"src/test/java/{normalized[len('src/test/'):].lstrip('/')}"
        if normalized.startswith("src/main/java/"):
            return "src/test/java/" + normalized[len("src/main/java/") :]
        if normalized.startswith("main/java/"):
            return "src/test/java/" + normalized[len("main/java/") :]
        if normalized.startswith("java/"):
            return "src/test/java/" + normalized[len("java/") :]
        return f"src/test/java/{normalized.lstrip('/')}"

    def _build_minimum_smoke_test(self, analysis: AnalysisResult) -> tuple[str, str]:
        package_name = analysis.package_base or "com.example.app"
        package_path = package_name.replace(".", "/")
        path = f"src/test/java/{package_path}/PipelineSmokeTest.java"
        content = (
            f"package {package_name};\n\n"
            "import org.junit.jupiter.api.Test;\n"
            "import static org.assertj.core.api.Assertions.assertThat;\n\n"
            "class PipelineSmokeTest {\n\n"
            "    @Test\n"
            "    void smokeTest_compiles() {\n"
            "        assertThat(true).isTrue();\n"
            "    }\n"
            "}\n"
        )
        return path, content

    def _prepare_test_files_for_execution(
        self,
        generated_code: GeneratedCode,
        test_result: TestResult,
        analysis: AnalysisResult,
        story_scope: Optional[StoryScope] = None,
    ) -> Dict[str, str]:
        combined = self._combine_test_files(generated_code, test_result, story_scope)
        prepared: Dict[str, str] = {}
        included_tests: list[str] = []
        excluded_tests: list[str] = []

        for raw_path, raw_content in combined.items():
            normalized = self._normalize_test_execution_path(raw_path)
            if not normalized.startswith("src/test/java/"):
                logger.warning(f"  Ignoring non-test execution path: {raw_path}")
                continue

            content = raw_content if isinstance(raw_content, str) else str(raw_content or "")
            if not content.strip():
                logger.warning(f"  Ignoring empty generated test file: {normalized}")
                continue

            if story_scope is not None and not self._test_file_matches_story_scope(
                normalized,
                content,
                analysis,
                story_scope,
            ):
                excluded_tests.append(normalized)
                continue

            # Ensure @Timeout import is present before Maven sees the file
            content = self.tester._add_timeouts(content)
            prepared[normalized] = content
            included_tests.append(normalized)

        if not prepared:
            logger.warning(
                "  No valid test files found after path normalization and scope filtering. "
                "StoryScopeSmokeTest/PipelineSmokeTest fallback is disabled. "
                "The zero-tests retry will handle regeneration."
            )

        logger.info(
            "  Included tests: "
            + (", ".join(sorted(included_tests)) if included_tests else "(none)")
        )
        logger.info(
            "  Excluded unrelated tests: "
            + (", ".join(sorted(excluded_tests)) if excluded_tests else "(none)")
        )

        logger.info(
            "  Tests forwarded to Maven: "
            + ", ".join(sorted(prepared.keys()))
        )
        return prepared

    def _load_test_result_from_cache(self, story_id: str) -> Optional[TestResult]:
        report = self.settings.pipeline.artifacts_dir / f"test_report_{story_id}.json"
        output_path = self.settings.pipeline.output_dir / story_id
        if not report.exists() or not output_path.exists():
            return None
        data = json.loads(report.read_text(encoding="utf-8"))
        test_files: Dict[str, str] = {}
        for fp in output_path.rglob("*.java"):
            rel = fp.relative_to(output_path).as_posix()
            if rel.startswith("src/test/"):
                test_files[rel] = fp.read_text(encoding="utf-8")
        return TestResult.from_dict(data, test_files=test_files)
