"""
Modèles de données du pipeline SDLC.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class UserStory:
    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    priority: str
    story_points: Optional[int]
    labels: List[str] = field(default_factory=list)
    epic: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_prompt(self) -> str:
        """Formate la US pour injection dans un prompt LLM."""
        ac = "\n".join(f"  - {c}" for c in self.acceptance_criteria)
        return f"""
USER STORY [{self.id}]: {self.title}
Priority: {self.priority} | Story Points: {self.story_points}
Labels: {', '.join(self.labels)}
Epic: {self.epic or 'N/A'}

Description:
{self.description}

Acceptance Criteria:
{ac}
""".strip()


@dataclass
class EntityField:
    name: str
    type: str
    nullable: bool = True
    unique: bool = False
    description: str = ""


@dataclass
class Entity:
    name: str
    fields: List[EntityField]
    relations: List[Dict[str, str]] = field(default_factory=list)
    business_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": [vars(f) for f in self.fields],
            "relations": self.relations,
            "business_rules": self.business_rules,
        }


@dataclass
class Endpoint:
    method: str          # GET, POST, PUT, DELETE, PATCH
    path: str            # /api/v1/resource/{id}
    description: str
    request_body: Optional[Dict] = None
    response_body: Optional[Dict] = None
    validations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return vars(self)


@dataclass
class GherkinScenario:
    feature: str
    scenario: str
    given: List[str]
    when: List[str]
    then: List[str]

    def to_text(self) -> str:
        given = "\n    ".join(self.given)
        when = "\n    ".join(self.when)
        then = "\n    ".join(self.then)
        return f"""
Feature: {self.feature}

  Scenario: {self.scenario}
    Given {given}
    When {when}
    Then {then}
""".strip()


@dataclass
class AnalysisResult:
    """Résultat de l'agent Implementation Advisor."""
    entities: List[Entity]
    endpoints: List[Endpoint]
    gherkin_scenarios: List[GherkinScenario]
    architecture_notes: str
    package_base: str                      # ex: com.company.project
    service_name: str                      # ex: OrderService
    dependencies: List[str] = field(default_factory=list)
    business_rules: List[str] = field(default_factory=list)
    # Test Contract — extracted from acceptance criteria by ImplementationAdvisor.
    # Each entry is a serialised TestCase dict (see core/test_contract.py).
    test_contract: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "endpoints": [ep.to_dict() for ep in self.endpoints],
            "gherkin_scenarios": [s.to_text() for s in self.gherkin_scenarios],
            "architecture_notes": self.architecture_notes,
            "package_base": self.package_base,
            "service_name": self.service_name,
            "dependencies": self.dependencies,
            "business_rules": self.business_rules,
            "test_contract": self.test_contract,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisResult":
        entities = []
        for entity in data.get("entities", []):
            fields = [
                EntityField(
                    name=f.get("name", "field"),
                    type=f.get("type", "String"),
                    nullable=f.get("nullable", True),
                    unique=f.get("unique", False),
                    description=f.get("description", ""),
                )
                for f in entity.get("fields", [])
            ]
            entities.append(
                Entity(
                    name=entity.get("name", "Entity"),
                    fields=fields,
                    relations=entity.get("relations", []),
                    business_rules=entity.get("business_rules", []),
                )
            )

        endpoints = [
            Endpoint(
                method=ep.get("method", "GET"),
                path=ep.get("path", "/api/v1/resource"),
                description=ep.get("description", ""),
                request_body=ep.get("request_body"),
                response_body=ep.get("response_body"),
                validations=ep.get("validations", []),
            )
            for ep in data.get("endpoints", [])
        ]

        scenarios = []
        for scenario_text in data.get("gherkin_scenarios", []):
            lines = [line.strip() for line in str(scenario_text).splitlines() if line.strip()]
            feature = next((line.replace("Feature:", "").strip() for line in lines if line.startswith("Feature:")), "Feature")
            scenario = next((line.replace("Scenario:", "").strip() for line in lines if line.startswith("Scenario:")), "Scenario")
            given = [line.replace("Given", "").strip() for line in lines if line.startswith("Given")]
            when = [line.replace("When", "").strip() for line in lines if line.startswith("When")]
            then = [line.replace("Then", "").strip() for line in lines if line.startswith("Then")]
            scenarios.append(GherkinScenario(feature=feature, scenario=scenario, given=given, when=when, then=then))

        return cls(
            entities=entities,
            endpoints=endpoints,
            gherkin_scenarios=scenarios,
            architecture_notes=data.get("architecture_notes", ""),
            package_base=data.get("package_base", "com.example.app"),
            service_name=data.get("service_name", "Resource"),
            dependencies=data.get("dependencies", []),
            business_rules=data.get("business_rules", []),
            test_contract=data.get("test_contract", []),
        )


