"""
GraphRAG JSON loader — normalizes external knowledge graph exports into
a lightweight internal structure consumed by pipeline agents.

Expected input formats (auto-detected):
  1. {entities: [...], relations: [...], ...}       ← standard export
  2. {nodes: [...], edges: [...], ...}              ← graph-tool / networkx export
  3. [{id, type, properties, ...}, ...]             ← flat node list

Internal structure: GraphRAGContext (frozen, safe to pass to LLM prompts)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────
#  Internal models
# ─────────────────────────────────────────────

@dataclass
class GraphRAGEntity:
    id: str
    name: str
    type: str                          # e.g. "class", "service", "module", "concept"
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    user_story_refs: List[str] = field(default_factory=list)  # Jira IDs linked

    def to_prompt_line(self) -> str:
        desc = f" — {self.description}" if self.description else ""
        return f"[{self.type.upper()}] {self.name}{desc}"


@dataclass
class GraphRAGRelation:
    source: str
    target: str
    relation_type: str                 # e.g. "uses", "extends", "implements", "depends_on"
    description: str = ""

    def to_prompt_line(self) -> str:
        return f"{self.source} --[{self.relation_type}]--> {self.target}"


@dataclass
class GraphRAGContext:
    """
    Normalized GraphRAG knowledge ready for agent consumption.
    All fields are plain Python so they serialize to JSON easily.
    """
    source_file: str
    entities: List[GraphRAGEntity] = field(default_factory=list)
    relations: List[GraphRAGRelation] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    # ── query helpers ───────────────────────────────────────────────

    def entities_by_type(self, entity_type: str) -> List[GraphRAGEntity]:
        return [e for e in self.entities if e.type.lower() == entity_type.lower()]

    def filter_for_story(self, story_id: str) -> "GraphRAGContext":
        """Return a reduced context relevant to a specific user story."""
        relevant_entities = [
            e for e in self.entities
            if not e.user_story_refs or story_id in e.user_story_refs
        ]
        entity_names = {e.name for e in relevant_entities}
        relevant_relations = [
            r for r in self.relations
            if r.source in entity_names or r.target in entity_names
        ]
        return GraphRAGContext(
            source_file=self.source_file,
            entities=relevant_entities,
            relations=relevant_relations,
            raw_metadata=self.raw_metadata,
        )

    def to_prompt_snippet(self, max_entities: int = 30, max_relations: int = 40) -> str:
        """Compact text block safe to inject into an LLM prompt."""
        lines: List[str] = ["=== GraphRAG Knowledge Context ==="]
        if self.entities:
            lines.append("\nEntities:")
            for e in self.entities[:max_entities]:
                lines.append(f"  • {e.to_prompt_line()}")
            if len(self.entities) > max_entities:
                lines.append(f"  ... (+{len(self.entities) - max_entities} more)")
        if self.relations:
            lines.append("\nRelations:")
            for r in self.relations[:max_relations]:
                lines.append(f"  • {r.to_prompt_line()}")
            if len(self.relations) > max_relations:
                lines.append(f"  ... (+{len(self.relations) - max_relations} more)")
        if not self.entities and not self.relations:
            lines.append("  (no data)")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "entity_count": len(self.entities),
            "relation_count": len(self.relations),
            "entities": [
                {
                    "id": e.id, "name": e.name, "type": e.type,
                    "description": e.description,
                    "user_story_refs": e.user_story_refs,
                }
                for e in self.entities
            ],
            "relations": [
                {
                    "source": r.source, "target": r.target,
                    "relation_type": r.relation_type, "description": r.description,
                }
                for r in self.relations
            ],
        }

    def summary(self) -> str:
        types = {}
        for e in self.entities:
            types[e.type] = types.get(e.type, 0) + 1
        type_str = ", ".join(f"{v} {k}" for k, v in sorted(types.items()))
        return (
            f"{len(self.entities)} entities ({type_str or 'none'}), "
            f"{len(self.relations)} relations"
        )


# ─────────────────────────────────────────────
#  Parser
# ─────────────────────────────────────────────

class GraphRAGLoader:
    """Loads and normalizes a GraphRAG JSON export."""

    def load_file(self, path: str | Path) -> GraphRAGContext:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"GraphRAG file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._parse(data, source_file=str(path))

    def load_dict(self, data: Dict[str, Any], source_file: str = "<inline>") -> GraphRAGContext:
        return self._parse(data, source_file=source_file)

    # ── internal ────────────────────────────────────────────────────

    def _parse(self, data: Any, source_file: str) -> GraphRAGContext:
        entities: List[GraphRAGEntity] = []
        relations: List[GraphRAGRelation] = []
        metadata: Dict[str, Any] = {}

        if isinstance(data, list):
            # flat node list
            entities = self._parse_node_list(data)
        elif isinstance(data, dict):
            metadata = {k: v for k, v in data.items()
                        if k not in ("entities", "nodes", "relations", "edges", "links")}
            # detect format
            if "entities" in data:
                entities = self._parse_entity_list(data["entities"])
                relations = self._parse_relation_list(
                    data.get("relations", data.get("edges", data.get("links", [])))
                )
            elif "nodes" in data:
                entities = self._parse_node_list(data["nodes"])
                relations = self._parse_relation_list(data.get("edges", data.get("links", [])))
            else:
                # try to infer from keys
                entities = self._infer_entities(data)

        return GraphRAGContext(
            source_file=source_file,
            entities=entities,
            relations=relations,
            raw_metadata=metadata,
        )

    def _parse_entity_list(self, items: List[Any]) -> List[GraphRAGEntity]:
        result = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("id", item.get("entity_id", f"e{i}")))
            name = item.get("name", item.get("label", item.get("title", entity_id)))
            etype = item.get("type", item.get("entity_type", item.get("category", "concept")))
            desc = item.get("description", item.get("desc", item.get("summary", "")))
            refs = item.get("user_story_refs", item.get("stories", item.get("jira_refs", [])))
            props = {k: v for k, v in item.items()
                     if k not in ("id", "entity_id", "name", "label", "title",
                                  "type", "entity_type", "category",
                                  "description", "desc", "summary",
                                  "user_story_refs", "stories", "jira_refs")}
            result.append(GraphRAGEntity(
                id=entity_id, name=str(name), type=str(etype).lower(),
                description=str(desc), properties=props,
                user_story_refs=[str(r) for r in refs] if isinstance(refs, list) else [],
            ))
        return result

    def _parse_node_list(self, items: List[Any]) -> List[GraphRAGEntity]:
        """Same as entity list but handles graph-tool / networkx node format."""
        result = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            props = item.get("properties", item.get("data", item.get("attrs", {}))) or {}
            entity_id = str(item.get("id", item.get("node_id", f"n{i}")))
            name = props.get("name", item.get("label", item.get("name", entity_id)))
            etype = props.get("type", item.get("type", item.get("group", "concept")))
            desc = props.get("description", item.get("description", ""))
            refs = props.get("user_story_refs", [])
            result.append(GraphRAGEntity(
                id=entity_id, name=str(name), type=str(etype).lower(),
                description=str(desc), properties=props,
                user_story_refs=[str(r) for r in refs] if isinstance(refs, list) else [],
            ))
        return result

    def _parse_relation_list(self, items: List[Any]) -> List[GraphRAGRelation]:
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", item.get("from", item.get("src", ""))))
            target = str(item.get("target", item.get("to", item.get("dst", ""))))
            rtype = item.get("relation_type", item.get("type", item.get("label", item.get("relation", "related_to"))))
            desc = item.get("description", item.get("desc", ""))
            if source and target:
                result.append(GraphRAGRelation(
                    source=source, target=target,
                    relation_type=str(rtype), description=str(desc),
                ))
        return result

    def _infer_entities(self, data: Dict[str, Any]) -> List[GraphRAGEntity]:
        """Last resort: treat top-level string keys as entity names."""
        result = []
        for i, (key, val) in enumerate(data.items()):
            desc = str(val) if not isinstance(val, (dict, list)) else ""
            result.append(GraphRAGEntity(
                id=f"inferred-{i}", name=key, type="concept",
                description=desc[:200],
            ))
        return result


# ─────────────────────────────────────────────
#  Module-level helper
# ─────────────────────────────────────────────

_loader = GraphRAGLoader()


def load_graphrag(path: str | Path) -> GraphRAGContext:
    """Convenience function — loads a GraphRAG JSON file."""
    return _loader.load_file(path)


def load_graphrag_dict(data: Dict[str, Any]) -> GraphRAGContext:
    """Load from an already-parsed dict."""
    return _loader.load_dict(data)
