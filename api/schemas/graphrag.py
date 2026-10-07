from pydantic import BaseModel
from typing import Any, Dict, List, Optional


# ── Shared building blocks ────────────────────────────────────────────────────

class GraphRAGEntitySchema(BaseModel):
    id: str
    name: str
    type: str
    description: str
    user_story_refs: List[str]


class GraphRAGRelationSchema(BaseModel):
    source: str
    target: str
    relation_type: str
    description: str


# ── Existing global endpoints ─────────────────────────────────────────────────

class GraphRAGSummaryResponse(BaseModel):
    loaded: bool
    source_file: Optional[str]
    entity_count: int
    relation_count: int
    entity_types: List[str]
    entities: List[GraphRAGEntitySchema]
    relations: List[GraphRAGRelationSchema]


class GraphRAGLoadRequest(BaseModel):
    path: str


class GraphRAGStatusResponse(BaseModel):
    loaded: bool
    source: Optional[str]   # "user" | "default" | None


# ── Story-centric endpoints ───────────────────────────────────────────────────

class StoryContextResponse(BaseModel):
    """Full graph context retrieved for a single user story."""
    story_id: str
    found: bool                          # False → graph loaded but no data for this story
    source: str                          # "graph" | "none"

    # From raw_metadata["stories"][story_id] if present
    files: List[str]
    tests: List[str]
    modules: List[str]
    constraints: List[str]
    tags: List[str]
    priority: Optional[str]

    # From entity graph filtered by story_id
    related_entities: List[GraphRAGEntitySchema]
    relations: List[GraphRAGRelationSchema]

    # Prompt-ready snippet for agent injection
    prompt_snippet: str


class StoryFilesResponse(BaseModel):
    story_id: str
    files: List[str]
    source: str


class StoryTestsResponse(BaseModel):
    story_id: str
    tests: List[str]
    source: str


class StoryDependenciesResponse(BaseModel):
    story_id: str
    direct: List[GraphRAGRelationSchema]    # relations where source is a story entity
    transitive: List[GraphRAGRelationSchema]  # one hop further
    dependency_names: List[str]             # unique target names, easy to consume


class StorySummaryResponse(BaseModel):
    story_id: str
    found: bool
    entity_count: int
    relation_count: int
    file_count: int
    test_count: int
    module_count: int
    constraint_count: int
    entity_types: Dict[str, int]           # {"class": 3, "service": 1, ...}
    prompt_snippet_length: int
