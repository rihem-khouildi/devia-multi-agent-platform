"""
Repository Analyzer Agent
==========================
Indexes and understands a cloned repository so downstream agents
know exactly which files are relevant for a given user story.

Responsibilities:
- Walk the repo directory tree (deterministic, no LLM).
- Sample key files (entry points, similar existing code).
- Use LLM to identify which files are relevant to the US intent,
  what patterns exist, and what the change map should look like.
- Produce a concise RepoAnalysis handoff for the PlannerAgent.

Token efficiency:
- Never sends the full repository to the LLM.
- Sends only a compact directory tree + selected file snippets (≤ 200 lines each).
- Limits total prompt size via MAX_CHARS budget.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import RepoAnalysis
from utils.logger import get_logger

logger = get_logger(__name__)

# File extensions considered as source code
SOURCE_EXTENSIONS = {
    ".java", ".py", ".kt", ".groovy",
    ".ts", ".js", ".tsx", ".jsx",
    ".go", ".rs", ".cs", ".cpp", ".c",
    ".xml", ".yaml", ".yml", ".json",
    ".properties", ".toml", ".gradle",
}

# Files/dirs to always skip
SKIP_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "__pycache__",
    ".venv", "venv", "target", "build", ".gradle", ".mvn",
    "output", ".tools", "dist", ".eggs",
}
SKIP_FILES = {
    ".gitignore", ".gitattributes", "*.class", "*.jar",
    "*.lock", "package-lock.json",
}

SYSTEM_PROMPT = """
You are a senior software architect. You receive a compact directory tree and selected
file snippets from a cloned repository, together with a user story implementation intent.

Your job:
1. Identify the languages, frameworks, and build system in use.
2. Map the files most relevant to implementing the user story.
3. List files that might be impacted (indirectly).
4. Extract coding patterns already in use (e.g. "uses @RequiredArgsConstructor", "uses JUnit 5 + Mockito").
5. Build a change_map: for each file that needs to be created or modified, explain why.
6. Identify risks and unknowns.
7. Write a short (≤ 5 sentences) handoff summary for the next agent.

