"""
Planner / Orchestrator Agent
==============================
Receives the implementation intent (from the Advisor) and the repository
analysis (from the Analyzer), then decomposes the work into small, scoped
subtasks that can be executed by downstream agents.

Responsibilities:
- Break the work into subtasks, each limited to a small set of files.
- Identify which subtasks can run in parallel and which must be sequential.
- Assign the responsible agent to each subtask.
- Prevent scope overlap between parallel subtasks.
- Output a PlanResult with ordered execution groups.

Token efficiency:
- Receives only the us_intent summary + repo_analysis summary (not full code).
- Sends a focused prompt without re-loading repository context.
"""

import json
import os
import re
from typing import Optional

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import RepoAnalysis, PlanResult, SubTask
from utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
You are a senior software engineering tech lead and project planner.

You receive:
1. A user story implementation intent (what must be built).
2. A repository analysis summary (what already exists, what files are relevant).
3. A GraphRAG context (AUTHORITATIVE scope — the exact files, classes, modules allowed).

Your job:
- Decompose the implementation into small, focused subtasks.
- Each subtask must be limited to a small set of files (≤ 5 files).
- Assign the correct agent to each subtask: "developer", "tester", or "reviewer".
- Group subtasks that can run in PARALLEL (no shared files, no dependencies).
- Order execution groups so sequential dependencies are respected.
- Identify risks for the implementation plan.

STRICT SCOPE RULES — READ CAREFULLY:
- When a GRAPHRAG CONTEXT section is provided, it is the ONLY authoritative source of
  allowed files, classes, modules and services. You MUST NOT plan anything outside it.
- NEVER add pom.xml, build files, dependency files, or Maven configuration files.
- NEVER add authentication, security, OAuth, JWT, or access-control resources unless
  they are EXPLICITLY named in the user story acceptance criteria.
- NEVER add infrastructure files (application.properties, Dockerfile, CI scripts).
- NEVER add generic cross-cutting classes (GlobalExceptionHandler, OpenApiConfig)
  unless they are explicitly listed in GraphRAG or in the acceptance criteria.
- Do NOT overlap files across parallel subtasks (causes merge conflicts).
- Keep each subtask description concise and actionable.
- Prefer incremental changes (create/edit one layer at a time).
- Plan only the files and endpoints strictly required by the acceptance criteria.
- Do not invent generic CRUD work unless the user story explicitly requires CRUD.
- Output ONLY valid JSON matching the schema. No markdown, no prose.
""".strip()


class PlannerAgent(BaseAgent):
    """
    Decomposes a user story into ordered, parallel-safe subtasks.

    Usage:
        planner = PlannerAgent(hf_config)
        plan = await planner.plan(
            us_intent="...",
            repo_analysis=repo_analysis,
        )
    """

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config, "Planner", model=config.model_planner)
        logger.info(f"   Planner → modèle: {self.model}")

    async def plan(
        self,
        us_intent: str,
        repo_analysis: RepoAnalysis,
        extra_context: Optional[str] = None,
        graphrag_snippet: Optional[str] = None,
    ) -> PlanResult:
        """
        Decompose the user story into subtasks.

        Args:
            us_intent:       Short functional summary from the ImplementationAdvisor.
            repo_analysis:   Output from the RepositoryAnalyzerAgent.
            extra_context:   Optional additional constraints.
            graphrag_snippet: Authoritative scope from GraphRAG (files/classes allowed).

        Returns:
            PlanResult with ordered execution groups of subtasks.
        """
        logger.info("   Planning task decomposition...")
        user_message = self._build_prompt(us_intent, repo_analysis, extra_context or "", graphrag_snippet or "")

        # Use a lower token budget and planner-specific timeout to fail fast on slow providers.
        # LLM_PLANNER_TIMEOUT_SECONDS overrides the global LLM_REQUEST_TIMEOUT_SECONDS.
        planner_timeout = int(os.getenv("LLM_PLANNER_TIMEOUT_SECONDS",
                                        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "45")))
        original_timeout = os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS")
        os.environ["LLM_REQUEST_TIMEOUT_SECONDS"] = str(planner_timeout)
        logger.info(f"   Planner timeout: {planner_timeout}s")

        try:
            raw_response = await self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=2000,
                temperature=0.1,
            )
        finally:
            if original_timeout is None:
                os.environ.pop("LLM_REQUEST_TIMEOUT_SECONDS", None)
            else:
                os.environ["LLM_REQUEST_TIMEOUT_SECONDS"] = original_timeout

        plan = self._parse_response(raw_response)
        specialized = self._specialized_status_lookup_plan(us_intent, repo_analysis)
        if specialized is not None:
            logger.info("   → Deterministic planner override applied for status lookup story")
            plan = specialized
        logger.info(
            f"   Plan: {len(plan.subtasks)} subtasks in "
            f"{len(plan.execution_groups)} execution group(s)"
        )
        for i, group in enumerate(plan.execution_groups):
            logger.info(f"     Group {i + 1}: {group}")
        return plan

    # ──────────────────────────────────────────────────────────────
    #  Prompt builder
    # ──────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        us_intent: str,
        repo_analysis: RepoAnalysis,
        extra_context: str,
        graphrag_snippet: str = "",
    ) -> str:
        schema = json.dumps(self._response_schema(), indent=2)

        # Compact repo summary — never send full file contents
        change_map_text = "\n".join(
            f"  - {path}: {reason}"
            for path, reason in list(repo_analysis.change_map.items())[:20]
        )
        relevant_text = "\n".join(f"  - {f}" for f in repo_analysis.relevant_files[:20])
        patterns_text = "\n".join(f"  - {p}" for p in repo_analysis.existing_patterns[:10])
        risks_text = "\n".join(f"  - {r}" for r in repo_analysis.risks[:8])

        extra = f"\n## ADDITIONAL CONSTRAINTS\n{extra_context}" if extra_context else ""

        # GraphRAG section — hard scope boundary for the planner
        graphrag_section = ""
        if graphrag_snippet:
            graphrag_section = f"""
