"""
Fixer Agent
============
Automatically fixes build, compile, integration, and test errors after
validation. Works in a loop until the project reaches a clean state
(0 compilation errors) or the maximum iteration count is reached.

Fix priority order:
  1. Compilation / build errors  (blocking — must be fixed first)
  2. Broken imports and integration issues
  3. Failing tests
  4. Lint / style issues (non-blocking)

Architecture:
- The FixerAgent does NOT generate code itself.
- It delegates all code corrections to the DeveloperAgent.
- It re-runs the MavenCompiler after each fix cycle.
- It collects all errors before delegating to avoid repeated LLM calls.

Token efficiency:
- Sends only the structured error list + affected file contents, not the
  whole generated codebase.
- Limits the error list to the N most critical errors per cycle.
"""

import os
from typing import List, Optional

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import GeneratedCode, UserStory, AnalysisResult, FixResult
from core.maven_compiler import MavenCompiler, CompileResult, CompileError
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_FIX_ITERATIONS = int(os.getenv("FIXER_MAX_ITERATIONS", "3"))
MAX_ERRORS_PER_CYCLE = int(os.getenv("FIXER_MAX_ERRORS_PER_CYCLE", "10"))


class FixerAgent(BaseAgent):
    """
    Iterative fixer that resolves compilation and test errors.

    Usage:
        fixer = FixerAgent(hf_config, developer_agent, maven_compiler)
        fix_result = await fixer.fix(
            user_story=user_story,
            analysis=analysis,
            generated_code=generated_code,
            compile_result=compile_result,   # initial errors
        )
    """

    def __init__(self, config: HuggingFaceConfig, developer_agent, compiler: MavenCompiler):
        super().__init__(config, "Fixer", model=config.model_fixer)
        self.developer = developer_agent
        self.compiler = compiler
        logger.info(f"   Fixer → modèle: {self.model}")

    async def fix(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        generated_code: GeneratedCode,
        compile_result: CompileResult,
        max_iterations: Optional[int] = None,
    ) -> FixResult:
        """
        Fix all blocking errors iteratively.

        Args:
            user_story:      The user story being implemented.
            analysis:        The AnalysisResult from the Advisor.
            generated_code:  The current GeneratedCode to fix.
            compile_result:  The initial CompileResult with errors.
            max_iterations:  Override for the maximum number of fix loops.

        Returns:
            FixResult with success flag, fixed code, and diagnostics.
        """
        max_iter = max_iterations or MAX_FIX_ITERATIONS
        fixes_applied: List[str] = []
        current_code = generated_code
        current_result = compile_result

        logger.info(
            f"   [Fixer] Starting fix loop — "
            f"initial errors: {current_result.error_count} | max iterations: {max_iter}"
        )

        for iteration in range(1, max_iter + 1):
            if current_result.success:
                logger.info(f"   [Fixer] ✅ Clean after {iteration - 1} iteration(s)")
                return FixResult(
                    success=True,
                    iterations=iteration - 1,
                    fixed_code=current_code,
                    fixes_applied=fixes_applied,
                    remaining_errors=[],
                )

            # Triage errors by severity
            errors = self._triage_errors(current_result.errors)
            logger.info(
                f"   [Fixer] Iteration {iteration}/{max_iter} — "
                f"{len(errors)} error(s) to fix"
            )

            # Describe what is being fixed (for the handoff report)
            error_summary = self._summarize_errors(errors)
            fixes_applied.append(f"Iteration {iteration}: {error_summary}")

            # Delegate correction to the developer agent
            try:
                current_code = await self.developer.fix_compile_errors(
                    user_story=user_story,
                    analysis=analysis,
                    previous_code=current_code,
                    compile_result=current_result,
                )
                logger.info(f"   [Fixer] Developer applied corrections (iteration {iteration})")
            except Exception as e:
                logger.error(f"   [Fixer] Developer correction failed: {e}")
                remaining = [str(e) for e in current_result.errors[:MAX_ERRORS_PER_CYCLE]]
                return FixResult(
                    success=False,
                    iterations=iteration,
                    fixed_code=current_code,
                    fixes_applied=fixes_applied,
                    remaining_errors=remaining,
                )

            # Re-validate after fix
            try:
                current_result = await self.compiler.compile(current_code)
                logger.info(
                    f"   [Fixer] Post-fix compile: "
                    f"{'✅ OK' if current_result.success else f'❌ {current_result.error_count} error(s)'}"
                )
            except Exception as e:
                logger.error(f"   [Fixer] Compilation failed after fix: {e}")
                return FixResult(
                    success=False,
                    iterations=iteration,
                    fixed_code=current_code,
                    fixes_applied=fixes_applied,
                    remaining_errors=[str(e)],
                )

        # Max iterations reached — check final state
        if current_result.success:
            return FixResult(
                success=True,
                iterations=max_iter,
                fixed_code=current_code,
                fixes_applied=fixes_applied,
                remaining_errors=[],
            )

        remaining = [
            f"{e.file}:{e.line} — {e.message}"
            for e in current_result.errors[:MAX_ERRORS_PER_CYCLE]
        ]
        logger.warning(
            f"   [Fixer] ⚠️ Max iterations ({max_iter}) reached with "
            f"{current_result.error_count} error(s) remaining"
        )
        return FixResult(
            success=False,
            iterations=max_iter,
            fixed_code=current_code,
            fixes_applied=fixes_applied,
            remaining_errors=remaining,
        )

    # ──────────────────────────────────────────────────────────────
    #  Error triage
    # ──────────────────────────────────────────────────────────────

    def _triage_errors(self, errors: List[CompileError]) -> List[CompileError]:
        """
        Sort errors by severity for targeted fixing.

        Priority:
          1. Compilation errors (syntax, missing symbols)
          2. Import / package errors
          3. Type mismatch / casting errors
          4. Everything else
        """
        def priority(error: CompileError) -> int:
            msg = error.message.lower()
            if any(k in msg for k in ("cannot find symbol", "package does not exist",
                                       "class not found", "symbol not found")):
                return 0
            if any(k in msg for k in ("error:", "illegal", "incompatible", "expected")):
                return 1
            if any(k in msg for k in ("import", "package")):
                return 2
            return 3

        sorted_errors = sorted(errors, key=priority)
        return sorted_errors[:MAX_ERRORS_PER_CYCLE]

    def _summarize_errors(self, errors: List[CompileError]) -> str:
        """Build a short human-readable summary of errors for the report."""
        if not errors:
            return "no errors"
        by_file: dict = {}
        for e in errors:
            by_file.setdefault(e.file, []).append(e.message[:80])

        parts = []
        for fname, msgs in list(by_file.items())[:5]:
            parts.append(f"{fname}: {msgs[0]}")
        suffix = f" (+{len(errors) - len(parts)} more)" if len(errors) > len(parts) else ""
        return "; ".join(parts) + suffix