RULES:
- Be precise and concise. No hallucinations.
- Only reference files that actually exist in the tree.
- Prefer targeted, incremental changes over large refactors.
- Output ONLY valid JSON matching the schema below. No markdown, no prose.
""".strip()


class RepositoryAnalyzerAgent(BaseAgent):
    """
    Analyzes a repository directory and produces a RepoAnalysis.

    Usage:
        analyzer = RepositoryAnalyzerAgent(hf_config)
        repo_analysis = await analyzer.analyze(
            repo_path="/path/to/cloned/repo",
            us_intent="Short functional description of the user story",
        )
    """

    MAX_TREE_LINES = 400      # max lines in the directory tree sent to LLM
    MAX_SNIPPET_LINES = 150   # max lines per sampled file
    MAX_SNIPPETS = 12         # max number of files sampled
    MAX_PROMPT_CHARS = 28_000 # total LLM prompt budget (characters)

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config, "RepositoryAnalyzer", model=config.model_analyzer)
        logger.info(f"   RepositoryAnalyzer → modèle: {self.model}")

    async def analyze(
        self,
        repo_path: str,
        us_intent: str,
        extra_context: Optional[str] = None,
    ) -> RepoAnalysis:
        """
        Analyze the repository at `repo_path` in the context of `us_intent`.

        Args:
            repo_path:     Absolute or relative path to the cloned repository.
            us_intent:     Short functional summary of what the user story wants to do.
            extra_context: Optional additional context (e.g., tech stack constraints).

        Returns:
            RepoAnalysis with relevant files, change map, patterns, and risks.
        """
        logger.info(f"   Analyzing repository: {repo_path}")
        root = Path(repo_path).resolve()

        if not root.exists():
            raise ValueError(
                f"[RepositoryAnalyzer] Repository path does not exist: {root}\n"
                "Pass a valid --repo-path argument pointing to the cloned repository.\n"
                "The analyzer cannot index a non-existent directory."
            )

        # Step 1: Build compact directory tree (deterministic, no LLM)
        tree_lines = self._build_tree(root)
        tree_text = "\n".join(tree_lines[:self.MAX_TREE_LINES])
        logger.info(f"   Tree: {len(tree_lines)} entries (truncated to {self.MAX_TREE_LINES})")

        # Step 2: Sample key files (heuristic selection)
        snippets = self._sample_key_files(root, us_intent)
        logger.info(f"   Sampled {len(snippets)} key files for LLM context")

        # Step 3: Build LLM prompt
        user_message = self._build_prompt(
            us_intent=us_intent,
            tree_text=tree_text,
            snippets=snippets,
            extra_context=extra_context or "",
        )

        # Step 4: Call LLM
        raw_response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=3000,
            temperature=0.1,
        )

        # Step 5: Parse response
        return self._parse_response(raw_response, str(root))

    # ──────────────────────────────────────────────────────────────
    #  Directory tree builder
    # ──────────────────────────────────────────────────────────────

    def _build_tree(self, root: Path) -> List[str]:
        """Walk the repo and return a compact indented tree."""
        lines: List[str] = [f"{root.name}/"]
        self._walk_tree(root, "", lines)
        return lines

    def _walk_tree(self, directory: Path, prefix: str, lines: List[str]) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        entries = [e for e in entries if e.name not in SKIP_DIRS]
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                self._walk_tree(entry, prefix + extension, lines)

    # ──────────────────────────────────────────────────────────────
    #  Key file sampler
    # ──────────────────────────────────────────────────────────────

    def _sample_key_files(self, root: Path, us_intent: str) -> Dict[str, str]:
        """
        Heuristically select files worth sending to the LLM.

        Priority (in order):
        1. Build files (pom.xml, build.gradle, package.json, requirements.txt)
        2. Entry points (Application.java, main.py, index.ts, etc.)
        3. Files whose names match keywords in the US intent
        4. Existing controllers/services/repositories (architecture samples)
        """
        intent_keywords = {w.lower() for w in us_intent.split() if len(w) > 3}
        candidates: List[tuple[int, Path]] = []  # (priority, path)

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            # Skip irrelevant dirs
            rel_parts = path.relative_to(root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue

            priority = self._score_file(path, root, intent_keywords)
            if priority >= 0:
                candidates.append((priority, path))

        candidates.sort(key=lambda x: x[0])
        selected = candidates[:self.MAX_SNIPPETS]

        snippets: Dict[str, str] = {}
        for _, path in selected:
            rel = path.relative_to(root).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                snippet = "\n".join(lines[:self.MAX_SNIPPET_LINES])
                snippets[rel] = snippet
            except Exception:
                pass

        return snippets

    def _score_file(self, path: Path, root: Path, intent_keywords: set) -> int:
        """
        Lower score = higher priority to send to LLM.
        Returns -1 if the file should be excluded.
        """
        name = path.name.lower()
        rel = path.relative_to(root).as_posix().lower()

        # Build files — top priority
        if name in ("pom.xml", "build.gradle", "build.gradle.kts", "package.json",
                    "requirements.txt", "pyproject.toml", "settings.gradle"):
            return 0

        # Skip non-source files after allowing explicit build files above
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            return -1

        # Entry points
        if name in ("application.java", "main.java", "main.py", "app.py",
                    "index.ts", "index.js", "program.cs"):
            return 1

        # Test directory — lower priority (useful but not critical for analysis)
        if "/test/" in rel or "test" in name:
            return 50

        # Skip compiled / generated artifacts
        if path.suffix in (".class", ".jar", ".pyc"):
            return -1

        # Files whose name matches intent keywords
        name_stem = path.stem.lower()
        if any(kw in name_stem for kw in intent_keywords):
            return 5

        # Architecture samples: controller, service, repository, entity
        if any(t in name_stem for t in ("controller", "service", "repository", "entity", "dto")):
            return 10

        # Config files
        if name in ("application.properties", "application.yml", "application.yaml"):
            return 8

        # Everything else — include but low priority
        return 30

    # ──────────────────────────────────────────────────────────────
    #  Prompt builder
    # ──────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        us_intent: str,
        tree_text: str,
        snippets: Dict[str, str],
        extra_context: str,
    ) -> str:
        schema = json.dumps(self._response_schema(), indent=2)

        snippets_text = ""
        budget = self.MAX_PROMPT_CHARS - len(tree_text) - len(schema) - 2000
        for rel_path, content in snippets.items():
            section = f"\n### FILE: {rel_path}\n```\n{content}\n```\n"
            if len(snippets_text) + len(section) > budget:
                break
            snippets_text += section

        extra = f"\n## ADDITIONAL CONTEXT\n{extra_context}" if extra_context else ""

        return f"""
