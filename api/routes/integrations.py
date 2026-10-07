"""
Routes for per-user Jira & GitHub integration configuration.
Tokens are NEVER returned in plain text — only masked values are exposed.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_settings, get_current_user
from api.services import integration_service
from config.settings import Settings

router = APIRouter(prefix="/config/integrations", tags=["integrations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class IntegrationSaveRequest(BaseModel):
    jira_url: Optional[str] = None
    jira_username: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_project_key: Optional[str] = None
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None
    github_token: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_integrations(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Return the current user's integration config.
    Tokens are masked — never returned in plain text.
    """
    return integration_service.get_integration_config(current_user["id"])


@router.post("")
async def save_integrations(
    body: IntegrationSaveRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Save or update the current user's integration config.
    Token fields left empty or matching the masked placeholder are preserved unchanged.
    """
    if not settings.encryption.is_configured():
        raise HTTPException(
            status_code=500,
            detail="ENCRYPTION_KEY is not set on the server. Contact the administrator.",
        )

    integration_service.save_integration_config(
        user_id=current_user["id"],
        settings=settings,
        jira_url=body.jira_url,
        jira_username=body.jira_username,
        jira_api_token=body.jira_api_token,
        jira_project_key=body.jira_project_key,
        github_owner=body.github_owner,
        github_repo=body.github_repo,
        github_token=body.github_token,
    )
    return {"success": True, "message": "Integration configuration saved."}


@router.post("/test-jira")
async def test_jira(
    current_user: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Test Jira connectivity using user config if available, otherwise .env.
    """
    result = integration_service.test_jira_connection(current_user["id"], settings)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/test-github")
async def test_github(
    current_user: Annotated[dict, Depends(get_current_user)],
    settings: Settings = Depends(get_settings),
):
    """
    Test GitHub connectivity using user config if available, otherwise .env.
    """
    result = integration_service.test_github_connection(current_user["id"], settings)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
