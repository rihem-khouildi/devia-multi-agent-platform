import json
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from api.deps import get_settings
from api.schemas.graphrag import (
    GraphRAGSummaryResponse,
    GraphRAGLoadRequest,
    GraphRAGStatusResponse,
    StoryContextResponse,
    StoryFilesResponse,
    StoryTestsResponse,
    StoryDependenciesResponse,
    StorySummaryResponse,
)
from api.services import graphrag_service
from config.settings import Settings

router = APIRouter(prefix="/graphrag", tags=["graphrag"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_graph():
    """Raise 503 if no GraphRAG context has been loaded yet."""
    if graphrag_service.get_context() is None:
        raise HTTPException(
            status_code=503,
            detail="GraphRAG context not loaded. POST /graphrag/load first.",
        )


def _require_story_context(story_id: str) -> dict:
    """Return assembled story context or raise 404."""
    _require_graph()
    ctx = graphrag_service.get_story_context(story_id)
    if ctx is None:
        raise HTTPException(status_code=503, detail="GraphRAG context unavailable.")
    return ctx


# ── Global endpoints (unchanged contract) ─────────────────────────────────────

@router.get("/summary", response_model=GraphRAGSummaryResponse)
async def get_summary(settings: Settings = Depends(get_settings)):
    ctx = graphrag_service.get_context()
    if ctx is None:
        return GraphRAGSummaryResponse(
            loaded=False,
            source_file=None,
            entity_count=0,
            relation_count=0,
            entity_types=[],
            entities=[],
            relations=[],
        )
    return GraphRAGSummaryResponse(**graphrag_service.summary_dict(ctx))


@router.post("/load", response_model=GraphRAGSummaryResponse)
async def load_graphrag(body: GraphRAGLoadRequest, settings: Settings = Depends(get_settings)):
    try:
        ctx = graphrag_service.load_context(body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to load GraphRAG file: {exc}")
    return GraphRAGSummaryResponse(**graphrag_service.summary_dict(ctx))


@router.post("/upload", response_model=GraphRAGSummaryResponse)
async def upload_graphrag(file: UploadFile = File(...), settings: Settings = Depends(get_settings)):
    """Upload a GraphRAG JSON file and load it as the user context (highest priority)."""
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accepted.")

    content = await file.read()
    try:
        json.loads(content)   # validate JSON before saving
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}")

    # Persist to a dedicated user uploads directory so restarts can reload it
    upload_dir = settings.pipeline.docs_dir / "user_graphrag"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / "user-graph.json"
    dest.write_bytes(content)

    try:
        ctx = graphrag_service.load_context(str(dest), source="user")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to load uploaded GraphRAG: {exc}")

    return GraphRAGSummaryResponse(**graphrag_service.summary_dict(ctx))


@router.post("/load-default", response_model=GraphRAGSummaryResponse)
async def load_default_graphrag(settings: Settings = Depends(get_settings)):
    """Reload the server-side default GraphRAG (drops any user upload)."""
    import os
    filename = os.getenv("GRAPHRAG_FILE", "test-graph.json")
    candidate = settings.pipeline.docs_dir / filename
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Default GraphRAG file not found: {candidate}")
    try:
        ctx = graphrag_service.load_context(str(candidate), source="default")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to load default GraphRAG: {exc}")
    return GraphRAGSummaryResponse(**graphrag_service.summary_dict(ctx))


@router.get("/status", response_model=GraphRAGStatusResponse)
async def graphrag_status():
    """Return current load status and source without full summary payload."""
    return GraphRAGStatusResponse(
        loaded=graphrag_service.get_context() is not None,
        source=graphrag_service.get_source(),
    )


# ── Story-centric endpoints ───────────────────────────────────────────────────

@router.get("/stories/{story_id}/context", response_model=StoryContextResponse)
async def get_story_context(story_id: str, settings: Settings = Depends(get_settings)):
    """
    Full graph context for a story: impacted files, related entities,
    relations, architectural constraints, and an LLM-ready prompt snippet.
    """
    data = _require_story_context(story_id)
    return StoryContextResponse(**data)


@router.get("/stories/{story_id}/files", response_model=StoryFilesResponse)
async def get_story_files(story_id: str, settings: Settings = Depends(get_settings)):
    """Files impacted by this story according to the knowledge graph."""
    data = _require_story_context(story_id)
    return StoryFilesResponse(
        story_id=story_id,
        files=data["files"],
        source=data["source"],
    )


@router.get("/stories/{story_id}/tests", response_model=StoryTestsResponse)
async def get_story_tests(story_id: str, settings: Settings = Depends(get_settings)):
    """Test files related to this story."""
    data = _require_story_context(story_id)
    return StoryTestsResponse(
        story_id=story_id,
        tests=data["tests"],
        source=data["source"],
    )


@router.get("/stories/{story_id}/dependencies", response_model=StoryDependenciesResponse)
async def get_story_dependencies(story_id: str, settings: Settings = Depends(get_settings)):
    """
    Direct and transitive dependency relations for this story's entities.
    Useful for impact analysis before code generation.
    """
    _require_graph()
    deps = graphrag_service.get_story_dependencies(story_id)
    if deps is None:
        raise HTTPException(status_code=503, detail="GraphRAG context unavailable.")
    return StoryDependenciesResponse(**deps)


@router.get("/stories/{story_id}/summary", response_model=StorySummaryResponse)
async def get_story_summary(story_id: str, settings: Settings = Depends(get_settings)):
    """Lightweight stats for this story in the knowledge graph."""
    data = _require_story_context(story_id)

    entity_types: dict = {}
    for e in data["related_entities"]:
        entity_types[e["type"]] = entity_types.get(e["type"], 0) + 1

    return StorySummaryResponse(
        story_id=story_id,
        found=data["found"],
        entity_count=len(data["related_entities"]),
        relation_count=len(data["relations"]),
        file_count=len(data["files"]),
        test_count=len(data["tests"]),
        module_count=len(data["modules"]),
        constraint_count=len(data["constraints"]),
        entity_types=entity_types,
        prompt_snippet_length=len(data["prompt_snippet"]),
    )