@dataclass
class GeneratedCode:
    """Code Java généré par l'agent Developer."""
    files: Dict[str, str]       # { "src/main/.../Entity.java": "public class..." }
    pom_xml: str                # contenu du pom.xml
    readme: str = ""

    def all_source_files(self) -> Dict[str, str]:
        """Retourne uniquement les fichiers source (non-test)."""
        return {k: v for k, v in self.files.items() if "/test/" not in k}


@dataclass
class TestResult:
    """Résultat de l'agent Tester."""
    coverage: float
    passed: bool
    test_files: Dict[str, str]     # { "src/test/.../EntityTest.java": "..." }
    test_summary: str
    failed_tests: List[str] = field(default_factory=list)
    coverage_details: Dict[str, float] = field(default_factory=dict)
    coverage_source: str = "fallback"
    coverage_gate_mode: str = "degraded"
    generation_mode: str = "initial_full"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "coverage": self.coverage,
            "passed": self.passed,
            "test_summary": self.test_summary,
            "failed_tests": self.failed_tests,
            "coverage_details": self.coverage_details,
            "coverage_source": self.coverage_source,
            "coverage_gate_mode": self.coverage_gate_mode,
            "generation_mode": self.generation_mode,
            "metadata": self.metadata,
            "test_files_count": len(self.test_files),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], test_files: Optional[Dict[str, str]] = None) -> "TestResult":
        return cls(
            coverage=float(data.get("coverage", 0.0)),
            passed=bool(data.get("passed", False)),
            test_files=test_files or {},
            test_summary=data.get("test_summary", ""),
            failed_tests=data.get("failed_tests", []),
            coverage_details=data.get("coverage_details", {}),
            coverage_source=data.get("coverage_source", "fallback"),
            coverage_gate_mode=data.get("coverage_gate_mode", "degraded"),
            generation_mode=data.get("generation_mode", "initial_full"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StoryScope:
    story_id: str
    business_files: List[str] = field(default_factory=list)
    test_targets: List[str] = field(default_factory=list)
    entrypoints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    excluded_files: List[str] = field(default_factory=list)
    new_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    fixer_touched_files: List[str] = field(default_factory=list)
    file_roles: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "business_files": self.business_files,
            "test_targets": self.test_targets,
            "entrypoints": self.entrypoints,
            "dependencies": self.dependencies,
            "excluded_files": self.excluded_files,
            "new_files": self.new_files,
            "modified_files": self.modified_files,
            "fixer_touched_files": self.fixer_touched_files,
            "file_roles": self.file_roles,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryScope":
        return cls(
            story_id=data.get("story_id", ""),
            business_files=data.get("business_files", []) or [],
            test_targets=data.get("test_targets", []) or [],
            entrypoints=data.get("entrypoints", []) or [],
            dependencies=data.get("dependencies", []) or [],
            excluded_files=data.get("excluded_files", []) or [],
            new_files=data.get("new_files", []) or [],
            modified_files=data.get("modified_files", []) or [],
            fixer_touched_files=data.get("fixer_touched_files", []) or [],
            file_roles=data.get("file_roles", {}) or {},
        )


@dataclass
class StoryCoverageReport:
    story_id: str
    line_coverage: Optional[float]
    branch_coverage: Optional[float]
    covered_lines: int = 0
    missed_lines: int = 0
    covered_branches: int = 0
    missed_branches: int = 0
    covered_files: List[str] = field(default_factory=list)
    uncovered_classes: List[Dict[str, Any]] = field(default_factory=list)
    uncovered_methods: List[Dict[str, Any]] = field(default_factory=list)
    scoped_classes: List[Dict[str, Any]] = field(default_factory=list)
    considered_files: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "line_coverage": self.line_coverage,
            "branch_coverage": self.branch_coverage,
            "covered_lines": self.covered_lines,
            "missed_lines": self.missed_lines,
            "covered_branches": self.covered_branches,
            "missed_branches": self.missed_branches,
            "covered_files": self.covered_files,
            "uncovered_classes": self.uncovered_classes,
            "uncovered_methods": self.uncovered_methods,
            "scoped_classes": self.scoped_classes,
            "considered_files": self.considered_files,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryCoverageReport":
        return cls(
            story_id=data.get("story_id", ""),
            line_coverage=data.get("line_coverage"),
            branch_coverage=data.get("branch_coverage"),
            covered_lines=int(data.get("covered_lines", 0) or 0),
            missed_lines=int(data.get("missed_lines", 0) or 0),
            covered_branches=int(data.get("covered_branches", 0) or 0),
            missed_branches=int(data.get("missed_branches", 0) or 0),
            covered_files=data.get("covered_files", []) or [],
            uncovered_classes=data.get("uncovered_classes", []) or [],
            uncovered_methods=data.get("uncovered_methods", []) or [],
            scoped_classes=data.get("scoped_classes", []) or [],
            considered_files=data.get("considered_files", []) or [],
        )


# ─────────────────────────────────────────────
#  New models for the reusable multi-agent pipeline
# ─────────────────────────────────────────────

@dataclass
class RepoAnalysis:
    """
    Output of the RepositoryAnalyzerAgent.
    Describes the structure of the target repository and what is relevant
    for the current user story.
    """
    repo_path: str
    languages: List[str]
    frameworks: List[str]
    build_system: str                      # "maven", "gradle", "npm", etc.
    build_commands: Dict[str, str]         # {"compile": "mvn compile", "test": "mvn test", ...}
    entry_points: List[str]               # key entry-point files
    relevant_files: List[str]             # files directly relevant to the US
    potentially_impacted: List[str]       # files that may be affected by the changes
    existing_patterns: List[str]          # coding patterns found (e.g., "uses @RequiredArgsConstructor")
    change_map: Dict[str, str]            # file_path → reason it must be changed/created
    risks: List[str]
    summary: str                          # short handoff summary for downstream agents

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "build_system": self.build_system,
            "build_commands": self.build_commands,
            "entry_points": self.entry_points,
            "relevant_files": self.relevant_files,
            "potentially_impacted": self.potentially_impacted,
            "existing_patterns": self.existing_patterns,
            "change_map": self.change_map,
            "risks": self.risks,
            "summary": self.summary,
        }


@dataclass
class SubTask:
    """A single unit of work produced by the PlannerAgent."""
    id: str                           # unique id, e.g. "task-1"
    title: str
    description: str
    files_to_edit: List[str]          # existing files to modify
    files_to_create: List[str]        # new files to create
    depends_on: List[str]             # IDs of tasks that must complete first
    agent: str                        # responsible agent: "developer", "tester", etc.
    priority: int                     # 1 = highest priority

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "files_to_edit": self.files_to_edit,
            "files_to_create": self.files_to_create,
            "depends_on": self.depends_on,
            "agent": self.agent,
            "priority": self.priority,
        }


