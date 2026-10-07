"""
Persistent storage for pipeline runs with PostgreSQL/SQLAlchemy.

Falls back to an in-memory store when the database is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.db import session_scope
from api.db_models import RunModel
from config.settings import Settings

_memory_runs: Dict[str, Dict[str, Any]] = {}


def save_run(settings: Settings, record: Dict[str, Any]) -> None:
    payload = {
        "run_id": record["run_id"],
        "story_id": record["story_id"],
        "story_title": record["story_title"],
        "status": record["status"],
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
        "error": record.get("error"),
        "graph_context_injected": bool(record.get("graph_context_injected")),
        "all_gates_passed": (record.get("result") or {}).get("all_gates_passed"),
        "result_json": record.get("result"),
        "steps_json": record.get("steps", []),
        "updated_at": record.get("completed_at") or record.get("started_at") or "",
    }

    try:
        with session_scope() as session:
            if session is None:
                _memory_runs[payload["run_id"]] = _record_from_payload(payload)
                return

            existing = session.get(RunModel, payload["run_id"])
            if existing is None:
                session.add(RunModel(**payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
    except SQLAlchemyError:
        _memory_runs[payload["run_id"]] = _record_from_payload(payload)


def get_run(settings: Settings, run_id: str) -> Optional[Dict[str, Any]]:
    if run_id in _memory_runs:
        return dict(_memory_runs[run_id])

    try:
        with session_scope() as session:
            if session is None:
                return None
            model = session.get(RunModel, run_id)
            return _model_to_record(model) if model else None
    except SQLAlchemyError:
        return _memory_runs.get(run_id)


def list_runs(settings: Settings) -> List[Dict[str, Any]]:
    runs_by_id = {run_id: dict(record) for run_id, record in _memory_runs.items()}

    try:
        with session_scope() as session:
            if session is None:
                return _sorted_runs(runs_by_id.values())

            models = session.execute(
                select(RunModel).order_by(
                    RunModel.started_at.desc(),
                    RunModel.updated_at.desc(),
                    RunModel.run_id.desc(),
                )
            ).scalars().all()
            for model in models:
                runs_by_id[model.run_id] = _model_to_record(model)
    except SQLAlchemyError:
        pass

    return _sorted_runs(runs_by_id.values())


def run_exists(run_id: str) -> bool:
    if run_id in _memory_runs:
        return True
    try:
        with session_scope() as session:
            if session is None:
                return False
            return session.get(RunModel, run_id) is not None
    except SQLAlchemyError:
        return False


def _model_to_record(model: RunModel) -> Dict[str, Any]:
    return {
        "run_id": model.run_id,
        "story_id": model.story_id,
        "story_title": model.story_title,
        "status": model.status,
        "started_at": model.started_at,
        "completed_at": model.completed_at,
        "steps": model.steps_json or [],
        "result": model.result_json,
        "error": model.error,
        "graph_context_injected": bool(model.graph_context_injected),
        "all_gates_passed": model.all_gates_passed,
    }


def _record_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": payload["run_id"],
        "story_id": payload["story_id"],
        "story_title": payload["story_title"],
        "status": payload["status"],
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "steps": payload.get("steps_json") or [],
        "result": payload.get("result_json"),
        "error": payload.get("error"),
        "graph_context_injected": bool(payload.get("graph_context_injected")),
        "all_gates_passed": payload.get("all_gates_passed"),
    }


def _sorted_runs(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        records,
        key=lambda row: (
            row.get("started_at") is None,
            row.get("started_at") or "",
            row.get("completed_at") or "",
            row.get("run_id") or "",
        ),
        reverse=True,
    )
