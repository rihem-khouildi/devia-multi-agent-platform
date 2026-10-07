"""
Thin wrapper around JiraClient for use from API routes.
Handles missing/misconfigured Jira gracefully.
"""

from typing import List, Optional

from config.settings import Settings
from core.models import UserStory


def _is_jira_configured(settings: Settings) -> bool:
    jira = settings.jira
    return bool(jira.url and jira.username and jira.api_token
                and "yourcompany" not in jira.url)


async def fetch_stories(settings: Settings, max_results: int = 50) -> tuple[List[UserStory], str]:
    """
    Returns (stories, source) where source is "jira" or "unavailable".
    Never raises — returns empty list with source="unavailable" on any error.
    """
    if not _is_jira_configured(settings):
        print("Jira not configured according to settings")
        return [], "unavailable"

    try:
           from agents.jira_client import JiraClient
           client = JiraClient(settings.jira)
           print("About to call Jira get_project_stories")
           stories = await client.get_project_stories(max_results=max_results)
           print(f"Fetched {len(stories)} stories from Jira")
           return stories, "jira"
    except Exception as e:
           print(f"Jira fetch_stories error: {e}")
           return [], "unavailable"


async def fetch_story(story_id: str, settings: Settings) -> Optional[UserStory]:
    """Fetch a single story by ID. Returns None if unavailable."""
    if not _is_jira_configured(settings):
        return None
    try:
        from agents.jira_client import JiraClient
        client = JiraClient(settings.jira)
        return await client.get_user_story(story_id)
    except Exception:
        return None


def jira_status(settings: Settings) -> dict:
    configured = _is_jira_configured(settings)
    return {
        "configured": configured,
        "url": settings.jira.url if configured else None,
        "project_key": settings.jira.project_key if configured else None,
    }
