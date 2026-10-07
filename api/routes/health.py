from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer

from api.deps import get_settings
from config.settings import Settings

router = APIRouter(prefix="/health", tags=["health"])

_optional_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@router.get("")
async def health(
    token: Annotated[Optional[str], Depends(_optional_bearer)] = None,
    settings: Settings = Depends(get_settings),
):
    from api.services.jira_service import jira_status
    from api.services import integration_service
    from api.db import is_database_ready, get_backend_name
    from api.auth import decode_access_token
    from api.services import user_service

    from api.services import graphrag_service

    jira = jira_status(settings)
    github_configured = bool(settings.github.token and settings.github.owner and settings.github.repo)
    hf_configured = bool(settings.hf.api_key)
    db_ready = is_database_ready()
    graphrag_loaded = graphrag_service.get_context() is not None
    graphrag_source = graphrag_service.get_source()  # "user" | "default" | None

    # Determine integration sources (user > env) if authenticated
    integration_sources = {
        "jira": {"configured": bool(jira.get("configured")), "source": "env" if jira.get("configured") else None},
        "github": {"configured": github_configured, "source": "env" if github_configured else None},
    }

    if token:
        try:
            payload = decode_access_token(token, settings)
            if payload:
                username = payload.get("sub", "")
                user = user_service.get_user_by_username(username)
                if user:
                    sources = integration_service.get_integration_source(user["id"], settings)
                    integration_sources["jira"] = sources["jira"]
                    integration_sources["github"] = sources["github"]
        except Exception:
            pass  # unauthenticated health check — fall back to env-only info

    return {
        "status": "ok",
        "database": {
            "ready": db_ready,
            "backend": get_backend_name(),
            "configured": bool(settings.database.url),
        },
        "config": {
            "jira": {**jira, **integration_sources["jira"]},
            "github": {"configured": integration_sources["github"]["configured"], "source": integration_sources["github"]["source"]},
            "huggingface": {"configured": hf_configured},
            "graphrag": {"loaded": graphrag_loaded, "source": graphrag_source},
            "pipeline": {
                "output_dir": str(settings.pipeline.output_dir),
                "min_test_coverage": settings.pipeline.min_test_coverage,
                "min_review_score": settings.pipeline.min_review_score,
            },
        },
    }
