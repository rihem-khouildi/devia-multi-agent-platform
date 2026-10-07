"""
Per-run structured error store with PostgreSQL persistence and memory fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.db import session_scope
from api.db_models import RunErrorModel
from api.services import run_store
from utils.logger import get_logger

logger = get_logger(__name__)

_store: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}


def init_run(run_id: str) -> None:
    _store.setdefault(run_id, {"compile": None, "test": None})


def store_compile_error(run_id: str, payload: Dict[str, Any]) -> None:
    _store_error(run_id, "compile", payload)
    logger.info("[error_store] run=%s  compile error recorded  type=%s", run_id, payload.get("error_type"))


def store_test_error(run_id: str, payload: Dict[str, Any]) -> None:
    _store_error(run_id, "test", payload)
    logger.info("[error_store] run=%s  test error recorded  type=%s", run_id, payload.get("error_type"))


def get_run_errors(run_id: str) -> Optional[List[Dict[str, Any]]]:
    bucket = _store.get(run_id)
    if bucket is not None:
        return [v for v in (bucket["compile"], bucket["test"]) if v is not None]

    try:
        with session_scope() as session:
            if session is not None:
                rows = session.execute(
                    select(RunErrorModel)
                    .where(RunErrorModel.run_id == run_id)
                    .order_by(RunErrorModel.step.asc(), RunErrorModel.id.asc())
                ).scalars().all()
                if rows:
                    return [_row_to_payload(row) for row in rows]
    except SQLAlchemyError:
        pass

    if run_store.run_exists(run_id):
        return []
    return None


def _store_error(run_id: str, bucket_key: str, payload: Dict[str, Any]) -> None:
    if run_id not in _store:
        _store[run_id] = {"compile": None, "test": None}
    _store[run_id][bucket_key] = payload

    try:
        with session_scope() as session:
            if session is None:
                return

            step = payload.get("step") or ("run_tests" if bucket_key == "test" else bucket_key)
            existing = session.execute(
                select(RunErrorModel).where(
                    RunErrorModel.run_id == run_id,
                    RunErrorModel.step == step,
                )
            ).scalar_one_or_none()

            data = {
                "run_id": run_id,
                "step": step,
                "error_type": payload.get("error_type", "unknown"),
                "summary": payload.get("summary", ""),
                "copyable_error": payload.get("copyable_error", ""),
                "files_json": payload.get("files", []),
                "raw_excerpt": payload.get("raw_excerpt", ""),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if existing is None:
                session.add(RunErrorModel(**data))
            else:
                for key, value in data.items():
                    setattr(existing, key, value)
    except SQLAlchemyError:
        logger.debug("[error_store] database write failed; error kept in memory for run %s", run_id)


def _row_to_payload(row: RunErrorModel) -> Dict[str, Any]:
    return {
        "run_id": row.run_id,
        "step": row.step,
        "error_type": row.error_type,
        "summary": row.summary,
        "copyable_error": row.copyable_error,
        "files": row.files_json or [],
        "raw_excerpt": row.raw_excerpt,
    }
