from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class StorySchema(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    priority: str
    story_points: Optional[int]
    labels: List[str]
    epic: Optional[str]

    @classmethod
    def from_domain(cls, us) -> "StorySchema":
        return cls(
            id=us.id,
            title=us.title,
            description=us.description,
            acceptance_criteria=us.acceptance_criteria,
            priority=us.priority,
            story_points=us.story_points,
            labels=us.labels,
            epic=us.epic,
        )


class StoriesListResponse(BaseModel):
    stories: List[StorySchema]
    total: int
    source: str  # "jira" | "unavailable"
