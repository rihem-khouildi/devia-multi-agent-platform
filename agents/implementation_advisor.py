"""
Agent Implementation Advisor
=============================
Analyse les spécifications (US + documentation) et produit:
- Liste des entités JPA avec champs et relations
- Liste des endpoints REST
- Scénarios Gherkin
- Notes d'architecture
- Plan d'implémentation pour le Developer Agent

Si un blueprint JSON existe dans docs/, il est utilisé directement
pour éviter de redemander au LLM ce qui est déjà spécifié.
"""

import json
import os
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import (
    UserStory, AnalysisResult, Entity, EntityField,
    Endpoint, GherkinScenario
)
from core.blueprint_parser import BlueprintParser
from core.exceptions import BlueprintParseError
from utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
Tu es un architecte logiciel senior expert en Java Spring Boot, DDD (Domain-Driven Design) et Clean Architecture.
Tu analyses des User Stories et de la documentation technique pour produire un plan d'implémentation structuré.

═══════════════════════════════════════════════════════════
RÈGLES STRICTES D'ARCHITECTURE
═══════════════════════════════════════════════════════════

1. CONVENTIONS DE NOMMAGE:
   ✓ Classes: PascalCase (UserService, OrderController, ProductEntity)
   ✓ Méthodes: camelCase (findById, createUser, updateOrder)
   ✓ Packages: lowercase avec points (com.company.project.domain)

2. ARCHITECTURE EN COUCHES (Clean Architecture):
   ✓ Controller → Service → Repository → Entity
   ✓ Controller: expose les endpoints REST
   ✓ Service: contient la logique métier
   ✓ Repository: accès aux données
   ✓ Entity: modèle de domaine JPA

3. TYPES JAVA POUR LES CHAMPS D'ENTITÉ:
   ✓ String, Long, Integer, Boolean, LocalDateTime, LocalDate
   ✓ BigDecimal (pour les montants monétaires)
   ✓ UUID (pour les identifiants uniques)
   ✓ Enum (pour les statuts/types)

4. ENDPOINTS REST (conventions RESTful):
   ✓ Pluriel: /api/v1/users, /api/v1/orders
   ✓ kebab-case pour les segments: /api/v1/order-items
   ✓ Méthodes HTTP standard: GET, POST, PUT, DELETE, PATCH
   ✓ Chemins cohérents: /api/v1/users/{id}/orders

5. STACK TECHNIQUE (Spring Boot 3.2 + Java 23):
   ✓ Spring Boot 3.2 → jakarta.* (JAMAIS javax.*)
   ✓ Spring Web → org.springframework.web.bind.annotation.*
   ✓ JPA → jakarta.persistence.*
   ✓ Validation → jakarta.validation.constraints.*
   ✓ Lombok → lombok.Data, lombok.Builder, lombok.RequiredArgsConstructor
   ✓ OpenAPI → io.swagger.v3.oas.annotations.*

═══════════════════════════════════════════════════════════
IMPORTANT
═══════════════════════════════════════════════════════════
- Respecte EXACTEMENT les conventions de nommage Java
- Respecte l'architecture en couches
- Génère des entités JPA réalistes avec les bons types Java
- Les endpoints suivent les conventions REST
- Prends en compte toutes les règles métier de la documentation

FORMAT DE RÉPONSE: Tu réponds UNIQUEMENT avec un JSON valide selon le schéma fourni, sans texte avant ou après.
""".strip()


class ImplementationAdvisorAgent(BaseAgent):
    """Agent qui analyse les specs et produit un plan d'implémentation.

    Si un blueprint JSON est fourni dans docs, il est utilisé directement.
    Sinon, le LLM analyse la documentation pour produire le plan.
    """

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config, "ImplementationAdvisor", model=config.model_advisor)
        self.blueprint_parser = BlueprintParser()
        logger.info(f"   ImplementationAdvisor → modèle: {self.model}")

    async def analyze(
        self,
        user_story: UserStory,
        docs: Dict[str, str],
        blueprint: Optional[Dict] = None,
    ) -> AnalysisResult:
        """
        Analyse la US et la documentation pour produire un plan technique.

        Si un blueprint est fourni, il est parsé directement sans appel LLM.
        Sinon, le LLM analyse la documentation.
        """
        logger.info(f"   Analyse de: {user_story.id}")

        # Si blueprint fourni, l'utiliser directement
        if blueprint:
            try:
                logger.info("   → Utilisation du blueprint JSON (pas d'appel LLM)")
                return self.blueprint_parser.parse(blueprint)
            except BlueprintParseError as e:
                logger.warning(f"   Blueprint invalide, fallback sur LLM: {e}")

        # Sinon, utiliser le LLM
        logger.info("   → Analyse via LLM")
        formatted_docs = self._format_docs(docs)
        user_message = self._build_prompt(user_story, formatted_docs)

        raw_response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4096,
        )

        return self._parse_response(raw_response)

    def _build_prompt(self, user_story: UserStory, docs: str) -> str:
        schema = json.dumps(self._response_schema(), indent=2)
        compact_story = (
            f"ID: {user_story.id}\n"
            f"Title: {user_story.title}\n"
            f"Description: {user_story.description[:600]}\n"
            f"Acceptance Criteria:\n"
            + "\n".join(f"- {c}" for c in user_story.acceptance_criteria[:10])
        )
        return f"""
