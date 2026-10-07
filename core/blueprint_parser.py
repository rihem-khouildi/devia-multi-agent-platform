"""
Parser pour les blueprints JSON.
Extrait les informations du blueprint pour créer un AnalysisResult.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.models import (
    AnalysisResult, Entity, EntityField, Endpoint, GherkinScenario
)
from core.exceptions import BlueprintParseError
from utils.logger import get_logger

logger = get_logger(__name__)


class BlueprintParser:
    """
    Parse un blueprint JSON et retourne un AnalysisResult.

    Structure attendue du blueprint:
    - requirements.functional_requirements → business rules
    - api_design.endpoints → endpoints REST
    - api_design.openapi_spec → spécification OpenAPI
    - architecture.nodes → composants (controller, service, etc.)
    - domain_model.entities → entités JPA
    - documentation.tech_stack → tech stack
    """

    def parse(self, blueprint: Dict[str, Any]) -> AnalysisResult:
        """Parse un blueprint JSON en AnalysisResult."""
        try:
            return AnalysisResult(
                entities=self._parse_entities(blueprint),
                endpoints=self._parse_endpoints(blueprint),
                gherkin_scenarios=self._parse_gherkin_scenarios(blueprint),
                architecture_notes=self._parse_architecture_notes(blueprint),
                package_base=self._parse_package_base(blueprint),
                service_name=self._parse_service_name(blueprint),
                dependencies=self._parse_dependencies(blueprint),
                business_rules=self._parse_business_rules(blueprint),
            )
        except Exception as e:
            raise BlueprintParseError(f"Erreur lors du parsing du blueprint: {e}")

    def parse_file(self, file_path: Path) -> AnalysisResult:
        """Parse un fichier blueprint JSON."""
        try:
            content = file_path.read_text(encoding="utf-8")
            blueprint = json.loads(content)
            logger.info(f"  Blueprint chargé: {file_path.name}")
            return self.parse(blueprint)
        except json.JSONDecodeError as e:
            raise BlueprintParseError(f"JSON invalide dans {file_path}: {e}")
        except FileNotFoundError:
            raise BlueprintParseError(f"Blueprint introuvable: {file_path}")

    def _parse_entities(self, blueprint: Dict) -> List[Entity]:
        """Extrait les entités depuis domain_model.entities."""
        entities = []
        domain_model = blueprint.get("domain_model", {})

        for entity_data in domain_model.get("entities", []):
            fields = [
                EntityField(
                    name=f.get("name", ""),
                    type=self._map_type(f.get("type", "String")),
                    nullable=f.get("nullable", True),
                    unique=f.get("unique", False),
                    description=f.get("description", ""),
                )
                for f in entity_data.get("fields", [])
            ]

            entities.append(Entity(
                name=entity_data.get("name", ""),
                fields=fields,
                relations=entity_data.get("relations", []),
                business_rules=entity_data.get("business_rules", []),
            ))

        # Si pas d'entités dans domain_model, créer depuis les bounded_contexts
        if not entities:
            for bc in domain_model.get("bounded_contexts", []):
                for entity_data in bc.get("entities", []):
                    entities.append(Entity(
                        name=entity_data.get("name", bc.get("name", "")),
                        fields=[],
                        relations=[],
                        business_rules=[],
                    ))

        return entities

    def _parse_endpoints(self, blueprint: Dict) -> List[Endpoint]:
        """Extrait les endpoints depuis api_design.endpoints ou openapi_spec."""
        endpoints = []
        api_design = blueprint.get("api_design", {})

        # Essayer d'abord endpoints directs
        for ep_data in api_design.get("endpoints", []):
            endpoints.append(Endpoint(
                method=ep_data.get("method", "GET"),
                path=ep_data.get("path", "/"),
                description=ep_data.get("description", ""),
                request_body=ep_data.get("request_body"),
                response_body=ep_data.get("response_body"),
                validations=ep_data.get("validations", []),
            ))

        # Si pas d'endpoints, extraire depuis openapi_spec.paths
        if not endpoints:
            openapi = api_design.get("openapi_spec", {})
            for path, methods in openapi.get("paths", {}).items():
                for method, details in methods.items():
                    if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        endpoints.append(Endpoint(
                            method=method.upper(),
                            path=path,
                            description=details.get("description", details.get("summary", "")),
                            request_body=None,
                            response_body=None,
                            validations=[],
                        ))

        return endpoints

    def _parse_gherkin_scenarios(self, blueprint: Dict) -> List[GherkinScenario]:
        """Génère des scénarios Gherkin depuis les requirements."""
        scenarios = []
        requirements = blueprint.get("requirements", {})

        # Créer un scénario pour chaque requirement fonctionnel
        for fr in requirements.get("functional_requirements", []):
            description = fr.get("description", "")
            if description:
                scenarios.append(GherkinScenario(
                    feature=blueprint.get("project_name", "Feature"),
                    scenario=f"FR-{fr.get('id', 'XXX')}: {description[:50]}...",
                    given=["the system is running"],
                    when=["the user performs the action"],
                    then=[description],
                ))

        return scenarios

    def _parse_architecture_notes(self, blueprint: Dict) -> str:
        """Extrait les notes d'architecture."""
        arch = blueprint.get("architecture", {})
        metadata = arch.get("metadata", {})

        notes = []
        if metadata.get("description"):
            notes.append(metadata["description"])

        patterns = arch.get("patterns", [])
        if patterns:
            notes.append(f"Patterns: {', '.join(patterns)}")

        doc = blueprint.get("documentation", {})
        if doc.get("overview"):
            notes.append(doc["overview"])

        return " | ".join(notes) if notes else "Standard layered architecture"

    def _parse_package_base(self, blueprint: Dict) -> str:
        """Extrait le package base depuis architecture.nodes."""
        arch = blueprint.get("architecture", {})

        for node in arch.get("nodes", []):
            props = node.get("properties", {})
            package = props.get("package", "")
            if package:
                # Retirer le dernier segment (ex: com.example.app.api -> com.example.app)
                parts = package.rsplit(".", 1)
                return parts[0] if len(parts) > 1 else package

        return "com.example.app"

    def _parse_service_name(self, blueprint: Dict) -> str:
        """Extrait le nom du service."""
        # Essayer depuis architecture.nodes
        arch = blueprint.get("architecture", {})
        for node in arch.get("nodes", []):
            label = node.get("label", "")
            if "Service" in label:
                return label.replace("Service", "")

        # Fallback sur project_name
        project_name = blueprint.get("project_name", "Generated")
        # Convertir en PascalCase
        return "".join(word.capitalize() for word in project_name.replace("-", " ").replace("_", " ").split())

    def _parse_dependencies(self, blueprint: Dict) -> List[str]:
        """Extrait les dépendances depuis documentation.tech_stack."""
        dependencies = ["spring-boot-starter-web"]

        tech_stack = blueprint.get("documentation", {}).get("tech_stack", {})

        if tech_stack.get("database") and tech_stack["database"] != "None":
            dependencies.append("spring-boot-starter-data-jpa")

        if tech_stack.get("messaging") and tech_stack["messaging"] != "None":
            dependencies.append("spring-boot-starter-amqp")

        return dependencies

    def _parse_business_rules(self, blueprint: Dict) -> List[str]:
        """Extrait les règles métier depuis requirements."""
        rules = []
        requirements = blueprint.get("requirements", {})

        for fr in requirements.get("functional_requirements", []):
            if fr.get("priority") == "MUST":
                rules.append(fr.get("description", ""))

        for nfr in requirements.get("non_functional_requirements", []):
            rules.append(nfr.get("description", ""))

        return [r for r in rules if r]

    def _map_type(self, type_str: str) -> str:
        """Mappe les types du blueprint vers les types Java."""
        type_map = {
            "string": "String",
            "integer": "Integer",
            "long": "Long",
            "boolean": "Boolean",
            "date": "LocalDate",
            "datetime": "LocalDateTime",
            "decimal": "BigDecimal",
            "uuid": "UUID",
        }
        return type_map.get(type_str.lower(), type_str)