## USER STORY IMPLEMENTATION INTENT
{us_intent}
{extra}

## REPOSITORY DIRECTORY TREE
```
{tree_text}
```

## KEY FILE SNIPPETS (selected samples)
{snippets_text}

## EXPECTED RESPONSE SCHEMA
Respond with a single JSON object matching this schema exactly:
{schema}
""".strip()

    def _response_schema(self) -> dict:
        return {
            "languages": ["java", "python"],
            "frameworks": ["Spring Boot 3.2", "JUnit 5"],
            "build_system": "maven",
            "build_commands": {
                "compile": "mvn compile",
                "test": "mvn test",
                "package": "mvn package",
                "clean": "mvn clean"
            },
            "entry_points": ["src/main/java/com/example/app/Application.java"],
            "relevant_files": [
                "src/main/java/com/example/app/entity/User.java",
                "src/main/java/com/example/app/service/UserService.java"
            ],
            "potentially_impacted": [
                "src/main/java/com/example/app/controller/UserController.java"
            ],
            "existing_patterns": [
                "uses @RequiredArgsConstructor for dependency injection",
                "uses JUnit 5 + Mockito for tests",
                "uses Jakarta EE (jakarta.*) not javax.*"
            ],
            "change_map": {
                "src/main/java/com/example/app/entity/Order.java": "Create new entity for order management",
                "pom.xml": "Add dependency if needed"
            },
            "risks": [
                "Existing UserService may need to be extended"
            ],
            "summary": "Short handoff summary for the planner agent (≤ 5 sentences)."
        }

    # ──────────────────────────────────────────────────────────────
    #  Response parser
    # ──────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str, repo_path: str) -> RepoAnalysis:
        try:
            data = self.extract_json(raw)
        except (ValueError, Exception) as e:
            logger.warning(f"   Failed to parse analyzer JSON: {e} — using minimal fallback")
            return self._empty_analysis(repo_path)

        return RepoAnalysis(
            repo_path=repo_path,
            languages=data.get("languages", []),
            frameworks=data.get("frameworks", []),
            build_system=data.get("build_system", "maven"),
            build_commands=data.get("build_commands", {"compile": "mvn compile", "test": "mvn test"}),
            entry_points=data.get("entry_points", []),
            relevant_files=data.get("relevant_files", []),
            potentially_impacted=data.get("potentially_impacted", []),
            existing_patterns=data.get("existing_patterns", []),
            change_map=data.get("change_map", {}),
            risks=data.get("risks", []),
            summary=data.get("summary", "Repository analyzed."),
        )

    def _empty_analysis(self, repo_path: str) -> RepoAnalysis:
        """Minimal fallback when repo does not exist or LLM fails."""
        return RepoAnalysis(
            repo_path=repo_path,
            languages=["java"],
            frameworks=["Spring Boot 3.2"],
            build_system="maven",
            build_commands={"compile": "mvn compile", "test": "mvn test", "package": "mvn package"},
            entry_points=[],
            relevant_files=[],
            potentially_impacted=[],
            existing_patterns=[],
            change_map={},
            risks=["Repository path not found or empty — analysis is minimal"],
            summary="Repository could not be analyzed. Proceeding with defaults.",
        )
