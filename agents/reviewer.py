"""
Agent Code Reviewer
====================
Analyse le code Java généré par le Developer et détecte:
- Bugs potentiels
- Violations des principes SOLID
- Problèmes de sécurité
- Mauvaises pratiques Spring Boot
- Naming conventions Java

Retourne un ReviewResult avec un score et une liste de problèmes.
Si des problèmes critiques sont détectés → le Developer doit régénérer.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List

from agents.base_agent import BaseAgent
from config.settings import HuggingFaceConfig
from core.models import GeneratedCode, AnalysisResult
from core.exceptions import ReviewParseError
from utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
Tu es un expert Java et Spring Boot chargé de faire la code review d'un projet généré automatiquement.

═══════════════════════════════════════════════════════════
TON RÔLE: Identifier les problèmes réels dans le code Java
═══════════════════════════════════════════════════════════

CATÉGORIES D'ANALYSE:
═══════════════════════════════════════════════════════════

1. BUGS:
   - NullPointerException potentiels
   - Logique incorrecte
   - Cas non gérés
   - Ressources non fermées

2. SOLID:
   - Single Responsibility violations
   - Open/Closed violations
   - Liskov Substitution violations
   - Interface Segregation violations
   - Dependency Inversion violations

3. SÉCURITÉ:
   - Injection SQL
   - Données sensibles exposées
   - Endpoints non sécurisés
   - Validation d'entrée manquante

4. CONVENTIONS SPRING BOOT 3.2 / JAKARTA EE (CRITIQUE):
   ✗ JAMAIS javax.* → doit être jakarta.*
   ✗ JAMAIS jakarta.ws.rs.* → doit être org.springframework.web.bind.annotation.*
   ✗ JAMAIS @Autowired sur champs → doit être @RequiredArgsConstructor + final
   ✗ JAMAIS @Path, @GET, @POST (JAX-RS) → doit être @RestController, @GetMapping, etc.
   ✗ JAMAIS springfox.* → doit être springdoc-openapi (io.swagger.v3.oas.annotations.*)
   ✓ TOUJOURS imports Lombok explicites (import lombok.Data, import lombok.Builder, etc.)
   ✓ TOUJOURS @Transactional sur les méthodes de service modifiant les données
   ✓ TOUJOURS ResponseEntity<T> pour les contrôleurs REST

5. QUALITÉ:
   - Nommage incorrect (non conforme aux conventions Java)
   - Méthodes trop longues (> 50 lignes)
   - Duplication de code
   - Commentaires manquants pour la logique complexe
   - DTOs non réutilisés (doublons)

═══════════════════════════════════════════════════════════
SCORING & SEVERITY
═══════════════════════════════════════════════════════════

CRITICAL (bloque le commit):
- Bugs critiques (NullPointerException, logique incorrecte)
- Failles de sécurité
- Violations de conventions Spring Boot 3.2/Jakarta EE (javax.*, jakarta.ws.rs.*, @Autowired)

MAJOR (doit être corrigé):
- Violations SOLID importantes
- Mauvaises pratiques Spring
- @Transactional manquant
- Validation d'entrée manquante

MINOR (recommandé):
- Style de code
- Nommage non optimal
- Optimisation possible
- Commentaires manquants

RÈGLE: approved=true uniquement si score >= 70 ET zéro problème CRITICAL.

═══════════════════════════════════════════════════════════
FORMAT DE RÉPONSE (JSON strict, rien d'autre)
═══════════════════════════════════════════════════════════
{
  "score": 0-100,
  "approved": true/false,
  "summary": "résumé en 1 phrase",
  "issues": [
    {
      "severity": "CRITICAL|MAJOR|MINOR",
      "file": "chemin/du/fichier",
      "description": "description du problème",
      "suggestion": "comment corriger avec exemple de code"
    }
  ],
  "positives": ["point fort 1", "point fort 2"],
  "correction_prompt": "Instructions précises pour corriger les problèmes CRITICAL et MAJOR"
}
""".strip()


@dataclass
class ReviewIssue:
    severity: str        # CRITICAL, MAJOR, MINOR
    file: str
    description: str
    suggestion: str


