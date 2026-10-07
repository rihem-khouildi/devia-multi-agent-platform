"""
Project sources endpoints — list, upload, delete, tree.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from api.deps import get_settings, get_current_user
from api.services import project_source_service
from config.settings import Settings

router = APIRouter(prefix="/projects/sources", tags=["project-sources"])

_MAX_ZIP_MB = 100
_MAX_ZIP_BYTES = _MAX_ZIP_MB * 1024 * 1024


@router.get("")
async def list_sources(
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    return project_source_service.list_sources(settings)


@router.post("/upload", status_code=201)
async def upload_project(
    _: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Only .zip files are accepted.")

    content = await file.read()
    if len(content) > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {_MAX_ZIP_MB} MB.")

    try:
        result = project_source_service.upload_project(content, file.filename, settings)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    return result


@router.delete("/{project_name}", status_code=204)
async def delete_source(
    project_name: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    try:
        project_source_service.delete_source(project_name, settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{project_name}/tree")
async def get_tree(
    project_name: str,
    _: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    try:
        return project_source_service.build_tree(project_name, settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
