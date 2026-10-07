import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_settings
from api.services import project_target_service, artifact_service
from config.settings import Settings

router = APIRouter(prefix="/projects", tags=["projects"])

# In-memory store for async validation jobs
_validation_jobs: dict = {}


def _build_project(settings: Settings) -> dict:
    output = Path(settings.pipeline.output_dir)
    return {
        "id": "current",
        "name": settings.jira.project_key or "SDLC Project",
        "jira_project_key": settings.jira.project_key,
        "github_repo": f"{settings.github.owner}/{settings.github.repo}" if settings.github.repo else None,
        "output_dir": str(output.resolve()),
        "artifacts_dir": str(Path(settings.pipeline.artifacts_dir).resolve()),
    }


def _list_generated_projects(settings: Settings) -> list:
    # settings.pipeline.output_dir is already output/generated (e.g. /app/output/generated)
    generated_dir = Path(settings.pipeline.output_dir).resolve()

    if not generated_dir.exists():
        return []

    projects = []
    for entry in sorted(generated_dir.iterdir()):
        if not entry.is_dir():
            continue

        stat = entry.stat()
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        runs_count = sum(1 for _ in entry.iterdir() if _.is_dir() or _.suffix == ".json")

        # relative_path: output/generated/<name>  (2 levels up from generated_dir)
        # generated_dir = /app/output/generated  → parents[1] = /app
        try:
            relative_path = str(entry.relative_to(generated_dir.parents[1]))
        except ValueError:
            relative_path = f"output/generated/{entry.name}"

        github_info = artifact_service.get_github_info(entry.name, settings) or {}
        github_pushed = bool(github_info.get("commit_sha"))

        # Incremental base snapshot (output/bases/{story_id}/) — ready as repo_path
        incremental_base = project_target_service.get_incremental_base_path(entry.name, settings)

        projects.append({
            "name": entry.name,
            "path": str(entry),           # absolute path to output/generated/{name}
            "base_path": str(incremental_base) if incremental_base else None,
            "relative_path": relative_path,
            "updated_at": updated_at,
            "runs_count": runs_count,
            "github_pushed": github_pushed,
            "commit_sha": github_info.get("commit_sha"),
            "branch": github_info.get("branch"),
            "pr_url": github_info.get("pr_url"),
        })

    return projects


@router.get("")
async def list_projects(settings: Settings = Depends(get_settings)):
    """Return the configured project metadata (Jira key, GitHub repo, paths)."""
    project = _build_project(settings)
    return {"projects": [project], "total": 1}


@router.get("/current")
async def current_project(settings: Settings = Depends(get_settings)):
    return _build_project(settings)


@router.get("/target")
async def get_target_project(settings: Settings = Depends(get_settings)):
    return project_target_service.get_target_project(settings)


@router.post("/target/validate")
async def validate_target_project(settings: Settings = Depends(get_settings)):
    job_id = str(uuid.uuid4())
    _validation_jobs[job_id] = {"status": "running", "result": None}

    async def _run():
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, project_target_service.validate_target_project, settings
            )
            _validation_jobs[job_id] = {"status": "done", "result": result}
        except Exception as exc:
            _validation_jobs[job_id] = {"status": "error", "result": {"error": str(exc)}}

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "running"}


@router.get("/target/validate/{job_id}")
async def get_validation_job(job_id: str):
    job = _validation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Validation job not found.")
    return job


@router.get("/generated")
async def list_generated_projects(settings: Settings = Depends(get_settings)):
    """List real project folders found inside output/generated, enriched with GitHub push status."""
    projects = _list_generated_projects(settings)
    base = project_target_service.get_target_project(settings)
    base_project = {
        "name": base.get("name", "Base Spring Boot Project"),
        "path": base.get("path", str(settings.pipeline.target_repo_path)),
        "is_base": True,
        "github_pushed": False,
        "commit_sha": None,
        "branch": None,
        "pr_url": None,
    }
    return {"base_project": base_project, "projects": projects, "total": len(projects)}


def _build_tree(path: Path, root: Path) -> dict:
    node: dict = {"name": path.name, "path": str(path.relative_to(root))}
    if path.is_dir():
        node["type"] = "directory"
        node["children"] = sorted(
            [_build_tree(child, root) for child in path.iterdir()],
            key=lambda n: (0 if n["type"] == "directory" else 1, n["name"].lower()),
        )
    else:
        node["type"] = "file"
    return node


@router.get("/generated/{project_name}/tree")
async def get_project_tree(project_name: str, settings: Settings = Depends(get_settings)):
    """Return recursive directory/file tree for a generated project."""
    # Guard against path traversal
    if ".." in project_name or "/" in project_name or "\\" in project_name:
        raise HTTPException(status_code=400, detail="Invalid project name.")

    generated_dir = Path(settings.pipeline.output_dir).resolve()
    project_path = (generated_dir / project_name).resolve()

    # Ensure the resolved path is inside generated_dir
    try:
        project_path.relative_to(generated_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project path.")

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found.")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"'{project_name}' is not a directory.")

    return _build_tree(project_path, generated_dir)
