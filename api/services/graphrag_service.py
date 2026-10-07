"""
GraphRAG context management and story-centric retrieval service.

Architecture:
  - One GraphRAGContext singleton held in memory (reloaded via POST /graphrag/load).
  - Per-story retrieval is computed on demand and cached in _story_cache.
  - Cache is invalidated whenever the context is reloaded.
  - All public functions are pure (no side effects except the singleton mutation
    in load_context / clear_cache).

Story context is assembled from TWO independent sources, then merged:
  1. Entity graph  — entities whose user_story_refs contain story_id,
                     plus relations connecting those entities.
  2. Raw metadata  — if the JSON had a top-level "stories": {"SCRUM-9": {...}}
                     block, we extract files / tests / modules / constraints from it.
     This handles both formats shown in the task brief.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.graphrag_loader import GraphRAGContext, GraphRAGEntity, GraphRAGRelation, load_graphrag

# ── Singleton state ───────────────────────────────────────────────────────────

_current_context: Optional[GraphRAGContext] = None
_current_path: Optional[str] = None
_context_source: Optional[str] = None   # "user" | "default" | None

# Per-story cache: story_id → assembled StoryData dict
# Invalidated on every load_context() call.
_story_cache: Dict[str, Dict[str, Any]] = {}


# ── Public lifecycle ──────────────────────────────────────────────────────────

def get_context() -> Optional[GraphRAGContext]:
    return _current_context


def get_source() -> Optional[str]:
    """Return 'user', 'default', or None depending on what is loaded."""
    return _context_source


def load_context(path: str, source: str = "user") -> GraphRAGContext:
    global _current_context, _current_path, _context_source, _story_cache
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"GraphRAG file not found: {resolved}")
    _current_context = load_graphrag(str(resolved))
    _current_path = str(resolved)
    _context_source = source
    _story_cache = {}          # invalidate per-story cache
    return _current_context


def clear_cache() -> None:
    """Force re-computation of all story caches (e.g. after hot reload)."""
    global _story_cache
    _story_cache = {}


# ── Global summary (existing contract, kept unchanged) ────────────────────────

def summary_dict(ctx: GraphRAGContext) -> dict:
    entity_types = sorted({e.type for e in ctx.entities})
    return {
        "loaded": True,
        "source_file": ctx.source_file,
        "entity_count": len(ctx.entities),
        "relation_count": len(ctx.relations),
        "entity_types": entity_types,
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.type,
                "description": e.description,
                "user_story_refs": e.user_story_refs,
            }
            for e in ctx.entities
        ],
        "relations": [
            {
                "source": r.source,
                "target": r.target,
                "relation_type": r.relation_type,
                "description": r.description,
            }
            for r in ctx.relations
        ],
    }


# ── Story-centric retrieval ───────────────────────────────────────────────────

def get_story_context(story_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the full assembled context for story_id, or None if no graph is loaded.
    Result is cached until the graph is reloaded.
    """
    if _current_context is None:
        return None
    if story_id not in _story_cache:
        _story_cache[story_id] = _assemble_story_context(story_id, _current_context)
    return _story_cache[story_id]


def get_story_files(story_id: str) -> Optional[List[str]]:
    ctx = get_story_context(story_id)
    return ctx["files"] if ctx is not None else None


def get_story_tests(story_id: str) -> Optional[List[str]]:
    ctx = get_story_context(story_id)
    return ctx["tests"] if ctx is not None else None


def get_story_dependencies(story_id: str) -> Optional[Dict[str, Any]]:
    """
    Return direct and transitive dependency relations for story_id.
    Direct  = relations where source is a story-related entity.
    Transitive = one more hop: relations where source is a direct target.
    """
    if _current_context is None:
        return None
    if story_id not in _story_cache:
        _story_cache[story_id] = _assemble_story_context(story_id, _current_context)

    data = _story_cache[story_id]
    entity_names = {e["name"] for e in data["related_entities"]}

    direct = data["relations"]
    direct_targets = {r["target"] for r in direct}

    # One-hop transitive: source is a direct target, but not already in entity_names
    all_relations = [
        {"source": r.source, "target": r.target,
         "relation_type": r.relation_type, "description": r.description}
        for r in _current_context.relations
    ]
    transitive = [
        r for r in all_relations
        if r["source"] in direct_targets and r["source"] not in entity_names
    ]

    dep_names = sorted({r["target"] for r in direct} | {r["target"] for r in transitive})

    return {
        "story_id": story_id,
        "direct": direct,
        "transitive": transitive,
        "dependency_names": dep_names,
    }


def get_story_prompt_snippet(story_id: str) -> str:
    """
    Return a compact text block ready to be injected into an LLM prompt.
    Returns empty string if no graph loaded or no data for story.
    """
    if _current_context is None:
        return ""
    ctx = get_story_context(story_id)
    if ctx is None or not ctx["found"]:
        return ""
    return ctx["prompt_snippet"]


# ── Assembly logic ────────────────────────────────────────────────────────────

