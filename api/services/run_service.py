"""
Pipeline run orchestration service.

Each run is kicked off as a background asyncio task; the caller gets a run_id
immediately (202 Accepted). Status is tracked in an in-memory registry and falls
back to on-disk artifacts for runs from previous server sessions.

GraphRAG integration
────────────────────
Before delegating to SDLCPipeline.run(), the service:
  1. Resolves the story_id from story_input (Jira ID or raw text).
  2. Pulls the assembled story context from graphrag_service (cached).
  3. Attaches it to the pipeline instance so every agent can consume it via
     pipeline._graphrag_context and pipeline._get_graphrag_snippet(story_id).

This is injected pre-run, not re-fetched per agent, so cost is paid once.
"""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings
from api.services.artifact_service import list_execution_summaries, get_execution_summary
from api.services import run_store, project_target_service
from api.services.event_store import init_run as _init_run_events, record_run_event
from api.services import error_store
from api.services import file_review_service
from api.services.error_extractor import extract_compile_errors, extract_test_errors
from core.events import EventEmitter
from utils.logger import get_logger

logger = get_logger(__name__)

# In-memory registry: run_id → RunRecord
_runs: Dict[str, Dict[str, Any]] = {}

# Pipeline steps that we track as structured run events.
# Order matches the pipeline execution sequence.
_TRACKED_STEPS = [
    "story_loading",
    "graphrag_context",
    "planning",
    "code_generation",
    "compile",
    "test_generation",
    "run_tests",
    "quality_gate",
    "git_push",
]

# Pipeline-internal step name → canonical UI step (matches frontend JURY_PIPELINE_STEPS)
_PIPELINE_TO_CANONICAL: Dict[str, str] = {
    "resolve_user_story": "story_loading",
    "advisor": "planning",
    "planner": "planning",
    "developer": "code_generation",
    "compile": "compile",
    "fixer": "fixer",
    "tester": "test_generation",
    "run_tests": "run_tests",
    "reviewer": "review",
    "quality_gate": "quality_gate",
    "commit": "git_push",
}

# When several pipeline steps share a canonical step, only the terminator
# emits the canonical "success" — earlier siblings keep it at "running"
# to avoid the green→blue→green flicker in the UI.
_CANONICAL_TERMINATORS: Dict[str, str] = {
    "planning": "planner",
}


def _make_pipeline_event_listener(run_id: str):
    """
    Build a listener that translates SDLCPipeline EventEmitter events into
    structured run events scoped to a single run_id.

    Uses per-canonical-step status tracking so a UI step that already turned
    green never regresses to "running" when a sibling pipeline step starts.
    """
    canonical_status: Dict[str, str] = {}

    def on_event(event) -> None:
        if event.event_type not in ("step_started", "step_completed", "step_failed", "step_skipped"):
            return

        pipeline_step = event.step
        canonical = _PIPELINE_TO_CANONICAL.get(pipeline_step)
        if not canonical:
            return  # internal-only steps (load_docs, analyzer, write_files)

        current = canonical_status.get(canonical)
        msg = event.message or ""

        if event.event_type == "step_started":
            if current == "success":
                return
            canonical_status[canonical] = "running"
            record_run_event(run_id, canonical, "running", msg or f"{canonical} started")

        elif event.event_type == "step_completed":
            terminator = _CANONICAL_TERMINATORS.get(canonical)
            # No explicit terminator → 1:1 mapping, any completion turns it green.
            # Explicit terminator → only that pipeline step turns the canonical green.
            if terminator is None or pipeline_step == terminator:
                canonical_status[canonical] = "success"
                record_run_event(run_id, canonical, "success", msg or f"{canonical} completed")

        elif event.event_type == "step_failed":
            canonical_status[canonical] = "failed"
            record_run_event(run_id, canonical, "failed", msg or f"{canonical} failed")

        elif event.event_type == "step_skipped":
            if current != "success":
                canonical_status[canonical] = "skipped"
                record_run_event(run_id, canonical, "skipped", msg or f"{canonical} skipped")

    return on_event


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _story_id_from_input(story_input: str) -> str:
    """Best-effort Jira ID extraction; falls back to a deterministic hash slug."""
    stripped = story_input.strip()
    match = re.match(r'^([A-Z][A-Z0-9]+-\d+)', stripped)
    return match.group(1) if match else f"STORY-{uuid.uuid4().hex[:6].upper()}"


