"""
Per-run structured event store with PostgreSQL persistence and memory fallback.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.db import session_scope
from api.db_models import RunEventModel
from api.services import run_store
from utils.logger import get_logger

logger = get_logger(__name__)

_events: Dict[str, List[Dict[str, Any]]] = {}


def init_run(run_id: str) -> None:
    _events.setdefault(run_id, [])
    logger.debug("[event_store] Initialised event list for run %s", run_id)


def record_run_event(
    run_id: str,
    step: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if run_id not in _events:
        _events[run_id] = []
        logger.warning("[event_store] run_id %s not initialised; auto-creating list", run_id)

    event: Dict[str, Any] = {
        "id": uuid.uuid4().hex[:16],
        "run_id": run_id,
        "step": step,
        "status": status,
        "message": message,
        "details": details or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _events[run_id].append(event)

    try:
        with session_scope() as session:
            if session is not None:
                session.add(
                    RunEventModel(
                        id=event["id"],
                        run_id=run_id,
                        step=step,
                        status=status,
                        message=message,
                        details_json=event["details"],
                        created_at=event["created_at"],
                    )
                )
    except SQLAlchemyError:
        logger.debug("[event_store] database write failed; event kept in memory for run %s", run_id)

    logger.info(
        "[event_store] run=%s  step=%-20s  status=%s  msg=%s",
        run_id, step, status, message,
    )
    return event


def get_run_events(run_id: str) -> Optional[List[Dict[str, Any]]]:
    events = _events.get(run_id)
    if events is not None:
        return list(events)

    try:
        with session_scope() as session:
            if session is not None:
                rows = session.execute(
                    select(RunEventModel)
                    .where(RunEventModel.run_id == run_id)
                    .order_by(RunEventModel.created_at.asc(), RunEventModel.id.asc())
                ).scalars().all()
                if rows:
                    return [_row_to_event(row) for row in rows]
    except SQLAlchemyError:
        pass

    if run_store.run_exists(run_id):
        return []
    return None


def clear_run_events(run_id: str) -> None:
    _events.pop(run_id, None)


def _row_to_event(row: RunEventModel) -> Dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "step": row.step,
        "status": row.status,
        "message": row.message,
        "details": row.details_json or {},
        "created_at": row.created_at,
    }
