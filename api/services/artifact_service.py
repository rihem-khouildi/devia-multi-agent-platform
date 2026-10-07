"""
Read-only access to pipeline output artifacts stored on disk.
All artifacts live under output/artifacts/ as JSON files.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings


def _artifacts_dir(settings: Settings) -> Path:
    return Path(settings.pipeline.artifacts_dir)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Execution summaries ───────────────────────────────────────────────────────

def list_execution_summaries(settings: Settings) -> List[Dict[str, Any]]:
    """Return all execution_summary_*.json files as a list."""
    artifacts = _artifacts_dir(settings)
    summaries = []
    for p in sorted(artifacts.glob("execution_summary_*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        data = _load_json(p)
        if data:
            summaries.append(data)
    # Also pick up the bare execution_summary.json (legacy / single-run)
    bare = _load_json(artifacts / "execution_summary.json")
    if bare and not any(s.get("user_story_id") == bare.get("user_story_id") for s in summaries):
        summaries.append(bare)
    return summaries


def get_execution_summary(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    artifacts = _artifacts_dir(settings)
    data = _load_json(artifacts / f"execution_summary_{story_id}.json")
    if data:
        return data
    # fallback: bare file if its story_id matches
    bare = _load_json(artifacts / "execution_summary.json")
    if bare and bare.get("user_story_id") == story_id:
        return bare
    return None


def get_quality_report(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    artifacts = _artifacts_dir(settings)
    # Story-specific first, then shared file
    for name in [f"quality_report_{story_id}.json", "quality_report.json"]:
        data = _load_json(artifacts / name)
        if data:
            return data
    return None


def get_generated_files(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    artifacts = _artifacts_dir(settings)
    return _load_json(artifacts / f"generated_code_{story_id}.json")


def get_github_info(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Extract GitHub info from the execution summary."""
    summary = get_execution_summary(story_id, settings)
    if not summary:
        return None
    steps = summary.get("steps", {})
    commit_step = steps.get("commit", {})
    return {
        "commit_sha": commit_step.get("commit_sha"),
        "branch": commit_step.get("branch"),
        "pr_url": commit_step.get("pr_url"),
    }


def get_compile_report(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Return the compile_report artifact (CompileResult.to_dict())."""
    artifacts = _artifacts_dir(settings)
    # The pipeline saves compile_report.json (not story-scoped) — use as-is.
    return _load_json(artifacts / "compile_report.json")


def get_test_run_report(story_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Return the test_run artifact (TestRunResult.to_dict()) for a story."""
    artifacts = _artifacts_dir(settings)
    data = _load_json(artifacts / f"test_run_{story_id}.json")
    if data:
        return data
    # Fallback: latest bare test_run.json (single-run setups)
    return _load_json(artifacts / "test_run.json")


def get_pipeline_logs(story_id: str, settings: Settings) -> List[str]:
    """Return log lines from the pipeline log file (filtered by story_id if present)."""
    log_path = Path(settings.pipeline.logs_dir) / "sdlc.log"
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    # Return last 200 lines (or filter by story_id)
    relevant = [l for l in lines if story_id in l] or lines[-200:]
    return relevant[-200:]