def _persist_record(settings: Settings, record: Dict[str, Any]) -> None:
    run_store.save_run(settings, record)


# ── Public API ────────────────────────────────────────────────────────────────

async def start_run(
    story_input: str,
    settings: Settings,
    repo_path: Optional[str] = None,
    target_project_path: Optional[str] = None,
    dry_run: bool = False,
    resume_from: Optional[str] = None,
    graphrag_path: Optional[str] = None,
) -> str:
    """
    Register a new run and schedule it as a background task.
    Returns run_id immediately.
    """
    run_id = uuid.uuid4().hex[:12]
    story_id = _story_id_from_input(story_input)
    selected_repo_path = str(
        project_target_service.safe_source_repo_path(
            settings,
            target_project_path or repo_path,
        )
    )
    output_directory = str((Path(settings.pipeline.output_dir) / story_id).resolve())

    record: Dict[str, Any] = {
        "run_id": run_id,
        "story_id": story_id,
        "story_title": story_input[:80],
        # story_input preserved verbatim so trigger_commit can compute the same
        # checkpoint key (MD5 of input) that was used during the original run.
        "story_input": story_input,
        "status": "running",
        "started_at": _now_iso(),
        "completed_at": None,
        "steps": [],
        "result": None,
        "error": None,
        "graph_context_injected": False,
        "repo_path": selected_repo_path,
        "output_path": output_directory,
    }
    _runs[run_id] = record
    _persist_record(settings, record)
    _init_run_events(run_id)
    error_store.init_run(run_id)
    # file_review_service is initialised after pipeline generates code

    asyncio.create_task(
        _execute_run(run_id, story_input, story_id, settings,
                     selected_repo_path, dry_run, resume_from, graphrag_path)
    )
    return run_id


# ── Background execution ──────────────────────────────────────────────────────