Analyse cette User Story et la documentation technique fournie pour produire un plan d'implémentation Java Spring Boot complet.

## USER STORY
{compact_story}

## DOCUMENTATION TECHNIQUE
{docs}

## SCHÉMA DE RÉPONSE ATTENDU
Réponds avec un JSON respectant exactement ce schéma:
{schema}

IMPORTANT — PLAN D'IMPLÉMENTATION:
- `package_base`: ex "com.company.project" (détermine depuis la documentation ou utilise "com.example.app")
- `service_name`: nom métier principal (ex: "Order", "Customer", "Product")
- `entities`: toutes les entités JPA nécessaires
- `endpoints`: tous les endpoints REST selon les critères d'acceptation
- `business_rules`: règles métier extraites de la documentation
- `gherkin_scenarios`: scénarios de test au format Gherkin
- N'ajoute PAS d'endpoints CRUD génériques non demandés par les critères d'acceptation
- Si la user story porte sur une consultation, retourne seulement les endpoints strictement nécessaires
- Fais apparaître explicitement les statuts par défaut, relations obligatoires et champs d'identification métier

IMPORTANT — TEST CONTRACT (champ `test_cases`):
- Génère un test contract STRICT basé uniquement sur les Acceptance Criteria.
- Chaque test case doit correspondre à un comportement observable explicitement demandé.
- target_layer doit être: "dto", "validation", "service", "controller", ou "repository"
- N'inclus "repository" UNIQUEMENT si la US mentionne explicitement persistence/database/repository.
- Pour les DTO avec validation (@NotBlank, @Email...), utilise target_layer="validation" et validation_expected=true.
  Ces tests utilisent Jakarta Validator.validate(), JAMAIS assertThrows sur constructeur.
