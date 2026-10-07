from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class RunRequest(BaseModel):
    story_input: str          # Jira ID (e.g. "SCRUM-7") or raw story text
    repo_path: Optional[str] = None
    target_project_path: Optional[str] = None
    dry_run: bool = False
    resume_from: Optional[str] = None
    graphrag_path: Optional[str] = None
    # Project source selection (Part 2)
    source_project_type: Optional[str] = None   # "default" | "uploaded"
    source_project_name: Optional[str] = None   # required when type="uploaded"


class StepStatus(BaseModel):
    name: str
    status: str               # pending | running | completed | failed | skipped
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class RunSummaryResponse(BaseModel):
    run_id: str
    story_id: str
    story_title: str
    status: str               # running | completed | failed
    started_at: Optional[str]
    completed_at: Optional[str]
    steps: List[StepStatus]
    files_generated: int
    compile_success: Optional[bool]
    test_coverage: Optional[float]
    coverage_source: Optional[str]
    review_score: Optional[int]
    required_review_score: Optional[float] = None
    review_score_ok: Optional[bool] = None
    quality_gate_reason: Optional[str] = None
    all_gates_passed: Optional[bool]
    output_path: Optional[str]
    commit_sha: Optional[str]
    error: Optional[str]


class RunQualityResponse(BaseModel):
    run_id: str
    passed: bool
    gates: Dict[str, bool]
    metrics: Dict[str, Any]
    issues: List[Dict[str, Any]]
    quality_gate_reason: Optional[str] = None


class RunChangesResponse(BaseModel):
    run_id: str
    files: List[str]
    output_path: Optional[str]


class RunLogsResponse(BaseModel):
    run_id: str
    logs: List[str]


class RunGitHubResponse(BaseModel):
    run_id: str
    commit_sha: Optional[str]
    branch: Optional[str]
    pr_url: Optional[str]
    available: bool
    block_reason: Optional[str] = None


class RunListItem(BaseModel):
    run_id: str
    story_id: str
    story_title: str
    status: str
    started_at: Optional[str]
    all_gates_passed: Optional[bool]


class RunListResponse(BaseModel):
    runs: List[RunListItem]
    total: int


class RunEventItem(BaseModel):
    id: str
    run_id: str
    step: str
    status: str          # running | success | failed | skipped
    message: str
    details: Dict[str, Any]
    created_at: str


class RunEventsResponse(BaseModel):
    run_id: str
    events: List[RunEventItem]
    total: int


class ErrorFileEntry(BaseModel):
    path: str
    line: int
    message: str


class RunStepError(BaseModel):
    run_id: str
    step: str                             # "compile" | "run_tests" | "quality_gate"
    error_type: str                       # canonical failure_type
    summary: str                          # one-sentence human description
    details: Optional[str] = None        # additional context
    copyable_error: Optional[str] = None
    files: Optional[List[ErrorFileEntry]] = None
    raw_excerpt: Optional[str] = None
    recommended_action: Optional[str] = None
    timeout_details: Optional[Dict[str, Any]] = None


class RunErrorsResponse(BaseModel):
    run_id: str
    errors: List[RunStepError]
    total: int


class FileReviewItem(BaseModel):
    id: str
    path: str
    content: str
    status: str       # pending | accepted | rejected
    language: str     # java | xml | yaml | text | …


class FilesReviewResponse(BaseModel):
    run_id: str
    files: List[FileReviewItem]
    total: int
    pending: int
    accepted: int
    rejected: int
    all_approved: bool
    commit_allowed: bool  # True when all_approved and run status is not "running"


class FileActionResponse(BaseModel):
    run_id: str
    file_id: str
    status: str       # new status after action
    all_approved: bool
    message: str


class CommitTriggerResponse(BaseModel):
    run_id: str
    status: str       # "triggered" | "blocked" | "error"
    message: str
    all_approved: bool


# ── LLM Fix schemas ───────────────────────────────────────────────────────────

class LLMFixRequest(BaseModel):
    mode: str = "auto"
    target: str = "both"   # "compile" | "run_tests" | "both"


class LLMFixLastResult(BaseModel):
    compile_ok: Optional[bool] = None
    tests_ok: Optional[bool] = None
    test_coverage: Optional[float] = None
    failed_tests: Optional[List[str]] = None
    compile_errors: Optional[List[Dict[str, Any]]] = None


class LLMFixStatusResponse(BaseModel):
    run_id: str
    status: str            # idle | running | success | failed
    message: str
    patched_files: List[str]
    last_result: Optional[LLMFixLastResult]
    started_at: Optional[str]
    completed_at: Optional[str]
