from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_settings
from api.schemas.stories import StorySchema, StoriesListResponse
from api.services import jira_service
from config.settings import Settings

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("", response_model=StoriesListResponse)
async def list_stories(
    max_results: int = Query(50, ge=1, le=200),
    settings: Settings = Depends(get_settings),
):
    stories, source = await jira_service.fetch_stories(settings, max_results=max_results)
    return StoriesListResponse(
        stories=[StorySchema.from_domain(s) for s in stories],
        total=len(stories),
        source=source,
    )


@router.get("/{story_id}", response_model=StorySchema)
async def get_story(story_id: str, settings: Settings = Depends(get_settings)):
    story = await jira_service.fetch_story(story_id, settings)
    if not story:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found. Jira may not be configured or the story does not exist.",
        )
    return StorySchema.from_domain(story)
