"""
Agent Developer (refactorisé)
==============================
Génère UNIQUEMENT la logique métier spécifique à la US:
  - Entities JPA
  - Repositories
  - DTOs (Request + Response)
  - Service interface + ServiceImpl
  - Controller REST

Tout le boilerplate (Application, Config, Exceptions, pom.xml)
est généré par JavaTemplateEngine en Python pur — sans LLM.
"""

import json
import os
import re
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import UserStory, AnalysisResult, GeneratedCode, PlanResult, SubTask, RepoAnalysis
from core.java_template_engine import JavaTemplateEngine
from utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
Tu es un développeur Java senior expert en Spring Boot 3.x et Clean Architecture.
Tu génères UNIQUEMENT la logique métier d'un projet Spring Boot existant.

═══════════════════════════════════════════════════════════
CONTEXTE DU PROJET (déjà présent, NE PAS RE-GÉNÉRER):
═══════════════════════════════════════════════════════════
- Application.java            ✅ déjà généré par JavaTemplateEngine
- OpenApiConfig.java          ✅ déjà généré par JavaTemplateEngine
- GlobalExceptionHandler.java ✅ déjà généré par JavaTemplateEngine
- ResourceNotFoundException   ✅ déjà généré par JavaTemplateEngine
- BusinessException           ✅ déjà généré par JavaTemplateEngine
- ErrorResponse               ✅ déjà généré par JavaTemplateEngine
- application.properties      ✅ déjà généré par JavaTemplateEngine
- pom.xml                     ✅ déjà généré par JavaTemplateEngine

═══════════════════════════════════════════════════════════
TON RÔLE: générer UNIQUEMENT les fichiers métier suivants
═══════════════════════════════════════════════════════════
✓ Entities JPA (@Entity, @Table, @Id, @GeneratedValue)
✓ Repositories (extends JpaRepository<Entity, ID>)
✓ DTOs Request/Response (classes immuables avec Lombok)
✓ Service interface (contrat métier avec Javadoc)
✓ ServiceImpl (@Service, @Transactional, logique métier)
✓ Controller REST (@RestController, tous les endpoints)

═══════════════════════════════════════════════════════════
RÈGLES ABSOLUES - Spring Boot 3.2 + Java 21 + Jakarta EE
═══════════════════════════════════════════════════════════

1. JAKARTA EE (JAMAIS javax.*):
   ✓ imports jakarta.persistence explicites
   ✓ imports jakarta.validation.constraints explicites
   ✗ JAMAIS: javax.persistence.*, javax.validation.*

2. LOMBOK (imports explicites OBLIGATOIRES):
   ✓ import lombok.Data;
   ✓ import lombok.Builder;
   ✓ import lombok.AllArgsConstructor;
   ✓ import lombok.NoArgsConstructor;
   ✓ import lombok.RequiredArgsConstructor;
   ✓ import lombok.Getter;
   ✓ import lombok.Setter;

