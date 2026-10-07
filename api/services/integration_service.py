"""
Integration service — manages per-user Jira & GitHub configuration.

Security rules enforced here:
- Tokens are ALWAYS encrypted with Fernet before being written to the DB.
- Tokens are NEVER returned in plain text via any public method.
- Decryption happens only inside merge_settings(), just before the pipeline runs.
- Log statements NEVER include token values.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from api.db import session_scope
from api.db_models import UserIntegrationModel
from config.settings import Settings, JiraConfig, GitHubConfig

logger = logging.getLogger(__name__)

_MASKED = "••••••••configured"


# ── Encryption helpers ────────────────────────────────────────────────────────

def _get_fernet(settings: Settings) -> Optional[Fernet]:
    key = settings.encryption.key
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        logger.error("ENCRYPTION_KEY is invalid — cannot encrypt/decrypt tokens")
        return None


def _encrypt(value: str, fernet: Fernet) -> str:
    return fernet.encrypt(value.encode()).decode()


def _decrypt(value: str, fernet: Fernet) -> str:
    return fernet.decrypt(value.encode()).decode()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_row(user_id: int) -> Optional[UserIntegrationModel]:
    with session_scope() as session:
        if session is None:
            return None
        return session.query(UserIntegrationModel).filter_by(user_id=user_id).first()


# ── Public API ────────────────────────────────────────────────────────────────

def get_integration_config(user_id: int) -> dict:
    """
    Return the integration config for a user, with tokens MASKED.
    Safe to expose in API responses.
    """
    row = _get_row(user_id)
    if not row:
        return {
            "jira": {
                "configured": False,
                "jira_url": None,
                "jira_username": None,
                "jira_api_token": None,
                "jira_project_key": None,
            },
            "github": {
                "configured": False,
                "github_owner": None,
                "github_repo": None,
                "github_token": None,
            },
        }

    jira_configured = bool(row.jira_url and row.jira_username and row.jira_api_token_enc)
    github_configured = bool(row.github_owner and row.github_repo and row.github_token_enc)

    return {
        "jira": {
            "configured": jira_configured,
            "jira_url": row.jira_url,
            "jira_username": row.jira_username,
            "jira_api_token": _MASKED if row.jira_api_token_enc else None,
            "jira_project_key": row.jira_project_key,
        },
        "github": {
            "configured": github_configured,
            "github_owner": row.github_owner,
            "github_repo": row.github_repo,
            "github_token": _MASKED if row.github_token_enc else None,
        },
    }


def save_integration_config(
    user_id: int,
    settings: Settings,
    *,
    jira_url: Optional[str] = None,
    jira_username: Optional[str] = None,
    jira_api_token: Optional[str] = None,
    jira_project_key: Optional[str] = None,
    github_owner: Optional[str] = None,
    github_repo: Optional[str] = None,
    github_token: Optional[str] = None,
) -> None:
    """
    Upsert the user's integration config.
    Token fields left as None (or empty string) preserve the existing encrypted value.
    Tokens are ALWAYS encrypted before storage — never stored in plain text.
    """
    fernet = _get_fernet(settings)

    with session_scope() as session:
        if session is None:
            logger.error("Database not available — cannot save integration config")
            return

        row = session.query(UserIntegrationModel).filter_by(user_id=user_id).first()
        if not row:
            row = UserIntegrationModel(user_id=user_id)
            session.add(row)

        # Non-secret fields — always overwrite if provided
        if jira_url is not None:
            row.jira_url = jira_url.strip() or None
        if jira_username is not None:
            row.jira_username = jira_username.strip() or None
        if jira_project_key is not None:
            row.jira_project_key = jira_project_key.strip() or None
        if github_owner is not None:
            row.github_owner = github_owner.strip() or None
        if github_repo is not None:
            row.github_repo = github_repo.strip() or None

        # Secret fields — only overwrite when a non-empty value is supplied
        if jira_api_token and jira_api_token.strip() and jira_api_token != _MASKED:
            if fernet:
                row.jira_api_token_enc = _encrypt(jira_api_token.strip(), fernet)
            else:
                logger.warning("ENCRYPTION_KEY not set — Jira token stored in plain text (not recommended)")
                row.jira_api_token_enc = jira_api_token.strip()

        if github_token and github_token.strip() and github_token != _MASKED:
            if fernet:
                row.github_token_enc = _encrypt(github_token.strip(), fernet)
            else:
                logger.warning("ENCRYPTION_KEY not set — GitHub token stored in plain text (not recommended)")
                row.github_token_enc = github_token.strip()

    logger.info("Integration config saved for user_id=%s (tokens NOT logged)", user_id)


def merge_settings(base_settings: Settings, user_id: int) -> Settings:
    """
    Build effective settings by overlaying user config on top of .env defaults.
    Decryption happens HERE and only here — the result is kept in memory only.

    Priority: user DB config > .env > defaults
    """
    row = _get_row(user_id)
    if not row:
        return base_settings

    fernet = _get_fernet(base_settings)
    effective = deepcopy(base_settings)

    # ── Jira overlay ─────────────────────────────────────────────────────────
    jira_token_plain: Optional[str] = None
    if row.jira_api_token_enc:
        try:
            jira_token_plain = (
                _decrypt(row.jira_api_token_enc, fernet) if fernet else row.jira_api_token_enc
            )
        except (InvalidToken, Exception):
            logger.error("Failed to decrypt Jira token for user_id=%s — using .env fallback", user_id)

    if row.jira_url:
        effective.jira = JiraConfig(
            url=row.jira_url,
            username=row.jira_username or base_settings.jira.username,
            api_token=jira_token_plain or base_settings.jira.api_token,
            project_key=row.jira_project_key or base_settings.jira.project_key,
        )

    # ── GitHub overlay ────────────────────────────────────────────────────────
    github_token_plain: Optional[str] = None
    if row.github_token_enc:
        try:
            github_token_plain = (
                _decrypt(row.github_token_enc, fernet) if fernet else row.github_token_enc
            )
        except (InvalidToken, Exception):
            logger.error("Failed to decrypt GitHub token for user_id=%s — using .env fallback", user_id)

    if row.github_owner and row.github_repo:
        effective.github = GitHubConfig(
            token=github_token_plain or base_settings.github.token,
            owner=row.github_owner,
            repo=row.github_repo,
            default_branch=base_settings.github.default_branch,
            base_branch=base_settings.github.base_branch,
        )

    return effective


def get_integration_source(user_id: int, settings: Settings) -> dict:
    """
    Return the source of each integration config: 'user', 'env', or None.
    Used by the health endpoint.
    """
    row = _get_row(user_id)

    jira_from_user = bool(
        row and row.jira_url and row.jira_username and row.jira_api_token_enc
    )
    jira_from_env = bool(settings.jira.url and settings.jira.username and settings.jira.api_token)

    github_from_user = bool(
        row and row.github_owner and row.github_repo and row.github_token_enc
    )
    github_from_env = bool(
        settings.github.token and settings.github.owner and settings.github.repo
    )

    return {
        "jira": {
            "configured": jira_from_user or jira_from_env,
            "source": "user" if jira_from_user else ("env" if jira_from_env else None),
        },
        "github": {
            "configured": github_from_user or github_from_env,
            "source": "user" if github_from_user else ("env" if github_from_env else None),
        },
    }


def test_jira_connection(user_id: int, settings: Settings) -> dict:
    """
    Test Jira connectivity using effective settings (user > env).
    Returns {"success": bool, "message": str}.
    """
    import requests as http_requests
    from requests.auth import HTTPBasicAuth

    effective = merge_settings(settings, user_id)
    jira_url = effective.jira.url
    username = effective.jira.username
    token = effective.jira.api_token

    if not (jira_url and username and token):
        return {"success": False, "message": "Jira is not configured."}

    try:
        url = f"{jira_url.rstrip('/')}/rest/api/3/myself"
        resp = http_requests.get(url, auth=HTTPBasicAuth(username, token), timeout=8)
        if resp.status_code == 200:
            display = resp.json().get("displayName", username)
            return {"success": True, "message": f"Connected as {display}"}
        return {"success": False, "message": f"Jira returned HTTP {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "message": f"Connection error: {exc}"}


def test_github_connection(user_id: int, settings: Settings) -> dict:
    """
    Test GitHub connectivity using effective settings (user > env).
    Returns {"success": bool, "message": str}.
    """
    import requests as http_requests

    effective = merge_settings(settings, user_id)
    token = effective.github.token
    owner = effective.github.owner
    repo = effective.github.repo

    if not (token and owner and repo):
        return {"success": False, "message": "GitHub is not configured."}

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        resp = http_requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            full_name = resp.json().get("full_name", f"{owner}/{repo}")
            return {"success": True, "message": f"Repository {full_name} is accessible"}
        if resp.status_code == 404:
            return {"success": False, "message": f"Repository {owner}/{repo} not found or not accessible"}
        return {"success": False, "message": f"GitHub returned HTTP {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "message": f"Connection error: {exc}"}