def _assemble_story_context(story_id: str, graph: GraphRAGContext) -> Dict[str, Any]:
    """
    Core assembly: combines entity graph + raw_metadata stories block.
    Always returns a dict (never raises). `found` indicates data presence.
    """
    # ── Source 1: entity graph filtered by story_id ───────────────
    filtered = graph.filter_for_story(story_id)
    # filter_for_story includes entities with NO refs at all (global context).
    # We want ONLY entities explicitly tied to this story OR globally untagged
    # as a best-effort — keep both but flag explicitly referenced ones.
    explicit_entities = [e for e in filtered.entities if story_id in e.user_story_refs]
    global_entities   = [e for e in filtered.entities if not e.user_story_refs]

    # Use explicit if present, else fall back to global
    working_entities: List[GraphRAGEntity] = explicit_entities or global_entities

    entity_names = {e.name for e in working_entities}
    working_relations: List[GraphRAGRelation] = [
        r for r in filtered.relations
        if r.source in entity_names or r.target in entity_names
    ]

    # ── Source 2: raw_metadata "stories" block ────────────────────
    stories_block: Dict[str, Any] = graph.raw_metadata.get("stories", {})
    story_meta: Dict[str, Any] = stories_block.get(story_id, {})

    # Also try alternate key patterns (e.g. lowercase, with dash)
    if not story_meta:
        for key in stories_block:
            if key.upper() == story_id.upper():
                story_meta = stories_block[key]
                break

    meta_files:       List[str] = _as_str_list(story_meta.get("files", []))
    meta_tests:       List[str] = _as_str_list(story_meta.get("tests", []))
    meta_modules:     List[str] = _as_str_list(story_meta.get("modules", []))
    meta_constraints: List[str] = _as_str_list(story_meta.get("constraints", []))
    meta_tags:        List[str] = _as_str_list(story_meta.get("tags", []))
    meta_priority: Optional[str] = story_meta.get("priority")

    # ── Merge file/test data from entity types ────────────────────
    # If no raw_metadata section, infer from entity types
    entity_files = [
        e.name for e in working_entities
        if e.type in ("file", "class", "controller", "service", "repository", "entity")
    ]
    entity_tests = [
        e.name for e in working_entities
        if e.type in ("test", "test_class", "test_file")
        or (e.type == "class" and "test" in e.name.lower())
    ]

    files = _dedup(meta_files or entity_files)
    tests = _dedup(meta_tests or entity_tests)
    modules = _dedup(meta_modules or [
        e.name for e in working_entities if e.type == "module"
    ])

    # ── Build prompt snippet ──────────────────────────────────────
    prompt_snippet = _build_prompt_snippet(
        story_id=story_id,
        files=files,
        tests=tests,
        modules=modules,
        constraints=meta_constraints,
        entities=working_entities,
        relations=working_relations,
    )

    found = bool(explicit_entities or story_meta)

    return {
        "story_id": story_id,
        "found": found,
        "source": "graph" if found else "none",
        "files": files,
        "tests": tests,
        "modules": modules,
        "constraints": meta_constraints,
        "tags": meta_tags,
        "priority": meta_priority,
        "related_entities": [
            {
                "id": e.id, "name": e.name, "type": e.type,
                "description": e.description, "user_story_refs": e.user_story_refs,
            }
            for e in working_entities
        ],
        "relations": [
            {
                "source": r.source, "target": r.target,
                "relation_type": r.relation_type, "description": r.description,
            }
            for r in working_relations
        ],
        "prompt_snippet": prompt_snippet,
    }


def _build_prompt_snippet(
    story_id: str,
    files: List[str],
    tests: List[str],
    modules: List[str],
    constraints: List[str],
    entities: List[GraphRAGEntity],
    relations: List[GraphRAGRelation],
) -> str:
    lines = [f"=== GraphRAG Context for {story_id} ==="]

    if files:
        lines.append(f"\nImpacted files ({len(files)}):")
        lines.extend(f"  • {f}" for f in files[:20])

    if tests:
        lines.append(f"\nRelated tests ({len(tests)}):")
        lines.extend(f"  • {t}" for t in tests[:20])

    if modules:
        lines.append(f"\nModules: {', '.join(modules)}")

    if constraints:
        lines.append("\nArchitectural constraints:")
        lines.extend(f"  [!] {c}" for c in constraints)

    if entities:
        lines.append(f"\nRelated entities ({len(entities)}):")
        for e in entities[:25]:
            lines.append(f"  • {e.to_prompt_line()}")
        if len(entities) > 25:
            lines.append(f"  ... (+{len(entities) - 25} more)")

    if relations:
        lines.append(f"\nRelations ({len(relations)}):")
        for r in relations[:30]:
            lines.append(f"  • {r.to_prompt_line()}")
        if len(relations) > 30:
            lines.append(f"  ... (+{len(relations) - 30} more)")

    if len(lines) == 1:
        lines.append("  (no data found for this story)")

    return "\n".join(lines)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value:
        return [value]
    return []


def _dedup(items: List[str]) -> List[str]:
    seen: set = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