async def _execute_run(
    run_id: str,
    story_input: str,
    story_id: str,
    settings: Settings,
    repo_path: Optional[str],
    dry_run: bool,
    resume_from: Optional[str],
    graphrag_path: Optional[str],
) -> None:
    record = _runs[run_id]
    try:
        from core.pipeline import SDLCPipeline
        from api.services import graphrag_service

        # Per-run emitter: each pipeline step transition is recorded live as a
        # run event so the frontend timeline turns green progressively.
        run_emitter = EventEmitter()
        run_emitter.subscribe(_make_pipeline_event_listener(run_id))
        pipeline = SDLCPipeline(settings, emitter=run_emitter)
        output_directory = str((Path(settings.pipeline.output_dir) / story_id).resolve())

        logger.info("Target project selected: %s", repo_path)
        logger.info("Output directory: %s", output_directory)

        # ── Step: story_loading ───────────────────────────────────
        record_run_event(run_id, "story_loading", "running", f"Loading user story: {story_input[:80]}")

        # ── GraphRAG injection (priority order) ───────────────────
        record_run_event(run_id, "graphrag_context", "running", "Checking GraphRAG context availability")

        # 1. If caller supplied a path for this run, load it (and update singleton)
        if graphrag_path:
            graphrag_service.load_context(graphrag_path)

        # 2. If any context is now loaded, inject the story-filtered version
        global_ctx = graphrag_service.get_context()
        if global_ctx is not None:
            pipeline._graphrag_context = global_ctx
            record["graph_context_injected"] = True
            _persist_record(settings, record)
            # Pre-warm per-story cache so agents get it instantly
            graphrag_service.get_story_context(story_id)
            record_run_event(
                run_id, "graphrag_context", "success",
                "GraphRAG context injected into pipeline",
                {"story_id": story_id, "context_available": True},
            )
        else:
            record_run_event(
                run_id, "graphrag_context", "skipped",
                "No GraphRAG context loaded — continuing without it",
                {"context_available": False},
            )

        # Mark story loading success (we cannot know before pipeline.run resolves the story)
        record_run_event(run_id, "story_loading", "success", "User story input accepted")

        # ── Pipeline execution ────────────────────────────────────
        # Each step now emits its own running/success/failed event live via
        # the run_emitter listener — no need to pre-stamp "planning=running".
        # files_approved=False on first run: pipeline generates & writes files
        # but skips GitHub push until user reviews them via /files endpoints.
        result = await pipeline.run(
            user_story_input=story_input,
            repo_path=repo_path,
            dry_run=dry_run,
            resume=bool(resume_from),
            resume_from=resume_from,
            files_approved=False,
        )

        # ── Post-run event + error derivation from result steps ──────────────
        _emit_step_events_from_result(run_id, result)
        _extract_and_store_errors(run_id, result, settings)

        # ── Init file review from generated code artifact ─────────────────────
        resolved_story_id = (result.get("user_story") or {}).get("id") or story_id
        _init_file_review(run_id, resolved_story_id, settings)

        record["status"] = "completed" if result.get("all_gates_passed") else "failed"
        result["repo_path"] = repo_path
        record["result"] = result
        record["repo_path"] = repo_path
        record["output_path"] = result.get("output_path") or output_directory
        # Refine story metadata from what the pipeline resolved
        resolved_us = result.get("user_story") or {}
        if resolved_us.get("id"):
            record["story_id"] = resolved_us["id"]
        if resolved_us.get("title"):
            record["story_title"] = resolved_us["title"]
        record["steps"] = _extract_steps(result)
        _persist_record(settings, record)

    except Exception as exc:
        # The listener already recorded the failed step (e.g. compile, fixer, …)
        # via state.mark_failed(); we only emit a top-level pipeline failure here.
        record_run_event(
            run_id, "pipeline", "failed",
            f"Pipeline execution failed: {exc}",
            {"error": str(exc)},
        )
        record["status"] = "failed"
        record["error"] = str(exc)
        summary = get_execution_summary(record["story_id"], settings)
        if summary:
            record["result"] = _result_from_execution_summary(summary)
            record["steps"] = _steps_from_execution_summary(summary)
    finally:
        record["completed_at"] = _now_iso()
        _persist_record(settings, record)


# Step names in pipeline result → our canonical step labels.
# Mirrors _PIPELINE_TO_CANONICAL above; kept as a separate constant because the
# post-run pass enriches events with metrics (coverage, review_score, …) that
# the live listener does not have yet.
_RESULT_STEP_MAP = dict(_PIPELINE_TO_CANONICAL)