@dataclass
class ReviewResult:
    score: float
    approved: bool
    summary: str
    issues: List[ReviewIssue] = field(default_factory=list)
    positives: List[str] = field(default_factory=list)
    correction_prompt: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "CRITICAL")

    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "MAJOR")

    @property
    def minor_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "MINOR")

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "approved": self.approved,
            "summary": self.summary,
            "critical": self.critical_count,
            "major": self.major_count,
            "minor": self.minor_count,
            "issues": [vars(i) for i in self.issues],
            "positives": self.positives,
        }


class ReviewerAgent(BaseAgent):
    """Agent qui analyse la qualité du code Java généré."""

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config, "Reviewer", model=config.model_reviewer)
        logger.info(f"  🤖 Reviewer → modèle: {self.model}")

    async def review(
        self,
        generated_code: GeneratedCode,
        analysis: AnalysisResult,
    ) -> ReviewResult:
        """Analyse le code généré et retourne un rapport de review."""
        logger.info(f"  🔍 Review de {len(generated_code.files)} fichiers Java...")

        # Prépare un résumé du code (pour ne pas dépasser les limites de tokens)
        code_summary = self._prepare_code_summary(generated_code)

        user_message = f"""
Fais la code review du projet Spring Boot suivant.

## CONTEXTE
- Service: {analysis.service_name}
- Package: {analysis.package_base}
- Entités: {', '.join(e.name for e in analysis.entities)}
- Endpoints: {len(analysis.endpoints)}

## CODE GÉNÉRÉ ({len(generated_code.files)} fichiers)

{code_summary}

## CRITÈRES D'ACCEPTATION DE LA US
{chr(10).join(f"- {r}" for r in analysis.business_rules)}

Retourne UNIQUEMENT le JSON de review, sans aucun texte autour.
""".strip()

        response = await self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=3000,
            temperature=0.1,
        )

        return self._parse_review(response)

    def _prepare_code_summary(self, generated_code: GeneratedCode) -> str:
        """Prépare un résumé du code pour le prompt (évite les limites de tokens)."""
        lines = []
        # Priorise les fichiers les plus importants
        priority_keywords = ["Service", "Controller", "Entity", "Repository", "Exception"]

        def priority(path: str) -> int:
            for i, kw in enumerate(priority_keywords):
                if kw in path:
                    return i
            return len(priority_keywords)

        sorted_files = sorted(generated_code.files.items(), key=lambda x: priority(x[0]))

        total_chars = 0
        max_chars = 12000  # limite pour laisser de la place au prompt

        for file_path, content in sorted_files:
            if total_chars >= max_chars:
                lines.append(f"\n[... {len(generated_code.files) - len(lines)} fichiers supplémentaires non affichés]")
                break
            snippet = content[:2000] if len(content) > 2000 else content
            lines.append(f"\n### {file_path}\n```java\n{snippet}\n```")
            total_chars += len(snippet)

        return "\n".join(lines)

    def _parse_review(self, response: str) -> ReviewResult:
        """Parse la réponse JSON du LLM."""
        def clean_llm_json(raw_response: str) -> str:
            cleaned = raw_response.strip()

            # Enlève les wrappers de code block ```json ... ```
            if cleaned.startswith("```"):
                parts = cleaned.split("```")
                if len(parts) >= 2:
                    cleaned = parts[1]

            # Enlève le préfixe json si présent
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

            return cleaned.strip()

        try:
            cleaned = clean_llm_json(response)

            try:
                data = json.loads(cleaned)
            except Exception as e:
                print(f"⚠️ JSON parsing failed: {e}")
                logger.warning(f"  ⚠️ JSON parsing failed: {e}")
                data = {
                    "score": 75,
                    "approved": True,
                    "summary": "Fallback: parsing failed but LLM response was usable",
                    "issues": [],
                }

            issues = [
                ReviewIssue(
                    severity=i.get("severity", "MINOR"),
                    file=i.get("file", "unknown"),
                    description=i.get("description", ""),
                    suggestion=i.get("suggestion", ""),
                )
                for i in data.get("issues", [])
            ]

            return ReviewResult(
                score=float(data.get("score", 50)),
                approved=bool(data.get("approved", False)),
                summary=data.get("summary", "Review complétée"),
                issues=issues,
                positives=data.get("positives", []),
                correction_prompt=data.get("correction_prompt", ""),
            )

        except (ValueError, KeyError, json.JSONDecodeError, TypeError) as e:
            logger.error(f"  ❌ Impossible de parser la review: {e}")
            raise ReviewParseError(
                f"Le reviewer n'a pas retourné un JSON valide. "
                f"Réponse brute: {response[:200]}..."
            )
