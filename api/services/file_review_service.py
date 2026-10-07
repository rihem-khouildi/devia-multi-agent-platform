"""
Per-run generated-file review store with PostgreSQL persistence and memory fallback.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.db import session_scope
from api.db_models import FileReviewModel, GeneratedFileModel
from utils.logger import get_logger

logger = get_logger(__name__)

_store: Dict[str, List[Dict[str, Any]]] = {}


def _file_id(path: str) -> str:
    return hashlib.sha1(path.encode()).hexdigest()[:12]


def _detect_language(path: str) -> str:
    p = path.lower()
    if p.endswith(".java"):
        return "java"
    if p.endswith(".xml"):
        return "xml"
    if p.endswith((".yml", ".yaml")):
        return "yaml"
    if p.endswith(".properties"):
        return "properties"
    if p.endswith(".json"):
        return "json"
    if p.endswith(".md"):
        return "markdown"
    if p.endswith(".sql"):
        return "sql"
    return "text"


def _make_record(path: str, content: str, status: str = "pending") -> Dict[str, Any]:
    return {
        "id": _file_id(path),
        "path": path,
        "content": content,
        "status": status,
        "language": _detect_language(path),
    }


def init_run_files(run_id: str, files_dict: Dict[str, str]) -> int:
    existing = get_files(run_id)
    if existing is not None and len(existing) > 0:
        logger.debug("[file_review] run=%s already initialised (%d files)", run_id, len(existing))
        return len(existing)

    records = [_make_record(path, content) for path, content in sorted(files_dict.items())]
    _store[run_id] = [dict(record) for record in records]

    try:
        with session_scope() as session:
            if session is not None:
                existing_rows = session.execute(
                    select(GeneratedFileModel).where(GeneratedFileModel.run_id == run_id)
                ).scalars().all()
                existing_by_file_id = {row.file_id: row for row in existing_rows}
                for record in records:
                    row = existing_by_file_id.get(record["id"])
                    if row is None:
                        session.add(
                            GeneratedFileModel(
                                run_id=run_id,
                                file_id=record["id"],
                                path=record["path"],
                                content=record["content"],
                                status=record["status"],
                                language=record["language"],
                            )
                        )
                    else:
                        row.path = record["path"]
                        row.content = record["content"]
                        row.status = row.status or record["status"]
                        row.language = record["language"]
    except SQLAlchemyError:
        logger.debug("[file_review] database init failed; files kept in memory for run %s", run_id)

    logger.info("[file_review] run=%s initialised with %d file(s)", run_id, len(records))
    return len(records)


def get_files(run_id: str) -> Optional[List[Dict[str, Any]]]:
    records = _store.get(run_id)
    if records is not None:
        return [dict(record) for record in records]

    try:
        with session_scope() as session:
            if session is not None:
                rows = session.execute(
                    select(GeneratedFileModel)
                    .where(GeneratedFileModel.run_id == run_id)
                    .order_by(GeneratedFileModel.path.asc())
                ).scalars().all()
                if rows:
                    materialized = [_row_to_record(row) for row in rows]
                    _store[run_id] = [dict(record) for record in materialized]
                    return materialized
    except SQLAlchemyError:
        pass
    return None


def accept_file(run_id: str, file_id: str) -> Optional[Dict[str, Any]]:
    return _set_status(run_id, file_id, "accepted")


def reject_file(run_id: str, file_id: str) -> Optional[Dict[str, Any]]:
    return _set_status(run_id, file_id, "rejected")


def reset_file(run_id: str, file_id: str) -> Optional[Dict[str, Any]]:
    return _set_status(run_id, file_id, "pending")


def is_all_approved(run_id: str) -> bool:
    records = get_files(run_id)
    if not records:
        return False
    return all(r["status"] == "accepted" for r in records)


def review_summary(run_id: str) -> Dict[str, Any]:
    records = get_files(run_id) or []
    by_status: Dict[str, int] = {"pending": 0, "accepted": 0, "rejected": 0}
    for record in records:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
    return {
        "total": len(records),
        "pending": by_status["pending"],
        "accepted": by_status["accepted"],
        "rejected": by_status["rejected"],
        "all_approved": is_all_approved(run_id),
    }


def load_from_artifact(
    run_id: str,
    story_id: str,
    settings,
) -> int:
    existing = get_files(run_id)
    if existing is not None and len(existing) > 0:
        return len(existing)

    from api.services.artifact_service import get_generated_files

    artifact = get_generated_files(story_id, settings)
    if not artifact:
        logger.debug("[file_review] no artifact for run=%s story=%s", run_id, story_id)
        return 0

    files_dict: Dict[str, str] = artifact.get("files") or {}
    if artifact.get("pom_xml"):
        files_dict.setdefault("pom.xml", artifact["pom_xml"])
    if artifact.get("readme"):
        files_dict.setdefault("README.md", artifact["readme"])

    return init_run_files(run_id, files_dict)


def _set_status(run_id: str, file_id: str, status: str) -> Optional[Dict[str, Any]]:
    records = get_files(run_id)
    if records is None:
        return None

    updated_record: Optional[Dict[str, Any]] = None
    for record in records:
        if record["id"] == file_id:
            record["status"] = status
            updated_record = dict(record)
            break

    if updated_record is None:
        return None

    _store[run_id] = [dict(record) for record in records]

    try:
        with session_scope() as session:
            if session is not None:
                row = session.execute(
                    select(GeneratedFileModel).where(
                        GeneratedFileModel.run_id == run_id,
                        GeneratedFileModel.file_id == file_id,
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.status = status

                session.add(FileReviewModel(run_id=run_id, file_id=file_id, status=status))
    except SQLAlchemyError:
        logger.debug("[file_review] database status update failed; file kept in memory for run %s", run_id)

    logger.info("[file_review] run=%s file=%s -> %s", run_id, file_id, status)
    return updated_record


def _row_to_record(row: GeneratedFileModel) -> Dict[str, Any]:
    return {
        "id": row.file_id,
        "path": row.path,
        "content": row.content,
        "status": row.status,
        "language": row.language,
    }
