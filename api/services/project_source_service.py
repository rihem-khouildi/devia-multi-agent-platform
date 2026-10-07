"""
Manages user-uploaded project sources (zip archives).

Layout on disk:
  uploaded-projects/
    <project_name>/
      pom.xml | build.gradle
      src/...
"""

import io
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")


def _uploaded_root(settings: Settings) -> Path:
    root = settings.pipeline.get_project_root() / "uploaded-projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_safe_member(member_path: str) -> bool:
    """Reject paths that escape the target directory (path-traversal guard)."""
    parts = Path(member_path).parts
    return ".." not in parts and not Path(member_path).is_absolute()


def _sanitize_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    return name[:128]


def _is_valid_project(folder: Path) -> bool:
    return (folder / "pom.xml").exists() or (folder / "build.gradle").exists()


# ── Public API ────────────────────────────────────────────────────────────────

def list_sources(settings: Settings) -> Dict[str, Any]:
    """Return the default base project and all uploaded projects."""
    base_path = settings.pipeline.target_repo_path
    sources: List[Dict[str, Any]] = [
        {
            "name": "base-spring-project",
            "type": "default",
            "path": str(base_path),
            "valid": _is_valid_project(base_path),
        }
    ]

    root = _uploaded_root(settings)
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            sources.append(
                {
                    "name": entry.name,
                    "type": "uploaded",
                    "path": str(entry),
                    "valid": _is_valid_project(entry),
                }
            )

    return {"sources": sources, "total": len(sources)}


def upload_project(zip_bytes: bytes, filename: str, settings: Settings) -> Dict[str, Any]:
    """
    Extract a zip archive into uploaded-projects/<project_name>/.
    Returns info about the imported project.
    """
    # Derive project name from filename (strip .zip)
    raw_name = Path(filename).stem
    project_name = _sanitize_name(raw_name)
    if not project_name:
        raise ValueError("Cannot derive a valid project name from the filename.")

    root = _uploaded_root(settings)
    target = root / project_name

    if target.exists():
        raise FileExistsError(
            f"A project named '{project_name}' already exists. Delete it first or rename your zip."
        )

    # Validate zip
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("Uploaded file is not a valid zip archive.")

    # Security: check all member paths
    for member in zf.namelist():
        if not _is_safe_member(member):
            raise ValueError(f"Unsafe path detected in zip: {member}")

    # Extract — strip a single top-level directory if the zip wraps everything in one folder
    members = zf.namelist()
    top_dirs = {m.split("/")[0] for m in members if m.strip()}
    strip_prefix: Optional[str] = None
    if len(top_dirs) == 1:
        sole = next(iter(top_dirs))
        if all(m.startswith(sole + "/") or m == sole + "/" for m in members):
            strip_prefix = sole + "/"

    target.mkdir(parents=True)
    try:
        for member in members:
            dest_rel = member[len(strip_prefix):] if strip_prefix and member.startswith(strip_prefix) else member
            if not dest_rel or dest_rel.endswith("/"):
                continue
            dest_path = target / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(zf.read(member))
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(f"Failed to extract zip: {exc}") from exc

    valid = _is_valid_project(target)
    if not valid:
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError(
            "The uploaded project does not appear to be a valid Maven/Gradle project "
            "(no pom.xml or build.gradle found at root level)."
        )

    logger.info("Uploaded project '%s' extracted to %s", project_name, target)
    return {"name": project_name, "path": str(target), "valid": True}


def delete_source(project_name: str, settings: Settings) -> None:
    if not _SAFE_NAME_RE.match(project_name):
        raise ValueError("Invalid project name.")
    root = _uploaded_root(settings)
    target = root / project_name
    if not target.exists():
        raise FileNotFoundError(f"Project '{project_name}' not found.")
    shutil.rmtree(target)
    logger.info("Deleted uploaded project '%s'", project_name)


def get_source_path(source_type: str, source_name: Optional[str], settings: Settings) -> Path:
    """Resolve the actual filesystem path for a given source type/name."""
    if source_type == "default" or not source_type:
        return settings.pipeline.target_repo_path
    if source_type == "uploaded":
        if not source_name:
            raise ValueError("source_project_name is required when source_project_type='uploaded'.")
        if not _SAFE_NAME_RE.match(source_name):
            raise ValueError("Invalid source_project_name.")
        root = _uploaded_root(settings)
        path = root / source_name
        if not path.exists():
            raise FileNotFoundError(f"Uploaded project '{source_name}' not found.")
        return path
    raise ValueError(f"Unknown source_project_type: '{source_type}'.")


def build_tree(project_name: str, settings: Settings) -> Dict[str, Any]:
    """Return a recursive directory tree for an uploaded project."""
    if not _SAFE_NAME_RE.match(project_name):
        raise ValueError("Invalid project name.")
    root = _uploaded_root(settings)
    folder = root / project_name
    if not folder.exists():
        raise FileNotFoundError(f"Project '{project_name}' not found.")
    return {"name": project_name, "type": "directory", "children": _tree_node(folder)}


def _tree_node(path: Path) -> List[Dict[str, Any]]:
    children = []
    try:
        for entry in sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name)):
            if entry.is_dir():
                children.append({"name": entry.name, "type": "directory", "children": _tree_node(entry)})
            else:
                children.append({"name": entry.name, "type": "file", "size": entry.stat().st_size})
    except PermissionError:
        pass
    return children