@dataclass
class PlanResult:
    """
    Output of the PlannerAgent.
    Contains the ordered list of subtasks and their parallelization groups.
    """
    subtasks: List[SubTask]
    execution_groups: List[List[str]]  # groups of parallel task IDs, in order
    risks: List[str]
    summary: str                       # short handoff summary

    def to_dict(self) -> dict:
        return {
            "subtasks": [t.to_dict() for t in self.subtasks],
            "execution_groups": self.execution_groups,
            "risks": self.risks,
            "summary": self.summary,
        }


@dataclass
class TestRunResult:
    """
    Result of actually running `mvn test` (real execution, not LLM estimate).
    Populated by MavenBuildRunner.run_tests().
    """
    success: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    skipped_tests: int = 0
    line_coverage: Optional[float] = None    # from JaCoCo, None if not measured
    branch_coverage: Optional[float] = None  # from JaCoCo, None if not measured
    duration_seconds: float = 0.0
    failed_test_names: List[str] = field(default_factory=list)
    coverage_source: str = "fallback"
    jacoco_report_path: Optional[str] = None
    workspace_path: Optional[str] = None
    written_test_files: List[str] = field(default_factory=list)
    effective_pom_has_jacoco: bool = False

    @property
    def coverage(self) -> Optional[float]:
        """Best available real coverage metric."""
        return self.line_coverage

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
            "duration_seconds": self.duration_seconds,
            "failed_test_names": self.failed_test_names,
            "coverage_source": self.coverage_source,
            "jacoco_report_path": self.jacoco_report_path,
            "workspace_path": self.workspace_path,
            "written_test_files": self.written_test_files,
            "effective_pom_has_jacoco": self.effective_pom_has_jacoco,
        }