## GRAPHRAG CONTEXT — AUTHORITATIVE SCOPE BOUNDARY
The following is the ONLY scope allowed for this story.
You MUST limit files_to_create and files_to_edit strictly to resources
derived from the entities, files, and modules listed below.
DO NOT plan pom.xml, authentication, security, or any resource not listed here.

{graphrag_snippet}

REMINDER: Any file or class NOT derivable from the above GraphRAG context
is OUT OF SCOPE and must NOT appear in your plan.
"""

        return f"""
## USER STORY IMPLEMENTATION INTENT
{us_intent}
{graphrag_section}
## REPOSITORY SUMMARY
- Build system: {repo_analysis.build_system}
- Languages: {', '.join(repo_analysis.languages)}
- Frameworks: {', '.join(repo_analysis.frameworks)}
- Compile command: {repo_analysis.build_commands.get('compile', 'mvn compile')}
- Test command: {repo_analysis.build_commands.get('test', 'mvn test')}

### Relevant files
{relevant_text or '  (none identified)'}

### Required changes (change map)
{change_map_text or '  (not specified — use your judgment)'}

### Existing coding patterns
{patterns_text or '  (not identified)'}

### Known risks
{risks_text or '  (none)'}
{extra}

## EXPECTED RESPONSE SCHEMA
Respond with a single JSON object matching this schema exactly:
{schema}
""".strip()

    def _response_schema(self) -> dict:
        return {
            "subtasks": [
                {
                    "id": "task-1",
                    "title": "Create Order entity",
                    "description": "Create the JPA entity class for Order with all required fields.",
                    "files_to_edit": [],
                    "files_to_create": [
                        "src/main/java/com/example/app/entity/Order.java"
                    ],
                    "depends_on": [],
                    "agent": "developer",
                    "priority": 1
                },
                {
                    "id": "task-2",
                    "title": "Create OrderRepository",
                    "description": "Create the Spring Data JPA repository for Order.",
                    "files_to_edit": [],
                    "files_to_create": [
                        "src/main/java/com/example/app/repository/OrderRepository.java"
                    ],
                    "depends_on": ["task-1"],
                    "agent": "developer",
                    "priority": 2
                },
                {
                    "id": "task-3",
                    "title": "Create OrderService",
                    "description": "Implement the business logic service for Order.",
                    "files_to_edit": [],
                    "files_to_create": [
                        "src/main/java/com/example/app/service/OrderService.java"
                    ],
                    "depends_on": ["task-1", "task-2"],
                    "agent": "developer",
                    "priority": 3
                },
                {
                    "id": "task-4",
                    "title": "Create OrderController",
                    "description": "Expose REST endpoints for Order management.",
                    "files_to_edit": [],
                    "files_to_create": [
                        "src/main/java/com/example/app/controller/OrderController.java",
                        "src/main/java/com/example/app/dto/OrderRequest.java",
                        "src/main/java/com/example/app/dto/OrderResponse.java"
                    ],
                    "depends_on": ["task-3"],
                    "agent": "developer",
                    "priority": 4
                },
                {
                    "id": "task-5",
                    "title": "Write tests",
                    "description": "Write JUnit 5 + Mockito tests for OrderService and OrderController.",
                    "files_to_edit": [],
                    "files_to_create": [
                        "src/test/java/com/example/app/service/OrderServiceTest.java",
                        "src/test/java/com/example/app/controller/OrderControllerTest.java"
                    ],
                    "depends_on": ["task-4"],
                    "agent": "tester",
                    "priority": 5
                }
            ],
            "execution_groups": [
                ["task-1"],
                ["task-2"],
                ["task-3"],
                ["task-4"],
                ["task-5"]
            ],
            "risks": [
                "Order entity may need relations to existing User entity"
            ],
            "summary": "Short handoff summary for the developer agent (≤ 5 sentences)."
        }

    # ──────────────────────────────────────────────────────────────
    #  Response parser
    # ──────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> PlanResult:
        try:
            data = self.extract_json(raw)
        except (ValueError, Exception) as e:
            logger.warning(f"   Failed to parse planner JSON: {e} — using minimal fallback plan")
            return self._fallback_plan()

        subtasks = []
        for t in data.get("subtasks", []):
            subtasks.append(SubTask(
                id=t.get("id", "task-1"),
                title=t.get("title", "Unnamed task"),
                description=t.get("description", ""),
                files_to_edit=t.get("files_to_edit", []),
                files_to_create=t.get("files_to_create", []),
                depends_on=t.get("depends_on", []),
                agent=t.get("agent", "developer"),
                priority=int(t.get("priority", 99)),
            ))

        # Sort subtasks by priority for deterministic ordering
        subtasks.sort(key=lambda t: t.priority)

        execution_groups = data.get("execution_groups", [[t.id] for t in subtasks])

        return PlanResult(
            subtasks=subtasks,
            execution_groups=execution_groups,
            risks=data.get("risks", []),
            summary=data.get("summary", "Plan generated."),
        )

    def _fallback_plan(self) -> PlanResult:
        """Minimal single-task plan when LLM fails."""
        task = SubTask(
            id="task-1",
            title="Implement user story",
            description="Implement all required changes for the user story.",
            files_to_edit=[],
            files_to_create=[],
            depends_on=[],
            agent="developer",
            priority=1,
        )
        return PlanResult(
            subtasks=[task],
            execution_groups=[["task-1"]],
            risks=["Plan could not be generated — using single-task fallback"],
            summary="Fallback plan: single task delegated to developer agent.",
        )

    def _specialized_status_lookup_plan(
        self,
        us_intent: str,
        repo_analysis: RepoAnalysis,
    ) -> Optional[PlanResult]:
        text = " ".join(
            [
                us_intent.lower(),
                repo_analysis.summary.lower(),
                " ".join(repo_analysis.relevant_files).lower(),
                " ".join(repo_analysis.change_map.keys()).lower(),
            ]
        )
        if "status" not in text:
            return None
        if not any(term in text for term in ("application", "applications", "candidature", "candidatures")):
            return None
        if any(term in text for term in (" post ", " put ", " delete ", " patch ", " create ", " update ")):
            return None

        subtasks = [
            SubTask(
                id="task-1",
                title="Align Application Repository",
                description="Ensure the application repository supports the status lookup flow and any targeted query needed by the user story.",
                files_to_edit=["src/main/java/com/example/app/repository/ApplicationRepository.java"],
                files_to_create=[],
                depends_on=[],
                agent="developer",
                priority=1,
            ),
            SubTask(
                id="task-2",
                title="Implement Application Status Service",
                description="Implement only the application status lookup logic required by the acceptance criteria.",
                files_to_edit=[
                    "src/main/java/com/example/app/service/ApplicationService.java",
                    "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java",
                ],
                files_to_create=[],
                depends_on=["task-1"],
                agent="developer",
                priority=2,
            ),
            SubTask(
                id="task-3",
                title="Expose Application Status Endpoint",
                description="Expose a GET endpoint dedicated to consulting the status of an application.",
                files_to_edit=[
                    "src/main/java/com/example/app/controller/ApplicationController.java",
                    "src/main/java/com/example/app/dto/ApplicationResponse.java",
                    "src/main/java/com/example/app/dto/ApplicationRequest.java",
                ],
                files_to_create=[],
                depends_on=["task-2"],
                agent="developer",
                priority=3,
            ),
            SubTask(
                id="task-4",
                title="Test Status Endpoint",
                description="Add tests that cover the application status consultation flow only.",
                files_to_edit=[],
                files_to_create=[
                    "src/test/java/com/example/app/controller/ApplicationControllerTest.java",
                    "src/test/java/com/example/app/service/ApplicationServiceImplTest.java",
                ],
                depends_on=["task-3"],
                agent="tester",
                priority=4,
            ),
        ]
        return PlanResult(
            subtasks=subtasks,
            execution_groups=[["task-1"], ["task-2"], ["task-3"], ["task-4"]],
            risks=["The base repository may still contain broader CRUD artifacts that must not leak into this story."],
            summary="Deterministic plan for an application status lookup story.",
        )