def _emit_step_events_from_result(run_id: str, result: Dict[str, Any]) -> None:
    """
    Derive structured run events from the pipeline result's step dict.

    The pipeline already tracks status per step; we translate that into our
    canonical event format so the /events endpoint reflects the real outcome.
    """
    raw_steps: Dict[str, Any] = result.get("steps") or {}
    emitted_canonical: set = set()

    for pipeline_step_name, info in raw_steps.items():
        canonical = _RESULT_STEP_MAP.get(pipeline_step_name, pipeline_step_name)
        if canonical in emitted_canonical:
            continue  # avoid duplicates for steps that map to the same canonical name

        raw_status = info.get("status", "unknown")
        # Translate pipeline step status to our event status vocabulary
        if raw_status in ("completed", "success"):
            status = "success"
        elif raw_status == "failed":
            status = "failed"
        elif raw_status == "skipped":
            status = "skipped"
        else:
            status = "success"  # treat "completed" variants as success

        details: Dict[str, Any] = {}
        if info.get("error"):
            details["error"] = info["error"]
        if info.get("duration_seconds") is not None:
            details["duration_seconds"] = info["duration_seconds"]

        # Enrich quality_gate and git_push with result metrics
        if canonical == "quality_gate":
            all_gates = result.get("all_gates_passed")
            compile_ok = result.get("compile_success", True)
            # A quality gate step that "completed" but failed its evaluation is a failure
            if status == "success" and (all_gates is False or compile_ok is False):
                status = "failed"
            details.update({
                "all_gates_passed": all_gates,
                "compile_success": compile_ok,
                "test_coverage": result.get("test_coverage"),
                "coverage_source": result.get("coverage_source"),
                "review_score": result.get("review_score"),
            })
        elif canonical == "run_tests":
            details.update({
                "test_coverage": result.get("test_coverage"),
                "coverage_source": result.get("coverage_source"),
            })
        elif canonical == "git_push":
            details.update({
                "commit_sha": result.get("commit_sha"),
                "output_path": result.get("output_path"),
            })

        msg = f"Step '{pipeline_step_name}' → {status}"
        if info.get("error"):
            msg += f": {info['error'][:120]}"

        record_run_event(run_id, canonical, status, msg, details)
        emitted_canonical.add(canonical)


def _extract_and_store_errors(
    run_id: str,
    result: Dict[str, Any],
    settings,
) -> None:
    """
    Read compile_report and test_run artifacts from disk and store structured
    error payloads in the error_store for this run.

    Only called after pipeline.run() returns (success or blocked pipeline).
    Does NOT raise — errors here must never crash the run record update.
    """
    from api.services import artifact_service

    story_id = result.get("user_story", {}).get("id") or ""

    # ── Compile errors ────────────────────────────────────────────────────────
    try:
        if not result.get("compile_success", True):
            compile_report = artifact_service.get_compile_report(story_id, settings)
            if compile_report and not compile_report.get("success", True):
                payload = extract_compile_errors(run_id, compile_report)
                error_store.store_compile_error(run_id, payload)
                # Also emit a run event with error details
                record_run_event(
                    run_id, "compile", "failed",
                    payload["summary"],
                    {
                        "error_type": payload["error_type"],
                        "file_count": len(payload["files"]),
                        "files": payload["files"][:5],  # limit for event payload
                    },
                )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("error_extractor compile: %s", exc)

    # ── Test errors ───────────────────────────────────────────────────────────
    try:
        tests_ok = result.get("tests_validation_ok", True)
        if not tests_ok:
            test_run = artifact_service.get_test_run_report(story_id, settings)
            if test_run and not test_run.get("success", True):
                payload = extract_test_errors(run_id, test_run)
                error_store.store_test_error(run_id, payload)
                record_run_event(
                    run_id, "run_tests", "failed",
                    payload["summary"],
                    {
                        "error_type": payload["error_type"],
                        "file_count": len(payload["files"]),
                        "files": payload["files"][:5],
                    },
                )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("error_extractor test: %s", exc)