@dataclass
class PipelineStep:
    """Tracks the state of one pipeline step."""
    name: str
    status: str = "pending"   # pending | running | completed | failed | skipped
    error: Optional[str] = None
    artifact_key: Optional[str] = None   # key in PipelineState.artifacts

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "artifact_key": self.artifact_key,
        }


PIPELINE_STEPS = [
    "resolve_user_story",
    "load_docs",
    "advisor",
    "analyzer",
    "planner",
    "developer",
    "compile",
    "fixer",
    "tester",
    "run_tests",
    "reviewer",
    "write_files",
    "quality_gate",
    "commit",
]


@dataclass
class PipelineState:
    """
    Checkpoint state for the pipeline.
    Persisted to pipeline_state.json after each step so the pipeline can
    resume from any completed step without re-running earlier ones.
    """
    user_story_id: str
    steps: Dict[str, PipelineStep] = field(default_factory=dict)
    # Serialized artifacts (analysis JSON, plan JSON, etc.)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for step_name in PIPELINE_STEPS:
            if step_name not in self.steps:
                self.steps[step_name] = PipelineStep(name=step_name)
        self._emitter = None  # set by SDLCPipeline; not serialized

    def attach_emitter(self, emitter) -> None:
        self._emitter = emitter

    def _emit_step(self, event_type: str, step: str, status: str, message: str) -> None:
        emitter = getattr(self, "_emitter", None)
        if emitter is None:
            return
        try:
            emitter.emit(event_type, step=step, status=status, message=message)
        except Exception:
            pass  # never let event emission break the pipeline

    def mark_running(self, step: str) -> None:
        self.steps[step].status = "running"
        self._emit_step("step_started", step, "running", f"Step '{step}' started")

    def mark_completed(self, step: str, artifact_key: Optional[str] = None) -> None:
        self.steps[step].status = "completed"
        if artifact_key:
            self.steps[step].artifact_key = artifact_key
        self._emit_step("step_completed", step, "success", f"Step '{step}' completed")

    def mark_failed(self, step: str, error: str) -> None:
        self.steps[step].status = "failed"
        self.steps[step].error = error
        self._emit_step("step_failed", step, "failed", str(error))

    def mark_skipped(self, step: str) -> None:
        self.steps[step].status = "skipped"
        self._emit_step("step_skipped", step, "skipped", f"Step '{step}' skipped")

    def is_completed(self, step: str) -> bool:
        return self.steps.get(step, PipelineStep(name=step)).status == "completed"

    def is_failed(self, step: str) -> bool:
        return self.steps.get(step, PipelineStep(name=step)).status == "failed"

    def to_dict(self) -> dict:
        return {
            "user_story_id": self.user_story_id,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineState":
        state = cls(user_story_id=data.get("user_story_id", "unknown"))
        for name, step_data in data.get("steps", {}).items():
            state.steps[name] = PipelineStep(
                name=name,
                status=step_data.get("status", "pending"),
                error=step_data.get("error"),
                artifact_key=step_data.get("artifact_key"),
            )
        state.artifacts = data.get("artifacts", {})
        return state


@dataclass
class FixResult:
    """
    Output of the FixerAgent after one or more fix iterations.
    """
    success: bool                      # True if 0 errors remain after fixing
    iterations: int                    # number of fix iterations performed
    fixed_code: Optional["GeneratedCode"]  # the corrected GeneratedCode
    fixes_applied: List[str]           # human-readable descriptions of fixes
    remaining_errors: List[str]        # errors that could not be fixed

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "iterations": self.iterations,
            "fixes_applied": self.fixes_applied,
            "remaining_errors": self.remaining_errors,
        }