3. INJECTION PAR CONSTRUCTEUR (@RequiredArgsConstructor):
   ✓ @Service
   ✓ @RequiredArgsConstructor
   ✓ public class UserServiceImpl {
   ✓     private final UserRepository userRepository;
   ✗ JAMAIS: @Autowired sur les champs

4. EXCEPTIONS RUNTIME (étendent RuntimeException):
   ✓ throw new ResourceNotFoundException("User", "id", userId);
   ✓ throw new BusinessException("Invalid operation");
   ✗ JAMAIS: jakarta.ws.rs.WebApplicationException
   ✗ JAMAIS: jakarta.ws.rs.core.Response

5. SPRING WEB (JAMAIS JAX-RS):
   ✓ imports org.springframework.web.bind.annotation explicites
   ✓ @RestController, @GetMapping, @PostMapping, etc.
   ✓ ResponseEntity<T>
   ✗ JAMAIS: jakarta.ws.rs.@Path, @GET, @POST, etc.

6. SWAGGER (springdoc-openapi):
   ✓ import io.swagger.v3.oas.annotations.Operation;
   ✓ import io.swagger.v3.oas.annotations.tags.Tag;
   ✗ JAMAIS: springfox.documentation.*

7. TRANSACTIONS:
   ✓ @Transactional sur les méthodes de service
   ✓ import org.springframework.transaction.annotation.Transactional;

8. VALIDATION:
   ✓ @Valid sur les @RequestBody
   ✓ @NotNull, @NotBlank, @Size, @Email sur les DTOs

═══════════════════════════════════════════════════════════
IMPORTS TYPES PAR FICHIER (copier exactement)
═══════════════════════════════════════════════════════════

ENTITY:
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

REPOSITORY:
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

DTO:
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

SERVICE:
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

CONTROLLER:
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

═══════════════════════════════════════════════════════════
IMPORTANT
═══════════════════════════════════════════════════════════
- NE crée PAS de classes avec de nouveaux noms (réutilise les DTOs existants)
- Utilise EXACTEMENT le package spécifié dans la demande
- Assure la cohérence entre imports, types de retour et constructeurs
- Tous les DTOs doivent être uniques et réutilisés dans tous les endpoints

FORMAT DE RÉPONSE: ```java:src/main/java/chemin/complet/Fichier.java
""".strip()


class DeveloperAgent(BaseAgent):
    _WILDCARD_IMPORT_REPLACEMENTS = {
        "import jakarta.persistence.*;": [
            "import jakarta.persistence.Column;",
            "import jakarta.persistence.Entity;",
            "import jakarta.persistence.GeneratedValue;",
            "import jakarta.persistence.GenerationType;",
            "import jakarta.persistence.Id;",
            "import jakarta.persistence.JoinColumn;",
            "import jakarta.persistence.JoinTable;",
            "import jakarta.persistence.ManyToMany;",
            "import jakarta.persistence.ManyToOne;",
            "import jakarta.persistence.OneToMany;",
            "import jakarta.persistence.OneToOne;",
            "import jakarta.persistence.Table;",
            "import jakarta.persistence.EnumType;",
            "import jakarta.persistence.Enumerated;",
        ],
        "import jakarta.validation.constraints.*;": [
            "import jakarta.validation.constraints.Email;",
            "import jakarta.validation.constraints.NotBlank;",
            "import jakarta.validation.constraints.NotNull;",
            "import jakarta.validation.constraints.Size;",
        ],
        "import org.springframework.web.bind.annotation.*;": [
            "import org.springframework.web.bind.annotation.DeleteMapping;",
            "import org.springframework.web.bind.annotation.GetMapping;",
            "import org.springframework.web.bind.annotation.PathVariable;",
            "import org.springframework.web.bind.annotation.PostMapping;",
            "import org.springframework.web.bind.annotation.PutMapping;",
            "import org.springframework.web.bind.annotation.RequestBody;",
            "import org.springframework.web.bind.annotation.RequestMapping;",
            "import org.springframework.web.bind.annotation.RequestParam;",
            "import org.springframework.web.bind.annotation.RestController;",
        ],
        "import lombok.*;": [
            "import lombok.AllArgsConstructor;",
            "import lombok.Builder;",
            "import lombok.Data;",
            "import lombok.Getter;",
            "import lombok.NoArgsConstructor;",
            "import lombok.RequiredArgsConstructor;",
            "import lombok.Setter;",
        ],
    }

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config, "Developer", model=config.model_developer)
        logger.info(f"  🤖 Developer → modèle: {self.model}")

    async def generate(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        docs: Dict[str, str],
    ) -> GeneratedCode:
        """Génère le projet complet : boilerplate Python + logique métier LLM."""
        logger.info(f"  ⚙️ Génération du code pour {analysis.service_name}")

        # ── 1. Boilerplate Python (toujours correct, sans LLM) ────────
        engine = JavaTemplateEngine(analysis)
        boilerplate = engine.generate_all()
        pom_xml = engine.generate_pom()
        logger.info(f"    ✓ {len(boilerplate)} fichiers boilerplate générés (Python)")

        use_llm = os.getenv("DEVELOPER_USE_LLM", "true").lower() in ("1", "true", "yes", "on")

        # ── 2. Logique métier (déterministe + option LLM ciblé) ──────
        business_files = self._generate_deterministic_business_logic(analysis)
        logger.info(f"    ✓ {len(business_files)} fichiers métier générés (déterministe)")

        if use_llm:
            llm_files = await self._generate_business_logic(user_story, analysis)
            business_files.update(llm_files)
            logger.info(f"    ✓ {len(llm_files)} fichiers métier enrichis (LLM)")

        # ── 3. Merge : boilerplate + métier ──────────────────────────
        all_files = {**boilerplate, **business_files}
        all_files = self._sanitize_generated_java_files(all_files)
        logger.info(f"  ✓ {len(all_files)} fichiers Java au total")

        return GeneratedCode(
            files=all_files,
            pom_xml=pom_xml,
            readme=self._generate_readme(analysis, user_story),
        )

    async def _generate_business_logic(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
    ) -> Dict[str, str]:
        """Génère les fichiers métier en une passe complète."""

        entities_json = json.dumps([e.to_dict() for e in analysis.entities], indent=2)
        endpoints_json = json.dumps([ep.to_dict() for ep in analysis.endpoints], indent=2)
        pkg = analysis.package_base

        logger.info("    → Génération ciblée: logique métier spécifique")
        compact_story = (
            f"ID: {user_story.id}\n"
            f"Title: {user_story.title}\n"
            f"Description: {user_story.description[:600]}\n"
            "Acceptance Criteria:\n"
            + "\n".join(f"- {c}" for c in user_story.acceptance_criteria[:10])
        )
        message = f"""
    Tu dois UNIQUEMENT compléter/affiner la logique métier spécifique.
    NE régénère pas le boilerplate CRUD standard.

## USER STORY
{compact_story}

═══════════════════════════════════════════════════════════
PACKAGE BASE (OBLIGATOIRE - utilise ce package EXACTEMENT):
═══════════════════════════════════════════════════════════
{pkg}

## SERVICE: {analysis.service_name}

## ANALYSE STRUCTURÉE - ENTITÉS
{entities_json}

## ANALYSE STRUCTURÉE - ENDPOINTS
{endpoints_json}

## RÈGLES MÉTIER
{chr(10).join(f"- {r}" for r in analysis.business_rules)}

═══════════════════════════════════════════════════════════
ORDRE DE GÉNÉRATION (ciblé):
═══════════════════════════════════════════════════════════
1. Ajouter/affiner règles métier spécifiques dans ServiceImpl
2. Ajouter validations et erreurs métier nécessaires
3. Ajouter uniquement les méthodes/customisations non triviales

═══════════════════════════════════════════════════════════
RAPPELS CRITIQUES:
═══════════════════════════════════════════════════════════
✗ NE génère PAS: Application.java, GlobalExceptionHandler, exceptions personnalisées, pom.xml, application.properties
✗ NE régénère PAS le CRUD standard déjà présent
✓ RESPECTE STRICTEMENT le package `{pkg}` pour TOUS les fichiers
✓ Utilise UNIQUEMENT jakarta.* (JAMAIS javax.*)
✓ Utilise @RequiredArgsConstructor (JAMAIS @Autowired)
✓ Exceptions étendent RuntimeException (JAMAIS jakarta.ws.rs.*)
✓ Spring Web annotations (JAMAIS jakarta.ws.rs.@Path, @GET, etc.)
✓ Imports Lombok explicites (import lombok.Data, import lombok.Builder, etc.)
✓ Implémente UNIQUEMENT les endpoints explicitement présents dans l'analyse et les critères d'acceptation
✓ N'ajoute PAS de findAll/update/delete/create génériques s'ils ne sont pas demandés
""".strip()

        response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=message,
            max_tokens=4096,
        )
        return self.extract_code_blocks(response)

    def _generate_deterministic_business_logic(self, analysis: AnalysisResult) -> Dict[str, str]:
        """Génère Entity/Repository/DTO/Service/Controller CRUD sans LLM."""
        files: Dict[str, str] = {}
        pkg = analysis.package_base
        base = f"src/main/java/{pkg.replace('.', '/')}"
        service_name = analysis.service_name or "Resource"
        entity_name = analysis.entities[0].name if analysis.entities else f"{service_name}Entity"
        response_dto = f"{service_name}Response"
        request_dto = f"{service_name}Request"
        repository_name = f"{entity_name}Repository"
        service_interface = f"{service_name}Service"
        service_impl = f"{service_name}ServiceImpl"
        controller_name = f"{service_name}Controller"

        entity_fields = []
        if analysis.entities:
            entity_fields = analysis.entities[0].fields
        if not entity_fields:
            entity_fields = []

        files[f"{base}/dto/{request_dto}.java"] = self._build_request_dto(pkg, request_dto, entity_fields)
        files[f"{base}/dto/{response_dto}.java"] = self._build_response_dto(pkg, response_dto, entity_fields)
        files[f"{base}/service/{service_interface}.java"] = self._build_service_interface(pkg, service_interface, request_dto, response_dto)
        files[f"{base}/service/impl/{service_impl}.java"] = self._build_service_impl(
            pkg, service_impl, service_interface, request_dto, response_dto, repository_name, entity_name, entity_fields
        )
        files[f"{base}/controller/{controller_name}.java"] = self._build_controller(pkg, controller_name, service_interface, request_dto, response_dto, analysis)

        for entity in analysis.entities:
            files[f"{base}/entity/{entity.name}.java"] = self._build_entity(pkg, entity)
            files[f"{base}/repository/{entity.name}Repository.java"] = self._build_repository(pkg, entity.name)

        if not analysis.entities:
            files[f"{base}/entity/{entity_name}.java"] = self._build_minimal_entity(pkg, entity_name)
            files[f"{base}/repository/{repository_name}.java"] = self._build_repository(pkg, entity_name)

        return files

    def _expand_planned_paths_with_required_business_dependencies(
        self,
        planned_paths: set,
        deterministic_files: Dict[str, str],
    ) -> set:
        """
        Keep the minimal deterministic companion files required by planned
        controllers/services/DTOs so plan-driven output stays compile-safe.
        """
        normalized = {path.replace("\\", "/") for path in planned_paths if path}
        if not normalized:
            return normalized

        expanded = set(normalized)
        available = {path.replace("\\", "/") for path in deterministic_files}
        stems = set()
        include_domain_model = False

        for path in normalized:
            filename = path.rsplit("/", 1)[-1]
            if filename.endswith("Controller.java"):
                stems.add(filename.removesuffix("Controller.java"))
                include_domain_model = True
            elif filename.endswith("ServiceImpl.java"):
                stems.add(filename.removesuffix("ServiceImpl.java"))
                include_domain_model = True
            elif filename.endswith("Service.java"):
                stems.add(filename.removesuffix("Service.java"))
                include_domain_model = True
            elif filename.endswith("Request.java"):
                stems.add(filename.removesuffix("Request.java"))
                include_domain_model = True
            elif filename.endswith("Response.java"):
                stems.add(filename.removesuffix("Response.java"))
                include_domain_model = True
            elif filename.endswith("Repository.java") or "/entity/" in path:
                include_domain_model = True

        if not stems:
            return expanded

        for path in available:
            filename = path.rsplit("/", 1)[-1]
            for stem in stems:
                if filename in {
                    f"{stem}Controller.java",
                    f"{stem}Service.java",
                    f"{stem}ServiceImpl.java",
                    f"{stem}Request.java",
                    f"{stem}Response.java",
                }:
                    expanded.add(path)

        if include_domain_model:
            for path in available:
                if "/entity/" in path or "/repository/" in path:
                    expanded.add(path)

        return expanded

    def _build_entity(self, pkg: str, entity) -> str:
        lines = [
            f"package {pkg}.entity;",
            "",
            "import jakarta.persistence.Entity;",
            "import jakarta.persistence.GeneratedValue;",
            "import jakarta.persistence.GenerationType;",
            "import jakarta.persistence.Id;",
            "import jakarta.persistence.Table;",
            "import lombok.AllArgsConstructor;",
            "import lombok.Builder;",
            "import lombok.Data;",
            "import lombok.NoArgsConstructor;",
            "",
            "@Entity",
            f"@Table(name = \"{entity.name.lower()}\")",
            "@Data",
            "@Builder",
            "@NoArgsConstructor",
            "@AllArgsConstructor",
            f"public class {entity.name} {{",
            "",
            "    @Id",
            "    @GeneratedValue(strategy = GenerationType.IDENTITY)",
            "    private Long id;",
            "",
        ]
        for field in entity.fields:
            if field.name.lower() == "id":
                continue
            java_type = field.type or "String"
            lines.append(f"    private {java_type} {field.name};")
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _build_minimal_entity(self, pkg: str, name: str) -> str:
        return f"""package {pkg}.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Entity
@Table(name = \"{name.lower()}\")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class {name} {{

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
}}
"""

    def _build_repository(self, pkg: str, entity_name: str) -> str:
        return f"""package {pkg}.repository;

import {pkg}.entity.{entity_name};
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface {entity_name}Repository extends JpaRepository<{entity_name}, Long> {{
}}
"""

    def _build_request_dto(self, pkg: str, dto_name: str, fields) -> str:
        field_names = {getattr(field, "name", "").lower() for field in fields}
        attrs = []
        default_name_block = "    @NotBlank\n    private String name;\n"
        if "name" not in field_names:
            attrs.append("    private String name;")
        else:
            default_name_block = ""
        for field in fields:
            if field.name.lower() == "id":
                continue
            attrs.append(f"    private {field.type or 'String'} {field.name};")
        attrs_block = "\n".join(self._unique_java_field_lines(attrs))
        return f"""package {pkg}.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class {dto_name} {{

{default_name_block}

{attrs_block}
}}
"""

    def _build_response_dto(self, pkg: str, dto_name: str, fields) -> str:
        field_names = {getattr(field, "name", "").lower() for field in fields}
        attrs = []
        if "id" not in field_names:
            attrs.append("    private Long id;")
        if "name" not in field_names:
            attrs.append("    private String name;")
        for field in fields:
            if field.name.lower() == "id":
                continue
            attrs.append(f"    private {field.type or 'String'} {field.name};")
        attrs_block = "\n".join(self._unique_java_field_lines(attrs))
        return f"""package {pkg}.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class {dto_name} {{

{attrs_block}
}}
"""

    def _unique_java_field_lines(self, field_lines: list[str]) -> list[str]:
        unique_lines = []
        seen_names = set()
        for line in field_lines:
            match = re.search(r"private\s+[A-Za-z_][A-Za-z0-9_<>.,? ]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", line)
            if match:
                field_name = match.group(1)
                if field_name in seen_names:
                    continue
                seen_names.add(field_name)
            elif line in unique_lines:
                continue
            unique_lines.append(line)
        return unique_lines

    def _build_service_interface(self, pkg: str, name: str, request_dto: str, response_dto: str) -> str:
        return f"""package {pkg}.service;

import {pkg}.dto.{request_dto};
import {pkg}.dto.{response_dto};

import java.util.List;

public interface {name} {{

    List<{response_dto}> findAll();

    {response_dto} findById(Long id);

    {response_dto} create({request_dto} request);

    {response_dto} update(Long id, {request_dto} request);

    void delete(Long id);
}}
"""

    def _build_service_impl(
        self,
        pkg: str,
        impl_name: str,
        interface_name: str,
        request_dto: str,
        response_dto: str,
        repository_name: str,
        entity_name: str,
        fields,
    ) -> str:
        copy_lines = [f"        entity.setName(request.getName());"]
        response_lines = ["                .id(entity.getId())", "                .name(entity.getName())"]
        for field in fields:
            fname = field.name
            if fname.lower() == "id":
                continue
            cap = fname[0].upper() + fname[1:]
            copy_lines.append(f"        entity.set{cap}(request.get{cap}());")
            response_lines.append(f"                .{fname}(entity.get{cap}())")

        copy_block = "\n".join(dict.fromkeys(copy_lines))
        response_block = "\n".join(dict.fromkeys(response_lines))

        validation_lines = [
            "        if (request == null) {",
            '            throw new BusinessException("Request must not be null");',
            "        }",
        ]
        email_field = next((field for field in fields if field.name.lower() == "email"), None)
        if email_field:
            email_cap = email_field.name[0].upper() + email_field.name[1:]
            validation_lines.extend(
                [
                    f"        if (request.get{email_cap}() == null || !request.get{email_cap}().matches(\"^[^@\\\\s]+@[^@\\\\s]+\\\\.[^@\\\\s]+$\")) {{",
                    '            throw new BusinessException("Invalid email address");',
                    "        }",
                ]
            )
        validation_block = "\n".join(validation_lines)

        return f"""package {pkg}.service.impl;

import {pkg}.dto.{request_dto};
import {pkg}.dto.{response_dto};
import {pkg}.entity.{entity_name};
import {pkg}.exception.BusinessException;
import {pkg}.exception.ResourceNotFoundException;
import {pkg}.repository.{repository_name};
import {pkg}.service.{interface_name};
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class {impl_name} implements {interface_name} {{

    private final {repository_name} repository;

    @Override
    @Transactional(readOnly = true)
    public List<{response_dto}> findAll() {{
        return repository.findAll().stream().map(this::toResponse).toList();
    }}

    @Override
    @Transactional(readOnly = true)
    public {response_dto} findById(Long id) {{
        {entity_name} entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("{entity_name}", "id", id));
        return toResponse(entity);
    }}

    @Override
    @Transactional
    public {response_dto} create({request_dto} request) {{
{validation_block}
        {entity_name} entity = new {entity_name}();
{copy_block}
        {entity_name} saved = repository.save(entity);
        return toResponse(saved != null ? saved : entity);
    }}

    @Override
    @Transactional
    public {response_dto} update(Long id, {request_dto} request) {{
{validation_block}
        {entity_name} entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("{entity_name}", "id", id));
{copy_block}
        {entity_name} saved = repository.save(entity);
        return toResponse(saved != null ? saved : entity);
    }}

    @Override
    @Transactional
    public void delete(Long id) {{
        {entity_name} entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("{entity_name}", "id", id));
        repository.delete(entity);
    }}

    private {response_dto} toResponse({entity_name} entity) {{
        return {response_dto}.builder()
{response_block}
                .build();
    }}
}}
"""

    def _build_controller(
        self,
        pkg: str,
        controller_name: str,
        service_interface: str,
        request_dto: str,
        response_dto: str,
        analysis: AnalysisResult,
    ) -> str:
        base_path = "/api/v1/resources"
        if analysis.endpoints:
            path = analysis.endpoints[0].path or base_path
            base_path = re.sub(r"\{[^}]+\}", "", path).rstrip("/") or base_path

        return f"""package {pkg}.controller;

import {pkg}.dto.{request_dto};
import {pkg}.dto.{response_dto};
import {pkg}.service.{service_interface};
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("{base_path}")
@RequiredArgsConstructor
@Tag(name = "{controller_name}", description = "CRUD endpoints")
public class {controller_name} {{

    private final {service_interface} service;

    @GetMapping
    @Operation(summary = "List all")
    public ResponseEntity<List<{response_dto}>> findAll() {{
        return ResponseEntity.ok(service.findAll());
    }}

    @GetMapping("/{{id}}")
    @Operation(summary = "Get by id")
    public ResponseEntity<{response_dto}> findById(@PathVariable Long id) {{
        return ResponseEntity.ok(service.findById(id));
    }}

    @PostMapping
    @Operation(summary = "Create")
    public ResponseEntity<{response_dto}> create(@Valid @RequestBody {request_dto} request) {{
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }}

    @PutMapping("/{{id}}")
    @Operation(summary = "Update")
    public ResponseEntity<{response_dto}> update(@PathVariable Long id, @Valid @RequestBody {request_dto} request) {{
        return ResponseEntity.ok(service.update(id, request));
    }}

    @DeleteMapping("/{{id}}")
    @Operation(summary = "Delete")
    public ResponseEntity<Void> delete(@PathVariable Long id) {{
        service.delete(id);
        return ResponseEntity.noContent().build();
    }}
}}
"""

    async def generate_from_plan(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        repo_analysis: RepoAnalysis,
        plan: PlanResult,
        docs: Dict[str, str],
        existing_code: Optional[GeneratedCode] = None,
    ) -> GeneratedCode:
        """
        Plan-driven code generation.

        Executes each SubTask in the PlanResult sequentially within each
        execution group.  Within a group, tasks that do NOT share files
        are dispatched in parallel via asyncio.gather().

        Each task generates only the files listed in `files_to_create` and
        `files_to_edit`, with a focused LLM prompt that includes only the
        relevant context — not the whole codebase.

        Returns a merged GeneratedCode. In bootstrap mode, starts from the
        deterministic boilerplate. In incremental mode, starts from the
        existing repository files and only overlays missing scaffolding and
        generated changes.
        """
        import asyncio
        logger.info(f"  ⚙️  Plan-driven generation: {len(plan.subtasks)} subtask(s)")

        engine = JavaTemplateEngine(analysis)
        boilerplate = engine.generate_all()
        deterministic = self._generate_deterministic_business_logic(analysis)
        planned_paths = {
            path.replace("\\", "/")
            for task in plan.subtasks
            for path in (task.files_to_create + task.files_to_edit)
        }
        planned_paths = self._expand_planned_paths_with_required_business_dependencies(
            planned_paths,
            deterministic,
        )
        deterministic = {
            path: content
            for path, content in deterministic.items()
            if not planned_paths or path.replace("\\", "/") in planned_paths
        }
        incremental_mode = bool(existing_code and existing_code.files)

        if incremental_mode:
            accumulated = dict(existing_code.files)
            pom_xml = existing_code.pom_xml or engine.generate_pom()
            readme = self._generate_readme(analysis, user_story)
            logger.info(f"    ✓ {len(accumulated)} existing file(s) loaded as base")

            seeded_boilerplate = 0
            for path, content in boilerplate.items():
                if path not in accumulated:
                    accumulated[path] = content
                    seeded_boilerplate += 1
            if seeded_boilerplate:
                logger.info(f"    ✓ {seeded_boilerplate} missing boilerplate file(s) seeded")

            seeded_business = 0
            for path, content in deterministic.items():
                if path not in accumulated:
                    accumulated[path] = content
                    seeded_business += 1
            logger.info(f"    ✓ {seeded_business} new deterministic business file(s) seeded")
        else:
            pom_xml = engine.generate_pom()
            readme = self._generate_readme(analysis, user_story)
            logger.info(f"    ✓ {len(boilerplate)} boilerplate file(s) (Python)")
            accumulated = {**boilerplate}
            accumulated.update(deterministic)
            accumulated = self._sanitize_generated_java_files(accumulated)
            logger.info(f"    ✓ {len(deterministic)} deterministic business file(s)")

        # 3. Execute execution groups (sequential groups, parallel within group)
        ordered_subtasks = sorted(
            [t for t in plan.subtasks if t.agent == "developer"],
            key=lambda t: (t.priority, t.id),
        )
        for group_idx, group in enumerate(plan.execution_groups):
            group_tasks = [t for t in ordered_subtasks if t.id in group]
            if not group_tasks:
                continue

            logger.info(f"    → Group {group_idx + 1}/{len(plan.execution_groups)}: "
                        f"{[t.id for t in group_tasks]}")

            # Detect intra-group file conflicts → fallback to sequential for conflicting tasks
            parallel, sequential_fallback, conflicts = self._split_by_conflicts(group_tasks)
            if parallel:
                logger.info(f"    Parallel subtasks: {[t.id for t in parallel]}")
            if sequential_fallback:
                logger.info(
                    f"    Sequential fallback: {[t.id for t in sequential_fallback]} "
                    f"| conflicts={conflicts}"
                )

            # Run parallel-safe tasks concurrently
            if parallel:
                parallel_results = await asyncio.gather(
                    *[self._execute_subtask(t, user_story, analysis, accumulated, docs)
                      for t in parallel],
                    return_exceptions=True,
                )
                successful_parallel = []
                failed_tasks = []
                for task, result in zip(parallel, parallel_results):
                    if isinstance(result, Exception):
                        logger.warning(f"    ⚠️  Subtask {task.id} failed in parallel: {result}")
                        failed_tasks.append(task)
                    elif isinstance(result, dict):
                        successful_parallel.append((task, result))

                accumulated = self._merge_task_outputs(
                    accumulated,
                    successful_parallel,
                    group_idx + 1,
                )

                # Retry failed parallel tasks sequentially before giving up
                for task in failed_tasks:
                    logger.info(f"    ↻ Retrying subtask {task.id} sequentially...")
                    try:
                        retry_files = await self._execute_subtask(
                            task, user_story, analysis, accumulated, docs
                        )
                        accumulated = self._merge_task_outputs(
                            accumulated, [(task, retry_files)], group_idx + 1
                        )
                        logger.info(f"    ✓ Subtask {task.id} recovered on sequential retry")
                    except Exception as retry_err:
                        logger.warning(
                            f"    ⚠️  Subtask {task.id} failed on retry: {retry_err} "
                            "— seeding empty stubs for missing files"
                        )
                        stubs = self._seed_missing_files(task, accumulated, analysis)
                        accumulated.update(stubs)

            # Run conflicting tasks sequentially
            for task in sequential_fallback:
                try:
                    new_files = await self._execute_subtask(
                        task, user_story, analysis, accumulated, docs
                    )
                    accumulated = self._merge_task_outputs(
                        accumulated,
                        [(task, new_files)],
                        group_idx + 1,
                    )
                except Exception as e:
                    logger.warning(f"    ⚠️  Sequential subtask {task.id} failed: {e} — seeding stubs")
                    stubs = self._seed_missing_files(task, accumulated, analysis)
                    accumulated.update(stubs)

        accumulated = self._sanitize_generated_java_files(accumulated)
        logger.info(f"  ✓ {len(accumulated)} total file(s) after plan execution")

        return GeneratedCode(
            files=accumulated,
            pom_xml=pom_xml,
            readme=readme,
        )

    async def _execute_subtask(
        self,
        task: SubTask,
        user_story: UserStory,
        analysis: AnalysisResult,
        current_files: Dict[str, str],
        docs: Dict[str, str],
    ) -> Dict[str, str]:
        """
        Execute a single SubTask via a focused LLM prompt.

        Sends only:
          - The subtask description and target files
          - The content of files_to_edit (existing code to modify)
          - Compact AnalysisResult summary (entities, endpoints)
        """
        use_llm = os.getenv("DEVELOPER_USE_LLM", "true").lower() in ("1", "true", "yes", "on")
        expected_paths = sorted(set(task.files_to_create + task.files_to_edit))

        if not expected_paths:
            raise ValueError(f"Subtask {task.id} has no target files to produce or edit")

        if not use_llm:
            # Deterministic mode: return files already accumulated from deterministic generation
            result = {}
            for path in expected_paths:
                if path in current_files:
                    result[path] = current_files[path]
            self._validate_subtask_output(task, result)
            return result

        prompt = self._build_subtask_prompt(task, user_story, analysis, current_files, expected_paths)
        response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=prompt,
            max_tokens=4096,
        )

        generated = self._extract_and_sanitize_subtask_output(response)
        try:
            self._validate_subtask_output(task, generated)
        except ValueError as first_error:
            retry_prompt = self._build_subtask_retry_prompt(
                task=task,
                user_story=user_story,
                analysis=analysis,
                current_files=current_files,
                expected_paths=expected_paths,
                validation_error=str(first_error),
                previous_response=response,
            )
            logger.warning(
                f"    Retrying subtask {task.id} with stricter output contract: {first_error}"
            )
            retry_response = await self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_message=retry_prompt,
                max_tokens=4096,
            )
            generated = self._extract_and_sanitize_subtask_output(retry_response)
            self._validate_subtask_output(task, generated)
        logger.info(f"    ✓ Subtask {task.id}: {len(generated)} file(s) generated")
        return generated

    def _build_subtask_prompt(
        self,
        task: SubTask,
        user_story: UserStory,
        analysis: AnalysisResult,
        current_files: Dict[str, str],
        expected_paths: list[str],
    ) -> str:
        existing_context = self._build_subtask_existing_context(task, current_files)
        entities_json = json.dumps([e.to_dict() for e in analysis.entities[:3]], indent=2)
        endpoints_json = json.dumps([ep.to_dict() for ep in analysis.endpoints[:5]], indent=2)
        acceptance_criteria = "\n".join(f"- {c}" for c in user_story.acceptance_criteria[:10]) or "- None"
        files_hint = "\n".join(f"  - {f}" for f in expected_paths)
        output_contract = self._build_subtask_output_contract(expected_paths)

        return f"""
## SUBTASK [{task.id}]: {task.title}

{task.description}

## USER STORY
- ID: {user_story.id}
- Title: {user_story.title}
- Description: {user_story.description[:800]}

## ACCEPTANCE CRITERIA
{acceptance_criteria}

## FILES TO PRODUCE OR UPDATE
{files_hint}

## OUTPUT CONTRACT
{output_contract}

## EXISTING CODE TO EDIT
{existing_context or '(no existing files to edit)'}

## PACKAGE BASE
{analysis.package_base}

## ENTITIES
{entities_json}

## ENDPOINTS
{endpoints_json}

## BUSINESS RULES
{chr(10).join(f"- {r}" for r in analysis.business_rules[:5]) or '- None'}

## STRICT IMPLEMENTATION RULES
- Implement only what this subtask and the acceptance criteria require.
- Do not rename files.
- Do not invent alternate class names or alternate paths.
- Do not introduce extra CRUD endpoints, helper methods, or extra files unless explicitly required.
- If a listed file is to be edited, return the complete final file content, not a diff.
- Return only fenced Java code blocks with explicit target paths and no prose before or after them.
""".strip()

    def _build_subtask_retry_prompt(
        self,
        task: SubTask,
        user_story: UserStory,
        analysis: AnalysisResult,
        current_files: Dict[str, str],
        expected_paths: list[str],
        validation_error: str,
        previous_response: str,
    ) -> str:
        base_prompt = self._build_subtask_prompt(
            task=task,
            user_story=user_story,
            analysis=analysis,
            current_files=current_files,
            expected_paths=expected_paths,
        )
        trimmed_response = previous_response[:1200]
        return f"""
{base_prompt}

## PREVIOUS RESPONSE WAS REJECTED
Validation error: {validation_error}

Your previous response did not satisfy the required file contract.
You must correct it now.

## PREVIOUS RESPONSE EXCERPT
{trimmed_response}

## RETRY INSTRUCTIONS
- Produce at least one of the exact expected file paths.
- Prefer producing all expected file paths when the subtask logically requires them.
- Do not output any file whose path is not listed in FILES TO PRODUCE OR UPDATE.
- Do not add explanations, headings, bullet points, JSON, or markdown outside the fenced Java blocks.
""".strip()

    def _build_subtask_existing_context(
        self,
        task: SubTask,
        current_files: Dict[str, str],
    ) -> str:
        chunks = []
        for path in task.files_to_edit[:3]:
            if path in current_files:
                chunks.append(f"\n// === {path} (TO EDIT) ===\n{current_files[path][:1500]}\n")
        return "".join(chunks)

    def _build_subtask_output_contract(self, expected_paths: list[str]) -> str:
        lines = [
            "- Return one fenced Java block per file.",
            "- Use this exact header format: ```java:path/to/File.java",
            "- The path after ```java: must exactly match one of the expected file paths below.",
            "- Do not use placeholder paths.",
            "- Do not wrap all files in one generic block.",
            "- Do not include commentary outside the code blocks.",
            "- Expected file paths:",
        ]
        lines.extend(f"  - {path}" for path in expected_paths)
        return "\n".join(lines)

    def _extract_and_sanitize_subtask_output(self, response: str) -> Dict[str, str]:
        generated = self.extract_code_blocks(response)
        return self._sanitize_generated_java_files(generated)

    def _seed_missing_files(
        self, task, accumulated: Dict[str, str], analysis
    ) -> Dict[str, str]:
        """Generate minimal compilable Java stubs for files a subtask failed to produce."""
        from pathlib import Path as _Path
        pkg = getattr(analysis, "package_base", "com.example.app")
        stubs: Dict[str, str] = {}
        expected = set(task.files_to_create + task.files_to_edit)
        for path in expected:
            if path in accumulated:
                continue
            norm = path.replace("\\", "/")
            class_name = _Path(norm).stem
            if norm.endswith(".java"):
                if "interface" in task.title.lower() or "Interface" in class_name:
                    kind = "interface"
                elif "enum" in task.title.lower() or "Enum" in class_name:
                    kind = "enum"
                else:
                    kind = "class"
                stubs[norm] = (
                    f"package {pkg};\n\n"
                    f"// Auto-generated stub — replace with real implementation\n"
                    f"public {kind} {class_name} {{\n}}\n"
                )
                logger.info(f"    [stub] Seeded {norm}")
        return stubs

    def _validate_subtask_output(self, task, generated: Dict[str, str]) -> None:
        expected_paths = sorted(set(task.files_to_create + task.files_to_edit))
        generated_paths = sorted(path.replace("\\", "/") for path in generated.keys())
        unexpected_paths = [path for path in generated_paths if path not in expected_paths]
        if unexpected_paths:
            raise ValueError(
                f"Subtask {task.id} generated unexpected files: {', '.join(unexpected_paths[:5])}"
            )

        produced_expected = [path for path in generated_paths if path in expected_paths]
        if not produced_expected:
            raise ValueError(
                f"Subtask {task.id} produced none of its expected files: {', '.join(expected_paths[:5])}"
            )

    def _split_by_conflicts(
        self, tasks: list
    ) -> tuple:
        """
        Split tasks into (parallel-safe, sequential-fallback) based on file conflicts.

        If two tasks in the same group target the same file → they must be sequential.
        """
        all_files: Dict[str, str] = {}  # file_path → task_id that claims it
        parallel = []
        sequential = []
        conflicts: Dict[str, list] = {}

        for task in tasks:
            claimed = sorted(set(task.files_to_create + task.files_to_edit))
            conflict_paths = sorted({f for f in claimed if f in all_files})
            conflict = bool(conflict_paths)
            if conflict:
                sequential.append(task)
                conflicts[task.id] = conflict_paths
            else:
                parallel.append(task)
                for f in claimed:
                    all_files[f] = task.id

        parallel = sorted(parallel, key=lambda t: (t.priority, t.id))
        sequential = sorted(sequential, key=lambda t: (t.priority, t.id))
        return parallel, sequential, conflicts

    def _merge_task_outputs(
        self,
        accumulated: Dict[str, str],
        task_results: list,
        group_number: int,
    ) -> Dict[str, str]:
        merged = dict(accumulated)
        seen_paths: Dict[str, str] = {}
        ordered_results = sorted(task_results, key=lambda item: (item[0].priority, item[0].id))

        for task, result in ordered_results:
            for path in sorted(result.keys()):
                owner = seen_paths.get(path)
                if owner and owner != task.id:
                    raise ValueError(
                        f"Execution group {group_number} produced duplicate output path "
                        f"{path} from {owner} and {task.id}"
                    )
                seen_paths[path] = task.id

        for task, result in ordered_results:
            merged_files = sorted(result.keys())
            if merged_files:
                logger.info(f"    Merge {task.id}: {merged_files}")
            for path in merged_files:
                merged[path] = result[path]

        return merged

    def _extract_java_private_fields(self, content: str) -> dict:
        fields = {}
        for java_type, name in re.findall(
            r"^\s*private\s+([A-Za-z_][A-Za-z0-9_<>.,? ]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$",
            content,
            re.MULTILINE,
        ):
            fields[name] = " ".join(java_type.split())
        return fields

    def _sanitize_service_impl_against_entity_schema(
        self,
        files: Dict[str, str],
    ) -> Dict[str, str]:
        """
        Remove entity getter/setter usages introduced by the fixer when they do
        not exist on the actual entity present in the generated sources.
        """
        sanitized = dict(files)

        for path, content in list(sanitized.items()):
            normalized = path.replace("\\", "/")
            if not normalized.endswith("ServiceImpl.java"):
                continue

            entity_import = re.search(
                r"^\s*import\s+([a-zA-Z0-9_.]+)\.entity\.([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$",
                content,
                re.MULTILINE,
            )
            if not entity_import:
                continue

            entity_package_path = entity_import.group(1).replace(".", "/")
            entity_name = entity_import.group(2)
            entity_path = f"src/main/java/{entity_package_path}/entity/{entity_name}.java"
            entity_source = sanitized.get(entity_path)
            if not entity_source:
                continue

            allowed_fields = set(self._extract_java_private_fields(entity_source).keys())
            if not allowed_fields:
                continue
            allowed_fields.add("id")

            updated_lines = []
            changed = False
            for line in content.splitlines():
                setter_match = re.search(r"entity\.set([A-Z][A-Za-z0-9_]*)\s*\(", line)
                if setter_match:
                    prop = setter_match.group(1)
                    field_name = prop[0].lower() + prop[1:]
                    if field_name not in allowed_fields:
                        changed = True
                        continue

                getter_match = re.search(r"entity\.get([A-Z][A-Za-z0-9_]*)\(\)", line)
                if getter_match:
                    prop = getter_match.group(1)
                    field_name = prop[0].lower() + prop[1:]
                    if field_name not in allowed_fields:
                        changed = True
                        continue

                updated_lines.append(line)

            if changed:
                sanitized[path] = "\n".join(updated_lines) + "\n"

        return sanitized

    def _sanitize_generated_java_files(self, files: Dict[str, str]) -> Dict[str, str]:
        sanitized: Dict[str, str] = {}
        for path, content in files.items():
            normalized_path = path.replace("\\", "/")
            if normalized_path.endswith(".java"):
                content = self._replace_wildcard_imports(content)
            sanitized[path] = content
        sanitized = self._synchronize_model_fields_from_usage(sanitized)
        sanitized = self._sanitize_service_impl_against_entity_schema(sanitized)
        return sanitized

    def _synchronize_model_fields_from_usage(self, files: Dict[str, str]) -> Dict[str, str]:
        specs = self._build_model_class_specs(files)
        if not specs:
            return files

        expected_fields = self._collect_expected_model_fields(files, specs)
        updated = dict(files)

        for class_name, requested_fields in expected_fields.items():
            spec = specs.get(class_name)
            if not spec or not self._class_supports_generated_model_fields(spec["content"]):
                continue

            existing_fields = dict(spec["field_types"])
            new_content = spec["content"]
            changed = False

            for field_name, candidate_types in requested_fields.items():
                if field_name in existing_fields:
                    continue
                inferred_type = self._choose_model_field_type(field_name, candidate_types, specs)
                new_content = self._insert_field_into_java_class(new_content, field_name, inferred_type)
                existing_fields[field_name] = inferred_type
                changed = True

            if changed:
                updated[spec["path"]] = new_content

        return updated

    def _build_model_class_specs(self, files: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        specs: Dict[str, Dict[str, Any]] = {}
        field_pattern = re.compile(
            r"^\s*(?:private|protected|public)\s+(?!static\b)(?:final\s+)?([A-Z][A-Za-z0-9_<>,.\[\]? ]*|int|long|double|float|boolean|Integer|Long|Double|Float|Boolean|String)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*;\s*$",
            re.MULTILINE,
        )

        for path, content in files.items():
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue
            if not any(token in normalized for token in ("/entity/", "/dto/", "/model/")):
                continue

            type_match = re.search(r"\b(?:class|record)\s+([A-Z][A-Za-z0-9_]*)\b", content)
            if not type_match:
                continue

            field_types = {
                field_name: " ".join(field_type.split())
                for field_type, field_name in field_pattern.findall(content)
            }
            specs[type_match.group(1)] = {
                "path": path,
                "content": content,
                "field_types": field_types,
            }

        return specs

    def _collect_expected_model_fields(
        self,
        files: Dict[str, str],
        specs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, set[str]]]:
        expected: Dict[str, Dict[str, set[str]]] = {}
        known_classes = set(specs.keys())

        for path, content in files.items():
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".java") or normalized.startswith("src/test/"):
                continue

            variable_types = self._extract_java_variable_types(content)
            current_builder_class: Optional[str] = None

            for raw_line in content.splitlines():
                line = raw_line.strip()
                builder_start = re.search(r"\b([A-Z][A-Za-z0-9_]*)\.builder\(\)", line)
                if builder_start:
                    candidate_class = builder_start.group(1)
                    current_builder_class = candidate_class if candidate_class in known_classes else None
                elif current_builder_class and ".build()" in line:
                    current_builder_class = None

                if current_builder_class:
                    builder_line = re.match(r"\.([a-zA-Z_][A-Za-z0-9_]*)\((.*)\)\s*$", line)
                    if builder_line:
                        field_name, arg_expr = builder_line.groups()
                        inferred = self._infer_java_expression_type(arg_expr.strip(), variable_types, specs)
                        expected.setdefault(current_builder_class, {}).setdefault(field_name, set()).add(inferred)

                for accessor_match in re.finditer(
                    r"\b([a-zA-Z_][A-Za-z0-9_]*)\.(get|set)([A-Z][A-Za-z0-9_]*)\((.*)\)",
                    line,
                ):
                    var_name, accessor_kind, suffix, args = accessor_match.groups()
                    class_name = variable_types.get(var_name, "").replace("java.lang.", "").strip()
                    if class_name not in known_classes:
                        continue
                    field_name = suffix[0].lower() + suffix[1:]
                    if accessor_kind == "set":
                        inferred = self._infer_java_expression_type(args.strip(), variable_types, specs)
                    else:
                        inferred = specs.get(class_name, {}).get("field_types", {}).get(field_name, "String")
                    expected.setdefault(class_name, {}).setdefault(field_name, set()).add(inferred)

        return expected

    def _extract_java_variable_types(self, content: str) -> Dict[str, str]:
        variable_types: Dict[str, str] = {}
        declaration_patterns = (
            re.compile(
                r"\b(?:private|protected|public|final)\s+([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*(?:=[^;]*)?;"
            ),
            re.compile(
                r"\b([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*=\s*[^;]+;"
            ),
        )
        for pattern in declaration_patterns:
            for type_name, var_name in pattern.findall(content):
                variable_types[var_name] = " ".join(type_name.split())

        for params in re.findall(r"\(([^)]*)\)", content):
            for raw_param in params.split(","):
                param = raw_param.strip()
                match = re.match(r"([A-Z][A-Za-z0-9_<>,.\[\]? ]*)\s+([a-zA-Z_][A-Za-z0-9_]*)$", param)
                if match:
                    variable_types[match.group(2)] = " ".join(match.group(1).split())

        return variable_types

    def _infer_java_expression_type(
        self,
        expr: str,
        variable_types: Dict[str, str],
        specs: Dict[str, Dict[str, Any]],
    ) -> str:
        candidate = expr.strip()
        if not candidate or candidate == "null":
            return "String"
        if candidate in {"true", "false"}:
            return "Boolean"
        if re.fullmatch(r'"[^"]*"', candidate):
            return "String"
        if re.fullmatch(r"-?\d+[lL]", candidate):
            return "Long"
        if re.fullmatch(r"-?\d+", candidate):
            return "Integer"
        if re.fullmatch(r"-?\d+\.\d+[dD]?", candidate):
            return "Double"
        if re.fullmatch(r"-?\d+\.\d+[fF]", candidate):
            return "Float"

        getter_match = re.fullmatch(r"([a-zA-Z_][A-Za-z0-9_]*)\.get([A-Z][A-Za-z0-9_]*)\(\)", candidate)
        if getter_match:
            var_name, suffix = getter_match.groups()
            class_name = variable_types.get(var_name, "").replace("java.lang.", "").strip()
            field_name = suffix[0].lower() + suffix[1:]
            if class_name in specs:
                return specs[class_name]["field_types"].get(field_name, "String")

        return variable_types.get(candidate, "String").replace("java.lang.", "").strip() or "String"

    def _choose_model_field_type(
        self,
        field_name: str,
        candidate_types: set[str],
        specs: Dict[str, Dict[str, Any]],
    ) -> str:
        normalized_candidates = [
            candidate.replace("java.lang.", "").strip()
            for candidate in candidate_types
            if candidate and candidate != "unknown"
        ]
        for candidate in normalized_candidates:
            if candidate:
                return candidate

        for spec in specs.values():
            inferred = spec["field_types"].get(field_name)
            if inferred:
                return inferred

        return "String"

    def _class_supports_generated_model_fields(self, content: str) -> bool:
        if any(annotation in content for annotation in ("@Data", "@Getter", "@Setter", "@Builder")):
            return True
        return bool(re.search(r"\b(?:get|set)[A-Z][A-Za-z0-9_]*\s*\(", content))

    def _insert_field_into_java_class(self, content: str, field_name: str, field_type: str) -> str:
        field_line = f"    private {field_type} {field_name};\n"
        if field_line in content:
            return content

        lines = content.splitlines()
        insert_at = None
        method_or_ctor_pattern = re.compile(
            r"^\s*(?:public|protected|private)\s+(?:[A-Z][A-Za-z0-9_]*\s*\(|[\w<>\[\],.? ]+\s+[a-zA-Z_][A-Za-z0-9_]*\s*\()"
        )

        for idx, line in enumerate(lines):
            if method_or_ctor_pattern.match(line):
                insert_at = idx
                break

        if insert_at is None:
            for idx in range(len(lines) - 1, -1, -1):
                if lines[idx].strip() == "}":
                    insert_at = idx
                    break

        if insert_at is None:
            return content

        if insert_at > 0 and lines[insert_at - 1].strip():
            lines.insert(insert_at, "")
            insert_at += 1
        lines.insert(insert_at, field_line.rstrip("\n"))
        return "\n".join(lines) + "\n"

    def _replace_wildcard_imports(self, content: str) -> str:
        if "import " not in content or ".*;" not in content:
            return content

        for wildcard_import, explicit_imports in self._WILDCARD_IMPORT_REPLACEMENTS.items():
            if wildcard_import not in content:
                continue
            content = content.replace(wildcard_import, "\n".join(explicit_imports))

        lines = content.splitlines()
        deduped_lines = []
        seen_imports = set()
        for line in lines:
            if line.startswith("import "):
                if line in seen_imports:
                    continue
                seen_imports.add(line)
            deduped_lines.append(line)
        return "\n".join(deduped_lines)

    async def fix_compile_errors(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        previous_code: GeneratedCode,
        compile_result,
    ) -> GeneratedCode:
        """Corrige uniquement les fichiers métier qui ont des erreurs."""
        logger.info("  🔧 Correction des erreurs de compilation...")

        if os.getenv("DEVELOPER_ALLOW_LLM_FIX", "true").lower() not in ("1", "true", "yes", "on"):
            logger.info("  ⏭️ Correction LLM désactivée (DEVELOPER_ALLOW_LLM_FIX=false)")
            return previous_code

        # Boilerplate = toujours correct → on ne les envoie pas au LLM
        engine = JavaTemplateEngine(analysis)
        boilerplate_paths = set(engine.generate_all().keys())
        business_files = {
            p: c for p, c in previous_code.files.items()
            if p not in boilerplate_paths
        }

        business_context = "\n\n".join(
            f"// === {path} ===\n{content}"
            for path, content in business_files.items()
        )

        msg = f"""
Corrige les erreurs de compilation dans les fichiers métier.

═══════════════════════════════════════════════════════════
ERREURS DE COMPILATION À CORRIGER
═══════════════════════════════════════════════════════════
{compile_result.to_prompt()}

═══════════════════════════════════════════════════════════
FICHIERS MÉTIER (source de vérité)
═══════════════════════════════════════════════════════════
{chr(10).join(f"- {p}" for p in business_files)}

═══════════════════════════════════════════════════════════
CODE MÉTIER ACTUEL (NE PAS CRÉER DE NOUVELLES CLASSES)
═══════════════════════════════════════════════════════════
{business_context[:24000]}

═══════════════════════════════════════════════════════════
CONTEXTE DU PROJET
═══════════════════════════════════════════════════════════
- Package: {analysis.package_base}
- Service: {analysis.service_name}
- Exceptions disponibles:
  ✓ import {analysis.package_base}.exception.ResourceNotFoundException
  ✓ import {analysis.package_base}.exception.BusinessException

═══════════════════════════════════════════════════════════
CONTRAINTES STRICTES (violation = rejet)
═══════════════════════════════════════════════════════════
✗ NE crée PAS de nouvelles classes avec de nouveaux noms
✗ NE modifie PAS les fichiers boilerplate (Application.java, GlobalExceptionHandler, etc.)
✗ N'introduis AUCUN package autre que `{analysis.package_base}`
✓ RÉUTILISE les classes/DTOs déjà présentes dans le code métier actuel
✓ Assure la cohérence entre imports, types de retour et constructeurs utilisés
✓ Utilise UNIQUEMENT jakarta.* (JAMAIS javax.*)
✓ Utilise @RequiredArgsConstructor (JAMAIS @Autowired)
✓ Exceptions étendent RuntimeException (JAMAIS jakarta.ws.rs.*)
✓ Spring Web annotations (JAMAIS jakarta.ws.rs.*)
✓ Imports Lombok explicites OBLIGATOIRES

Génère UNIQUEMENT les fichiers corrigés: ```java:src/main/java/chemin/Fichier.java
""".strip()

        response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=msg,
            max_tokens=8192,
        )

        fixed_raw = self.extract_code_blocks(response)
        fixed = {
            path: content
            for path, content in fixed_raw.items()
            if path in business_files and content.strip()
        }
        merged = {**previous_code.files, **fixed}
        merged = self._sanitize_generated_java_files(merged)
        merged = self._sanitize_service_impl_against_entity_schema(merged)
        logger.info(f"  ✓ {len(fixed)} fichier(s) corrigé(s)")

        return GeneratedCode(
            files=merged,
            pom_xml=previous_code.pom_xml,
            readme=previous_code.readme,
        )

    # ── Test generation from contract ────────────────────────────────────────
    #
    # This replaces the TesterAgent free-generation approach.
    # The Developer generates tests in the SAME context as the production code,
    # so it knows the real constructors, getters, and methods.
    #
    # Rules enforced in the prompt:
    #   - Test cases come ONLY from the test_contract.
    #   - DTO validation uses Jakarta Validator, never assertThrows on constructors.
    #   - Controller tests use @WebMvcTest + MockMvc.
    #   - Service tests use Mockito.
    #   - Repository tests only if the contract explicitly includes them.

    _TEST_SYSTEM_PROMPT = """
You are generating JUnit 5 test files for a Maven Spring Boot project.

PATH RULES — CRITICAL:
- Every generated test file path MUST start with src/test/java/.
- NEVER generate test files under src/main/java/.
- NEVER generate production files in this step.
- Test class names MUST end with Test or Tests.
- Example correct path: src/test/java/com/example/app/dto/AuthenticationRequestTest.java
- Example WRONG path: src/main/java/com/example/app/dto/AuthenticationRequestTest.java

CONTENT RULES:
1. Generate ONLY the tests present in the Test Contract. Nothing else.
2. Do NOT invent methods, getters or constructors not visible in the provided source code.
3. For DTO tests (target_layer=dto): use the Lombok @AllArgsConstructor.
   Correct example:
   AuthenticationRequest req = new AuthenticationRequest("john", "pass123");
   assertThat(req.getUsername()).isEqualTo("john");
4. For validation tests (target_layer=validation): use Jakarta Validator.
   Correct example:
   ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
   Validator validator = factory.getValidator();
   Set<ConstraintViolation<AuthenticationRequest>> violations = validator.validate(new AuthenticationRequest("", "pass"));
   assertThat(violations).isNotEmpty();
   NEVER: assertThrows(IllegalArgumentException.class, () -> new AuthenticationRequest("", "pass"))
5. For controller tests (target_layer=controller): @WebMvcTest + MockMvc only.
6. For service tests (target_layer=service): @ExtendWith(MockitoExtension.class) + @Mock + @InjectMocks.
7. For repository tests (target_layer=repository): only if explicitly in the contract.
8. Required annotations:
   - @Timeout(10) on each @Test method
   - import static org.assertj.core.api.Assertions.*
9. Do NOT generate @SpringBootTest.
10. Do NOT generate smoke tests like assertThat(true).isTrue().
11. Do NOT create CoverageSafetyNetTest or StoryScopeSmokeTest.
12. Use ONLY jakarta.* (NEVER javax.*).

FORMAT: ```java:src/test/java/complete/path/ClassNameTest.java
""".strip()

    async def generate_test_files_from_contract(
        self,
        user_story: "UserStory",
        analysis: "AnalysisResult",
        test_contract_dicts: list,
        generated_code: "GeneratedCode",
    ) -> Dict[str, str]:
        """
        Generate src/test/java files strictly from the test_contract.

        Called in the pipeline AFTER production code is compiled successfully.
        The production code is passed so the LLM sees real class structures.

        Returns a dict of { "src/test/java/...": "..." }.
        Only paths under src/test/java/ are kept.
        """
        if not test_contract_dicts:
            logger.warning("  [Developer] No test contract — skipping test generation")
            return {}

        # Import here to avoid circular dependency at module level
        from core.test_contract import TestContract
        contract = TestContract.from_dict({
            "story_id": user_story.id,
            "test_cases": test_contract_dicts,
        })

        active_cases = contract.active_cases
        if not active_cases:
            logger.warning("  [Developer] Test contract has no active cases — skipping test generation")
            return {}

        logger.info(f"  [Developer] Generating tests from contract ({len(active_cases)} case(s))")

        # Build focused production code context (only relevant files)
        relevant_production = self._select_relevant_production_files(
            generated_code, contract
        )
        production_context = "\n\n".join(
            f"// === {path} ===\n{content[:2000]}"
            for path, content in relevant_production.items()
        )

        contract_snippet = contract.to_prompt_snippet()
        pkg = analysis.package_base

        msg = f"""
Génère les fichiers de test JUnit 5 basés STRICTEMENT sur ce Test Contract.

═══════════════════════════════════════════════════════════
TEST CONTRACT (source de vérité — NE PAS s'en écarter)
═══════════════════════════════════════════════════════════
{contract_snippet}

═══════════════════════════════════════════════════════════
USER STORY
═══════════════════════════════════════════════════════════
ID: {user_story.id}
Title: {user_story.title}
Acceptance Criteria:
{chr(10).join(f"- {c}" for c in user_story.acceptance_criteria[:8])}

═══════════════════════════════════════════════════════════
CODE DE PRODUCTION GÉNÉRÉ (constructeurs et méthodes réels)
═══════════════════════════════════════════════════════════
Package: {pkg}
{production_context[:18000]}

═══════════════════════════════════════════════════════════
CONTRAINTES CRITIQUES
═══════════════════════════════════════════════════════════
✓ Package de test: {pkg} (même structure que production)
✓ Chaque test file doit correspondre à UN test case ou UN groupe de test cases du contrat
✓ Utilise UNIQUEMENT les constructeurs/méthodes visibles dans le code fourni
✓ Pour validation: Validation.buildDefaultValidatorFactory() + validator.validate()
✗ JAMAIS assertThrows(IllegalArgumentException.class, () -> new Dto(...))
✗ JAMAIS inventer de getter non présent dans le code
✗ JAMAIS générer de tests hors du contrat

Génère les fichiers de test: ```java:src/test/java/chemin/ClassTest.java
""".strip()

        response = await self.call_llm(
            system_prompt=self._TEST_SYSTEM_PROMPT,
            user_message=msg,
            max_tokens=6000,
        )

        raw_files = self.extract_code_blocks(response)

        # Collect test files with tolerant path normalization.
        # The LLM sometimes places test files under src/main/java — we fix that automatically.
        test_files: Dict[str, str] = {}
        for path, content in raw_files.items():
            if not content.strip():
                continue
            normalized = path.replace("\\", "/")
            is_test_name = normalized.endswith("Test.java") or normalized.endswith("Tests.java")

            # Normalize wrong prefix for test-named files
            if is_test_name and normalized.startswith("src/main/java/"):
                fixed = "src/test/java/" + normalized[len("src/main/java/"):]
                logger.info(
                    "  [Developer] Normalized test path from %s to %s", normalized, fixed
                )
                normalized = fixed
            elif is_test_name and normalized.startswith("main/java/"):
                fixed = "src/test/java/" + normalized[len("main/java/"):]
                logger.info(
                    "  [Developer] Normalized test path from %s to %s", normalized, fixed
                )
                normalized = fixed
            elif is_test_name and normalized.startswith("java/"):
                fixed = "src/test/java/" + normalized[len("java/"):]
                logger.info(
                    "  [Developer] Normalized test path from %s to %s", normalized, fixed
                )
                normalized = fixed

            if not normalized.startswith("src/test/java/"):
                logger.warning(
                    "  [Developer] Ignored non-test path from contract generation: %s", path
                )
                continue
            test_files[normalized] = content

        logger.info(
            f"  [Developer] Generated {len(test_files)} test file(s) from contract "
            f"({len(active_cases)} case(s))"
        )
        return test_files

    def _select_relevant_production_files(
        self,
        generated_code: "GeneratedCode",
        contract: "object",
    ) -> Dict[str, str]:
        """Return production files relevant to the test contract classes (≤ 8 files)."""
        # contract here is a TestContract instance
        target_classes = getattr(contract, "target_classes", lambda: [])()
        result: Dict[str, str] = {}
        for path, content in generated_code.files.items():
            normalized = path.replace("\\", "/")
            if not normalized.startswith("src/main/java/"):
                continue
            # Include if the file name matches a target class
            stem = path.replace("\\", "/").rsplit("/", 1)[-1].replace(".java", "")
            if any(stem == tc or stem.endswith(tc) or tc in stem for tc in target_classes):
                result[path] = content
            if len(result) >= 8:
                break
        # If nothing matched, include the first few main files as context
        if not result:
            for path, content in list(generated_code.files.items())[:4]:
                if path.replace("\\", "/").startswith("src/main/java/"):
                    result[path] = content
        return result

    async def correct(
        self,
        user_story: UserStory,
        analysis: AnalysisResult,
        docs: dict,
        previous_code: GeneratedCode,
        correction_prompt: str,
        review_issues: list,
    ) -> GeneratedCode:
        """Corrige le code après retour du Reviewer."""
        logger.info("  🔧 Correction du code après review...")

        if os.getenv("DEVELOPER_ALLOW_LLM_FIX", "true").lower() not in ("1", "true", "yes", "on"):
            logger.info("  ⏭️ Correction post-review LLM désactivée")
            return previous_code

        engine = JavaTemplateEngine(analysis)
        boilerplate_paths = set(engine.generate_all().keys())

        issues_text = "\n".join(
            f"- [{i.get('severity')}] {i.get('file')}: {i.get('description')} → {i.get('suggestion')}"
            for i in review_issues
            if i.get("severity") in ("CRITICAL", "MAJOR")
        )

        msg = f"""
Corrige les problèmes identifiés par la code review.

═══════════════════════════════════════════════════════════
PROBLÈMES À CORRIGER (CRITICAL + MAJOR uniquement)
═══════════════════════════════════════════════════════════
{issues_text}

═══════════════════════════════════════════════════════════
INSTRUCTIONS DE CORRECTION
═══════════════════════════════════════════════════════════
{correction_prompt}

═══════════════════════════════════════════════════════════
CONTEXTE DU PROJET
═══════════════════════════════════════════════════════════
- Package: {analysis.package_base}
- Service: {analysis.service_name}

═══════════════════════════════════════════════════════════
CONTRAINTES (respecte les conventions Spring Boot 3.2)
═══════════════════════════════════════════════════════════
✓ Utilise UNIQUEMENT jakarta.* (JAMAIS javax.*)
✓ Utilise @RequiredArgsConstructor (JAMAIS @Autowired)
✓ Exceptions étendent RuntimeException (JAMAIS jakarta.ws.rs.*)
✓ Spring Web annotations (JAMAIS jakarta.ws.rs.*)
✓ Imports Lombok explicites OBLIGATOIRES

Génère UNIQUEMENT les fichiers corrigés: ```java:src/main/java/chemin/Fichier.java
""".strip()

        response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=msg,
            max_tokens=8192,
        )

        corrected_raw = self.extract_code_blocks(response)
        corrected = {
            path: content
            for path, content in corrected_raw.items()
            if path in previous_code.files and path not in boilerplate_paths and content.strip()
        }
        merged = {**previous_code.files, **corrected}
        merged = self._sanitize_generated_java_files(merged)
        logger.info(f"  ✓ {len(corrected)} fichier(s) corrigé(s)")

        return GeneratedCode(
            files=merged,
            pom_xml=previous_code.pom_xml,
            readme=previous_code.readme,
        )

    def _generate_readme(self, analysis: AnalysisResult, user_story: UserStory) -> str:
        endpoints = "\n".join(
            f"- `{ep.method} {ep.path}` — {ep.description}"
            for ep in analysis.endpoints
        )
        entities = ", ".join(e.name for e in analysis.entities) or "N/A"

        return f"""# {analysis.service_name} Service

Généré automatiquement par AI-SDLC Pipeline pour [{user_story.id}].

## User Story
**{user_story.title}**

{user_story.description[:400]}

## Architecture
- **Package**: `{analysis.package_base}`
- **Entités JPA**: {entities}
- **Stack**: Spring Boot 3.2 | Java 23 | H2 (dev) | PostgreSQL (prod)

## Endpoints
{endpoints}

## Lancement
```bash
mvn spring-boot:run
```

- API: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- H2 Console: `http://localhost:8080/h2-console`
"""