- Pour les controllers, indique expected_status (200, 201, 400, 401...).
- Pour les services, teste uniquement la logique métier explicite dans la US.
- Maximum 6 test cases. Préfère 3 tests fiables à 8 tests inventés.
- Ne génère PAS de test hors scope (ex: pas de UserRepositoryTest pour une US de login).
""".strip()

    def _response_schema(self) -> dict:
        return {
            "package_base": "com.company.project",
            "service_name": "ResourceName",
            "architecture_notes": "Description de l'architecture choisie",
            "dependencies": ["spring-boot-starter-web", "spring-boot-starter-data-jpa"],
            "business_rules": ["Règle 1", "Règle 2"],
            "test_cases": [
                {
                    "id": "TC1",
                    "title": "Valid request object is created correctly",
                    "target_class": "AuthenticationRequest",
                    "target_layer": "dto",
                    "scenario": "constructor creates object with accessible fields",
                    "given": "valid username and password",
                    "when": "AuthenticationRequest is instantiated",
                    "then": "getUsername() and getPassword() return expected values",
                    "input_data": {"username": "john", "password": "pass123"},
                    "expected_result": {"valid": True},
                    "should_generate": True
                },
                {
                    "id": "TC2",
                    "title": "Blank username triggers validation violation",
                    "target_class": "AuthenticationRequest",
                    "target_layer": "validation",
                    "scenario": "blank username violates @NotBlank",
                    "given": "AuthenticationRequest with blank username",
                    "when": "Jakarta Validator validates the request",
                    "then": "at least one ConstraintViolation is returned",
                    "input_data": {"username": "", "password": "pass123"},
                    "expected_result": {"validation_error": True},
                    "validation_expected": True,
                    "should_generate": True
                }
            ],
            "entities": [
                {
                    "name": "EntityName",
                    "fields": [
                        {
                            "name": "fieldName",
                            "type": "String|Long|Integer|Boolean|LocalDateTime|BigDecimal|UUID",
                            "nullable": True,
                            "unique": False,
                            "description": "Description du champ"
                        }
                    ],
                    "relations": [
                        {
                            "type": "ManyToOne|OneToMany|ManyToMany|OneToOne",
                            "target": "TargetEntity",
                            "field": "fieldName",
                            "description": "Description de la relation"
                        }
                    ],
                    "business_rules": ["Règle spécifique à l'entité"]
                }
            ],
            "endpoints": [
                {
                    "method": "GET|POST|PUT|DELETE|PATCH",
                    "path": "/api/v1/resources/{id}",
                    "description": "Description de l'endpoint",
                    "request_body": {"field": "type"},
                    "response_body": {"field": "type"},
                    "validations": ["@NotNull field", "@Size(min=1, max=255) name"]
                }
            ],
            "gherkin_scenarios": [
                {
                    "feature": "Feature name",
                    "scenario": "Scenario description",
                    "given": ["context step"],
                    "when": ["action step"],
                    "then": ["expected outcome"]
                }
            ]
        }

    def _parse_response(self, raw: str) -> AnalysisResult:
        """Parse la réponse JSON de Claude en AnalysisResult."""
        data = self.extract_json(raw)
        
        entities = [
            Entity(
                name=e["name"],
                fields=[
                    EntityField(
                        name=f["name"],
                        type=f["type"],
                        nullable=f.get("nullable", True),
                        unique=f.get("unique", False),
                        description=f.get("description", ""),
                    )
                    for f in e.get("fields", [])
                ],
                relations=e.get("relations", []),
                business_rules=e.get("business_rules", []),
            )
            for e in data.get("entities", [])
        ]
        
        endpoints = [
            Endpoint(
                method=ep["method"],
                path=ep["path"],
                description=ep["description"],
                request_body=ep.get("request_body"),
                response_body=ep.get("response_body"),
                validations=ep.get("validations", []),
            )
            for ep in data.get("endpoints", [])
        ]
        
        scenarios = [
            GherkinScenario(
                feature=s["feature"],
                scenario=s["scenario"],
                given=s.get("given", []),
                when=s.get("when", []),
                then=s.get("then", []),
            )
            for s in data.get("gherkin_scenarios", [])
        ]
        
        # Extract and validate test_contract cases.
        # We sanitize here to avoid propagating invalid layer values downstream.
        raw_test_cases = data.get("test_cases", [])
        valid_layers = {"dto", "validation", "service", "controller", "repository"}
        test_contract: List[dict] = []
        for tc in raw_test_cases:
            if not isinstance(tc, dict):
                continue
            layer = str(tc.get("target_layer", "service")).lower()
            if layer not in valid_layers:
                layer = "service"
            test_contract.append({
                "id": str(tc.get("id", f"TC{len(test_contract)+1}")),
                "title": str(tc.get("title", "")),
                "target_class": str(tc.get("target_class", "")),
                "target_layer": layer,
                "scenario": str(tc.get("scenario", "")),
                "given": str(tc.get("given", "")),
                "when": str(tc.get("when", "")),
                "then": str(tc.get("then", "")),
                "input_data": dict(tc.get("input_data") or {}),
                "expected_result": dict(tc.get("expected_result") or {}),
                "expected_status": tc.get("expected_status"),
                "validation_expected": bool(tc.get("validation_expected", False)),
                "should_generate": bool(tc.get("should_generate", True)),
            })
        logger.info(f"   Test contract extracted: {len(test_contract)} test case(s)")

        return AnalysisResult(
            entities=entities,
            endpoints=endpoints,
            gherkin_scenarios=scenarios,
            architecture_notes=data.get("architecture_notes", ""),
            package_base=data.get("package_base", "com.example.app"),
            service_name=data.get("service_name", "Resource"),
            dependencies=data.get("dependencies", []),
            business_rules=data.get("business_rules", []),
            test_contract=test_contract,
        )

    def _format_docs(self, docs: Dict[str, str], max_chars: int = 40000) -> str:
        """Formate la documentation pour le prompt."""
        max_chars = int(os.getenv("ADVISOR_MAX_DOC_CHARS", str(max_chars)))
        if not docs:
            return "Aucune documentation fournie."
        priority = ["analysis/", "architecture/", "gherkin/", "schemas/", "uml/", "root/"]
        ordered_docs: List[tuple[str, str]] = []
        for prefix in priority:
            for path, content in docs.items():
                if path.startswith(prefix):
                    ordered_docs.append((path, content))

        seen = set()
        sections = []
        total = 0
        for path, content in ordered_docs:
            if path in seen:
                continue
            seen.add(path)
            snippet = content[:1200]
            section = f"\n### {path}\n{snippet}\n"
            if total + len(section) > max_chars:
                break
            sections.append(section)
            total += len(section)
        return "\n".join(sections)