def _init_file_review(run_id: str, story_id: str, settings: Settings) -> None:
    """Load generated files from artifact into the file review store (idempotent)."""
    try:
        n = file_review_service.load_from_artifact(run_id, story_id, settings)
        if n:
            record_run_event(
                run_id, "git_push", "skipped",
                f"GitHub push blocked — {n} file(s) awaiting review",
                {"files_pending": n, "action_required": "Review and accept all files"},
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("file_review init: %s", exc)


async def trigger_commit(run_id: str, settings: Settings) -> None:
    """
    Re-run the pipeline from the commit step only, after files are approved.
    Uses pipeline resume capability (resume_from="commit").
    """
    record = _runs.get(run_id)
    if not record:
        raise ValueError(f"Run '{run_id}' not found in memory (server may have restarted).")

    # Use the original story_input (preserved verbatim) so the checkpoint key
    # (MD5 of story_input) matches the one created during the initial run.
    # Fallback to story_title for backwards-compat with records created before this fix.
    story_input = record.get("story_input") or record.get("story_title", "")
    story_id    = record.get("story_id", "")
    repo_path   = (record.get("result") or {}).get("repo_path") or record.get("repo_path")
    output_path = record.get("output_path")
    dry_run     = False  # commit trigger is never a dry run

    logger.info(
        "[trigger_commit] run_id=%s story_id=%s story_input=%r output_path=%s",
        run_id, story_id, story_input[:60], output_path,
    )

    record["status"] = "running"
    record_run_event(run_id, "git_push", "running", "Re-triggering GitHub push after file review approval")
    _persist_record(settings, record)

    asyncio.create_task(
        _execute_commit_only(run_id, story_input, story_id, settings, repo_path, dry_run, output_path)
    )


async def _execute_commit_only(
    run_id: str,
    story_input: str,
    story_id: str,
    settings: Settings,
    repo_path: Optional[str],
    dry_run: bool,
    output_path: Optional[str] = None,
) -> None:
    record = _runs[run_id]
    try:
        from core.pipeline import SDLCPipeline
        pipeline = SDLCPipeline(settings)

        # Diagnostic: log checkpoint path before calling pipeline.run
        state_file = pipeline._state_file(story_input)
        checkpoint_exists = state_file.exists()
        logger.info(
            "[commit-only] run_id=%s | checkpoint=%s | exists=%s | output_path=%s",
            run_id, state_file, checkpoint_exists, output_path,
        )
        if not checkpoint_exists:
            logger.warning(
                "[commit-only] Checkpoint missing — will attempt reconstruction from artifacts. "
                "run_id=%s story_id=%s output_path=%s",
                run_id, story_id, output_path,
            )

        result = await pipeline.run(
            user_story_input=story_input,
            repo_path=repo_path,
            dry_run=dry_run,
            resume=True,
            resume_from="commit",
            files_approved=True,  # user has approved all files
            fallback_output_path=output_path,
        )

        commit_sha = result.get("commit_sha")
        if commit_sha:
            record_run_event(
                run_id, "git_push", "success",
                f"GitHub push succeeded — commit {commit_sha}",
                {"commit_sha": commit_sha},
            )
            record["status"] = "completed"
            # Build incremental base snapshot so next run can use this story as base
            try:
                base_path = project_target_service.create_incremental_base(story_id, settings)
                logger.info("Incremental base ready for next run: %s", base_path)
            except Exception as exc:
                logger.warning("Could not prepare incremental base after push: %s", exc)
        else:
            record_run_event(run_id, "git_push", "failed", "Commit step ran but no SHA returned")
            record["status"] = "failed"

        # Merge commit sha into existing result
        existing_result = record.get("result") or {}
        existing_result["commit_sha"] = commit_sha
        existing_result["repo_path"] = repo_path
        record["result"] = existing_result

    except Exception as exc:
        record_run_event(run_id, "git_push", "failed", f"Commit failed: {exc}")
        record["status"] = "failed"
        record["error"] = str(exc)
    finally:
        record["completed_at"] = _now_iso()
        _persist_record(settings, record)


def _extract_steps(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = result.get("steps", {})
    if not raw:
        return []
    return [
        {
            "name": name,
            "status": info.get("status", "unknown"),
            "duration_seconds": info.get("duration_seconds"),
            "error": info.get("error"),
        }
        for name, info in raw.items()
    ]


def _steps_from_execution_summary(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "status": info.get("status", "unknown"),
            "duration_seconds": None,
            "error": info.get("error"),
        }
        for name, info in (summary.get("steps") or {}).items()
    ]


def _result_from_execution_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    validation = summary.get("validation", {})
    return {
        "all_gates_passed": not validation.get("pipeline_blocked", True),
        "compile_success": validation.get("compile_success"),
        "coverage_source": validation.get("coverage_source"),
        "user_story": {
            "id": summary.get("user_story_id"),
            "title": summary.get("user_story_id"),
        },
        "failed_step": summary.get("failed_step"),
        "primary_failure_type": summary.get("primary_failure_type"),
    }


# ── Queries ───────────────────────────────────────────────────────────────────

def get_run(run_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    return _runs.get(run_id) or run_store.get_run(settings, run_id)


def list_runs(settings: Settings) -> List[Dict[str, Any]]:
    """Persistent runs + artifact-backed runs (de-duplicated by run_id / story_id)."""
    persisted_runs = run_store.list_runs(settings)
    by_run_id = {run["run_id"]: run for run in persisted_runs}

    for run_id, live_record in _runs.items():
        by_run_id[run_id] = live_record

    persisted_story_ids = {r["story_id"] for r in by_run_id.values()}

    artifact_runs = []
    for summary in list_execution_summaries(settings):
        sid = summary.get("user_story_id", "")
        if sid in persisted_story_ids:
            continue
        artifact_runs.append({
            "run_id": f"artifact-{sid}",
            "story_id": sid,
            "story_title": sid,
            "status": "completed" if summary.get("final_status") == "succeeded" else "failed",
            "started_at": None,
            "all_gates_passed": summary.get("validation", {}).get("pipeline_blocked") is False,
        })

    memory_runs = [
        {
            "run_id": r["run_id"],
            "story_id": r["story_id"],
            "story_title": r["story_title"],
            "status": r["status"],
            "started_at": r["started_at"],
            "all_gates_passed": (
                (r.get("result") or {}).get("all_gates_passed")
                if r.get("result") is not None
                else r.get("all_gates_passed")
            ),
        }
        for r in by_run_id.values()
    ]
    return memory_runs + artifact_runs


def build_run_summary(run_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    record = get_run(run_id, settings)

    if record:
        result = record.get("result") or {}
        us = result.get("user_story") or {}
        return {
            "run_id": run_id,
            "story_id": record["story_id"],
            "story_title": us.get("title", record["story_title"]),
            "status": record["status"],
            "started_at": record["started_at"],
            "completed_at": record["completed_at"],
            "steps": record["steps"],
            "files_generated": result.get("files_generated", 0),
            "compile_success": result.get("compile_success"),
            "test_coverage": result.get("test_coverage"),
            "coverage_source": result.get("coverage_source"),
            "review_score": result.get("review_score"),
            "all_gates_passed": result.get("all_gates_passed"),
            "output_path": result.get("output_path") or record.get("output_path"),
            "commit_sha": result.get("commit_sha"),
            "error": record.get("error"),
        }

    if run_id.startswith("artifact-"):
        story_id = run_id[len("artifact-"):]
        summary = get_execution_summary(story_id, settings)
        if summary:
            return _summary_from_artifact(run_id, story_id, summary)

    return None


def _summary_from_artifact(run_id: str, story_id: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    validation = summary.get("validation", {})
    steps = [
        {
            "name": k,
            "status": v.get("status", "unknown"),
            "duration_seconds": None,
            "error": v.get("error"),
        }
        for k, v in summary.get("steps", {}).items()
    ]
    return {
        "run_id": run_id,
        "story_id": story_id,
        "story_title": story_id,
        "status": "completed" if summary.get("final_status") == "succeeded" else "failed",
        "started_at": None,
        "completed_at": None,
        "steps": steps,
        "files_generated": 0,
        "compile_success": validation.get("compile_success"),
        "test_coverage": None,
        "coverage_source": validation.get("coverage_source"),
        "review_score": None,
        "all_gates_passed": not validation.get("pipeline_blocked", True),
        "output_path": None,
        "commit_sha": None,
        "error": summary.get("primary_failure_type"),
    }
