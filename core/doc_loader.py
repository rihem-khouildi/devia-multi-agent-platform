"""
Charge et indexe la documentation projet:
- Modèles d'analyse (entités, relations, règles métier)
- Diagrammes UML (texte/PlantUML)
- Architecture logicielle
- Spécifications Gherkin
- Schémas d'architecture
- Blueprints JSON
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class DocumentationLoader:
    """
    Structure de dossier attendue:
    docs/
    ├── analysis/          # Modèles d'analyse structurés (JSON, MD)
    ├── uml/               # Diagrammes UML (PlantUML .puml, .md)
    ├── architecture/      # Architecture logicielle (.md, .json)
    ├── gherkin/           # Specs Gherkin (.feature)
    └── schemas/           # Schémas d'architecture (.json, .yaml)
    """

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".feature", ".puml"}

    def __init__(self, docs_dir: Path):
        self.docs_dir = Path(docs_dir)

    async def load_all(self) -> Dict[str, str]:
        """Charge tous les documents dans un dictionnaire {chemin: contenu}."""
        docs = {}
        
        if not self.docs_dir.exists():
            logger.warning(f" Dossier docs introuvable: {self.docs_dir}")
            return docs

        categories = ["analysis", "uml", "architecture", "gherkin", "schemas"]
        
        for category in categories:
            cat_path = self.docs_dir / category
            if cat_path.exists():
                files = self._load_directory(cat_path, category)
                docs.update(files)
                logger.debug(f"   {category}: {len(files)} fichiers")
        
        # Charger aussi la racine
        for f in self.docs_dir.glob("*"):
            if f.is_file() and f.suffix in self.SUPPORTED_EXTENSIONS:
                docs[f"root/{f.name}"] = f.read_text(encoding="utf-8")
        
        return docs

    def _load_directory(self, directory: Path, prefix: str) -> Dict[str, str]:
        """Charge récursivement un dossier."""
        result = {}
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix in self.SUPPORTED_EXTENSIONS:
                relative = file_path.relative_to(self.docs_dir)
                try:
                    content = file_path.read_text(encoding="utf-8")
                    result[str(relative)] = content
                except Exception as e:
                    logger.warning(f"   Impossible de lire {file_path}: {e}")
        return result

    def format_for_prompt(self, docs: Dict[str, str], max_chars: int = 50000) -> str:
        """Formate la documentation pour injection dans un prompt LLM."""
        sections = []
        total = 0
        
        priority_order = ["analysis/", "gherkin/", "architecture/", "uml/", "schemas/"]
        
        sorted_docs = {}
        for prefix in priority_order:
            for k, v in docs.items():
                if k.startswith(prefix) and k not in sorted_docs:
                    sorted_docs[k] = v
        for k, v in docs.items():
            if k not in sorted_docs:
                sorted_docs[k] = v
        
        for path, content in sorted_docs.items():
            section = f"\n### [{path}]\n{content}\n"
            if total + len(section) > max_chars:
                sections.append(f"\n### [{path}]\n[Tronqué - {len(content)} chars]\n")
                break
            sections.append(section)
            total += len(section)
        
        return "\n".join(sections)

    async def load_blueprint(self) -> Optional[Dict]:
        """
        Charge le fichier blueprint principal (pattern: blueprint-*.json).
        Retourne le contenu JSON ou None si aucun blueprint trouvé.
        """
        if not self.docs_dir.exists():
            return None

        # Chercher les fichiers blueprint-*.json
        blueprints = list(self.docs_dir.glob("blueprint-*.json"))

        if not blueprints:
            logger.debug("  Aucun blueprint trouvé dans docs/")
            return None

        # Prendre le premier (ou le plus récent)
        blueprint_file = sorted(blueprints, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        try:
            content = blueprint_file.read_text(encoding="utf-8")
            blueprint = json.loads(content)
            logger.info(f"  Blueprint chargé: {blueprint_file.name}")
            return blueprint
        except json.JSONDecodeError as e:
            logger.warning(f"  Blueprint JSON invalide ({blueprint_file}): {e}")
            return None
        except Exception as e:
            logger.warning(f"  Erreur lecture blueprint: {e}")
            return None

    def get_blueprint_path(self) -> Optional[Path]:
        """Retourne le chemin du fichier blueprint s'il existe."""
        if not self.docs_dir.exists():
            return None

        blueprints = list(self.docs_dir.glob("blueprint-*.json"))
        if blueprints:
            return sorted(blueprints, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None
