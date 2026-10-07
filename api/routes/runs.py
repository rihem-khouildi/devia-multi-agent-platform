from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_settings, get_current_user
from api.schemas.runs import (
    RunRequest, RunSummaryResponse, RunListResponse, RunListItem,
    RunQualityResponse, RunChangesResponse, RunLogsResponse, RunGitHubResponse,
    RunEventsResponse, RunEventItem,
    RunErrorsResponse, RunStepError,
    FilesReviewResponse, FileReviewItem, FileActionResponse, CommitTriggerResponse,
    LLMFixRequest, LLMFixStatusResponse, LLMFixLastResult,
)
from api.services import run_service, artifact_service, event_store, error_store
from api.services import file_review_service, llm_fix_service, project_source_service
from api.services import integration_service
from api.services.error_extractor import extract_compile_errors, extract_test_errors
from config.settings import Settings

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", status_code=202)
async def create_run(
    body: RunRequest,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    # Resolve source project path from source_project_type/name
    target_project_path = body.target_project_path
    if body.source_project_type and body.source_project_type != "default":
        try:
            resolved = project_source_service.get_source_path(
                body.source_project_type, body.source_project_name, settings
            )
            target_project_path = str(resolved)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    # Overlay user integration config on top of server .env defaults
    effective_settings = integration_service.merge_settings(settings, _.get("id", 0))

    run_id = await run_service.start_run(
        story_input=body.story_input,
        settings=effective_settings,
        repo_path=body.repo_path,
        target_project_path=target_project_path,
        dry_run=body.dry_run,
        resume_from=body.resume_from,
        graphrag_path=body.graphrag_path,
    )
    return {"run_id": run_id, "status": "running"}


@router.get("", response_model=RunListResponse)
async def list_runs(
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    runs = run_service.list_runs(settings)
    items = [RunListItem(**r) for r in runs]
    return RunListResponse(runs=items, total=len(items))


@router.get("/{run_id}", response_model=RunSummaryResponse)
async def get_run(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    min_review_score = settings.pipeline.min_review_score
    actual_review_score = summary.get("review_score")
    review_score_ok = (
        actual_review_score is None or actual_review_score >= min_review_score
    )

    quality_gate_reason = None
    if summary.get("all_gates_passed") is False:
        reasons = []
        if actual_review_score is not None and not review_score_ok:
            reasons.append(
                f"review score {actual_review_score}/100 < required {min_review_score}"
            )
        if reasons:
            quality_gate_reason = "; ".join(reasons)

    return RunSummaryResponse(
        **summary,
        required_review_score=min_review_score,
        review_score_ok=review_score_ok,
        quality_gate_reason=quality_gate_reason,
    )


@router.get("/{run_id}/summary", response_model=RunSummaryResponse)
async def get_run_summary(
    run_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    return await get_run(run_id, user, settings)


@router.get("/{run_id}/quality", response_model=RunQualityResponse)
async def get_run_quality(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]
    report = artifact_service.get_quality_report(story_id, settings)
    if not report:
        raise HTTPException(status_code=404, detail="Quality report not available for this run.")

    min_review_score = settings.pipeline.min_review_score
    actual_review_score = summary.get("review_score")
    review_score_ok = (
        actual_review_score is None or actual_review_score >= min_review_score
    )

    gates = dict(report.get("gates", {}))
    gates["review_score"] = review_score_ok

    # passed=true only when all gates (including review score) pass
    base_passed = report.get("passed", False)
    passed = base_passed and review_score_ok

    quality_gate_reason = None
    if not passed:
        reasons = []
        if not base_passed:
            reasons.append("one or more quality gates failed")
        if not review_score_ok:
            reasons.append(
                f"review score {actual_review_score}/100 < required {min_review_score}"
            )
        quality_gate_reason = "; ".join(reasons)

    metrics = dict(report.get("metrics", {}))
    metrics["required_review_score"] = min_review_score
    metrics["actual_review_score"] = actual_review_score
    metrics["review_score_ok"] = review_score_ok

    return RunQualityResponse(
        run_id=run_id,
        passed=passed,
        gates=gates,
        metrics=metrics,
        issues=[i if isinstance(i, dict) else vars(i) for i in report.get("issues", [])],
        quality_gate_reason=quality_gate_reason,
    )


@router.get("/{run_id}/changes", response_model=RunChangesResponse)
async def get_run_changes(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]
    generated = artifact_service.get_generated_files(story_id, settings)
    files = list(generated.get("files", {}).keys()) if generated else []

    return RunChangesResponse(
        run_id=run_id,
        files=files,
        output_path=summary.get("output_path"),
    )


@router.get("/{run_id}/logs", response_model=RunLogsResponse)
async def get_run_logs(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]
    logs = artifact_service.get_pipeline_logs(story_id, settings)
    return RunLogsResponse(run_id=run_id, logs=logs)


@router.get("/{run_id}/github", response_model=RunGitHubResponse)
async def get_run_github(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]
    gh = artifact_service.get_github_info(story_id, settings)

    if not gh or not gh.get("commit_sha"):
        # Surface a clear message when blocked by review score
        actual_review_score = summary.get("review_score")
        min_review_score = settings.pipeline.min_review_score
        all_gates_passed = summary.get("all_gates_passed")
        if (
            all_gates_passed is False
            and actual_review_score is not None
            and actual_review_score < min_review_score
        ):
            block_message = (
                f"GitHub Push blocked by Quality Gate: "
                f"review score {actual_review_score}/100 below required {min_review_score}. "
                f"Set MIN_REVIEW_SCORE={int(actual_review_score)} on Azure to unblock."
            )
        else:
            block_message = None
        return RunGitHubResponse(
            run_id=run_id,
            commit_sha=None,
            branch=None,
            pr_url=None,
            available=False,
            block_reason=block_message,
        )

    return RunGitHubResponse(
        run_id=run_id,
        commit_sha=gh.get("commit_sha"),
        branch=gh.get("branch"),
        pr_url=gh.get("pr_url"),
        available=True,
    )


@router.get("/{run_id}/events", response_model=RunEventsResponse)
async def get_run_events(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Return the structured event log for a run.

    Each event describes one pipeline step transition with its status, a
    human-readable message, and optional detail payload.  Events are ordered
    chronologically (oldest first).

    Returns 404 if the run_id has never been seen by this server process.
    Runs from previous sessions (artifact-backed or SQLite-only) will return
    an empty event list rather than 404 when the run exists in the DB.
    """
    events = event_store.get_run_events(run_id)

    if events is None:
        # run_id completely unknown — check DB/artifacts before giving up
        summary = run_service.build_run_summary(run_id, settings)
        if not summary:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        # Run exists in persistent storage but events are not in memory
        # (server restarted between run creation and this request).
        events = []

    items = [RunEventItem(**e) for e in events]
    return RunEventsResponse(run_id=run_id, events=items, total=len(items))


@router.get("/{run_id}/errors", response_model=RunErrorsResponse)
async def get_run_errors(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Return structured compile and/or test errors for a run.

    Priority:
      1. In-memory error store (live run or same server session).
      2. On-disk artifacts (previous sessions, or when memory was cleared).

    Returns an empty list when the run completed without errors.
    Returns 404 when the run_id is completely unknown.
    """
    # ── 1. Resolve the run and its story_id ──────────────────────────────────
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]

    # ── 2. Try in-memory store first (same session) ───────────────────────────
    in_memory = error_store.get_run_errors(run_id)
    if in_memory is not None:
        items = [RunStepError(**e) for e in in_memory]
        return RunErrorsResponse(run_id=run_id, errors=items, total=len(items))

    # ── 3. Fall back to on-disk artifacts (previous sessions) ─────────────────
    collected: list = []

    compile_report = artifact_service.get_compile_report(story_id, settings)
    if compile_report and not compile_report.get("success", True):
        collected.append(extract_compile_errors(run_id, compile_report))

    test_run = artifact_service.get_test_run_report(story_id, settings)
    if test_run and not test_run.get("success", True):
        collected.append(extract_test_errors(run_id, test_run))

    # ── 4. Review score below threshold ──────────────────────────────────────
    actual_review_score = summary.get("review_score")
    min_review_score = settings.pipeline.min_review_score
    if actual_review_score is not None and actual_review_score < min_review_score:
        collected.append({
            "run_id": run_id,
            "step": "quality_gate",
            "error_type": "review_score_below_threshold",
            "summary": f"Review score below threshold: {actual_review_score} / required {min_review_score}",
            "details": (
                f"The AI reviewer gave a score of {actual_review_score}/100. "
                f"The required minimum is {min_review_score}. "
                "This blocks GitHub Push."
            ),
            "recommended_action": (
                f"Improve generated code quality or set MIN_REVIEW_SCORE={int(actual_review_score)} "
                "in Azure environment variables to lower the threshold for demo."
            ),
        })

    items = [RunStepError(**e) for e in collected]
    return RunErrorsResponse(run_id=run_id, errors=items, total=len(items))


# ── File review endpoints ─────────────────────────────────────────────────────

@router.get("/{run_id}/files", response_model=FilesReviewResponse)
async def get_run_files(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Return the list of generated files for a run with their review status.

    Tries in-memory store first, then falls back to loading from the
    generated_code artifact on disk.  Returns an empty list (not 404) when
    files are not yet available (pipeline still running or not reached
    developer step).
    """
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    story_id = summary["story_id"]
    run_status = summary.get("status", "unknown")

    # Ensure in-memory store is populated (idempotent)
    file_review_service.load_from_artifact(run_id, story_id, settings)

    records = file_review_service.get_files(run_id) or []
    review = file_review_service.review_summary(run_id)

    items = [FileReviewItem(**r) for r in records]
    return FilesReviewResponse(
        run_id=run_id,
        files=items,
        total=review["total"],
        pending=review["pending"],
        accepted=review["accepted"],
        rejected=review["rejected"],
        all_approved=review["all_approved"],
        commit_allowed=review["all_approved"] and run_status != "running",
    )


@router.post("/{run_id}/files/{file_id}/accept", response_model=FileActionResponse)
async def accept_file(
    run_id: str,
    file_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """Mark a generated file as accepted."""
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    # Auto-load from artifact if needed
    file_review_service.load_from_artifact(run_id, summary["story_id"], settings)

    updated = file_review_service.accept_file(run_id, file_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found in run '{run_id}'.")

    all_approved = file_review_service.is_all_approved(run_id)
    return FileActionResponse(
        run_id=run_id,
        file_id=file_id,
        status="accepted",
        all_approved=all_approved,
        message="File accepted." + (" All files approved — commit allowed." if all_approved else ""),
    )


@router.post("/{run_id}/files/{file_id}/reject", response_model=FileActionResponse)
async def reject_file(
    run_id: str,
    file_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """Mark a generated file as rejected — blocks GitHub push."""
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    file_review_service.load_from_artifact(run_id, summary["story_id"], settings)

    updated = file_review_service.reject_file(run_id, file_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found in run '{run_id}'.")

    return FileActionResponse(
        run_id=run_id,
        file_id=file_id,
        status="rejected",
        all_approved=False,
        message="File rejected. GitHub push is blocked until all files are accepted.",
    )


@router.post("/{run_id}/files/{file_id}/reset", response_model=FileActionResponse)
async def reset_file(
    run_id: str,
    file_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """Reset a file review decision back to pending."""
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    file_review_service.load_from_artifact(run_id, summary["story_id"], settings)

    updated = file_review_service.reset_file(run_id, file_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found in run '{run_id}'.")

    return FileActionResponse(
        run_id=run_id,
        file_id=file_id,
        status="pending",
        all_approved=False,
        message="File reset to pending.",
    )


@router.post("/{run_id}/commit", response_model=CommitTriggerResponse)
async def trigger_commit(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Trigger the GitHub commit/push step for a run that has:
      - passed all quality gates (all_gates_passed)
      - had all generated files accepted by the reviewer

    Returns 400 if conditions are not met.
    """
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    run_status = summary.get("status", "unknown")
    if run_status == "running":
        raise HTTPException(status_code=409, detail="Run is still executing.")

    all_approved = file_review_service.is_all_approved(run_id)
    if not all_approved:
        review = file_review_service.review_summary(run_id)
        return CommitTriggerResponse(
            run_id=run_id,
            status="blocked",
            message=(
                f"GitHub push blocked: {review['pending']} file(s) pending, "
                f"{review['rejected']} file(s) rejected. "
                "Accept all files before committing."
            ),
            all_approved=False,
        )

    # Re-run the commit step via run_service
    try:
        await run_service.trigger_commit(run_id, settings)
        return CommitTriggerResponse(
            run_id=run_id,
            status="triggered",
            message="Commit triggered. Check run status for result.",
            all_approved=True,
        )
    except Exception as exc:
        return CommitTriggerResponse(
            run_id=run_id,
            status="error",
            message=str(exc),
            all_approved=True,
        )


# ── LLM Fix endpoints ─────────────────────────────────────────────────────────

@router.post("/{run_id}/llm-fix", status_code=202)
async def trigger_llm_fix(
    run_id: str,
    body: LLMFixRequest,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Launch an LLM-driven fix for compile or test errors.

    The fix runs in the background.  Poll GET /runs/{run_id}/llm-fix/status
    for progress.  No GitHub push is triggered at any point.
    """
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if summary.get("status") == "running":
        raise HTTPException(status_code=409, detail="Pipeline is still running — wait for it to finish.")

    current = llm_fix_service.get_status(run_id)
    if current and current.get("status") == "running":
        raise HTTPException(status_code=409, detail="An LLM fix is already in progress for this run.")

    valid_targets = ("compile", "run_tests", "both")
    if body.target not in valid_targets:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid target '{body.target}'. Must be one of: {valid_targets}",
        )

    await llm_fix_service.launch_fix(run_id, body.target, settings)
    return {"status": "started", "message": "LLM fix launched", "target": body.target}


@router.get("/{run_id}/llm-fix/status", response_model=LLMFixStatusResponse)
async def get_llm_fix_status(
    run_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """Return the current LLM fix status for a run."""
    summary = run_service.build_run_summary(run_id, settings)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    llm_fix_service.init_status(run_id, settings)  # idempotent; loads from disk on restart
    status_record = llm_fix_service.get_status(run_id, settings)

    last = status_record.get("last_result")
    last_result = LLMFixLastResult(**last) if last else None

    return LLMFixStatusResponse(
        run_id=run_id,
        status=status_record["status"],
        message=status_record["message"],
        patched_files=status_record.get("patched_files") or [],
        last_result=last_result,
        started_at=status_record.get("started_at"),
        completed_at=status_record.get("completed_at"),
    )
