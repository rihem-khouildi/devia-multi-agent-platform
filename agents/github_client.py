"""
Client GitHub pour committer le code généré.
Utilise l'API REST GitHub v3.

Différences vs GitLab:
- Commit fichier par fichier via /contents (ou via Git Tree API pour les gros commits)
- Pull Request au lieu de Merge Request
- Token: ghp_XXXX (Personal Access Token) ou github_pat_XXXX (Fine-grained)
"""

import base64
import json
from typing import Dict, List, Optional
import aiohttp

from config.settings import GitHubConfig
from core.models import UserStory, GeneratedCode, TestResult
from utils.logger import get_logger

logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """Client GitHub REST API v3."""

    def __init__(self, config: GitHubConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        # Base URL du repo: /repos/{owner}/{repo}
        self._repo_url = f"{GITHUB_API}/repos/{config.owner}/{config.repo}"

    # ──────────────────────────────────────────────────────────────
    #  Point d'entrée principal
    # ──────────────────────────────────────────────────────────────

    async def commit_code(
        self,
        user_story: UserStory,
        generated_code: GeneratedCode,
        test_result: TestResult,
        branch: str,
        base_branch: Optional[str] = None,
    ) -> str:
        """Crée une branche, committe tous les fichiers et ouvre une Pull Request."""

        # 1. Crée la branche depuis main/master
        effective_base_branch = base_branch or self.config.base_branch or self.config.default_branch
        await self._ensure_branch(branch, effective_base_branch)

        # 2. Prépare tous les fichiers à committer
        all_files = self._collect_files(generated_code, test_result)
        logger.info(f"   {len(all_files)} fichiers à committer")

        # 3. Commit via Git Tree API (un seul commit pour tous les fichiers)
        commit_sha = await self._commit_tree(
            branch=branch,
            message=self._build_commit_message(user_story, test_result),
            files=all_files,
        )

        # 4. Ouvre une Pull Request
        await self._create_pull_request(
            branch=branch,
            user_story=user_story,
            test_result=test_result,
        )

        return commit_sha

    # ──────────────────────────────────────────────────────────────
    #  Branche
    # ──────────────────────────────────────────────────────────────

    async def _ensure_branch(self, branch: str, base_branch: str):
        """Crée la branche si elle n'existe pas encore depuis la branche de base fournie."""

        async with aiohttp.ClientSession() as session:

            # Vérifie si la branche existe déjà
            async with session.get(
                f"{self._repo_url}/branches/{branch}",
                headers=self.headers,
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"  Branche existante: {branch}")
                    return

            # Récupère le SHA de la branche de base
            async with session.get(
                f"{self._repo_url}/git/ref/heads/{base_branch}",
                headers=self.headers,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Impossible de lire la branche {base_branch}: {text}")
                data = await resp.json()
                base_sha = data["object"]["sha"]

            # Crée la nouvelle branche
            payload = {"ref": f"refs/heads/{branch}", "sha": base_sha}
            async with session.post(
                f"{self._repo_url}/git/refs",
                headers=self.headers,
                json=payload,
            ) as resp:
                if resp.status == 201:
                    logger.info(f"  ✓ Branche créée: {branch} (base: {base_branch})")
                else:
                    text = await resp.text()
                    logger.warning(f"   Création branche: {resp.status} - {text[:200]}")

    # ──────────────────────────────────────────────────────────────
    #  Commit via Git Tree API (efficace pour beaucoup de fichiers)
    # ──────────────────────────────────────────────────────────────

    async def _commit_tree(
        self, branch: str, message: str, files: Dict[str, str]
    ) -> str:
        """
        Committe plusieurs fichiers en une seule opération via l'API Git Tree.
        Étapes: get base commit → create blobs → create tree → create commit → update ref
        """
        async with aiohttp.ClientSession() as session:

            # 1. Récupère le dernier commit de la branche
            async with session.get(
                f"{self._repo_url}/git/ref/heads/{branch}",
                headers=self.headers,
            ) as resp:
                data = await resp.json()
                base_commit_sha = data["object"]["sha"]

            # 2. Récupère le tree du commit de base
            async with session.get(
                f"{self._repo_url}/git/commits/{base_commit_sha}",
                headers=self.headers,
            ) as resp:
                data = await resp.json()
                base_tree_sha = data["tree"]["sha"]

            # 3. Crée les blobs pour chaque fichier
            tree_items = []
            for file_path, content in files.items():
                # Encode en base64
                encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                async with session.post(
                    f"{self._repo_url}/git/blobs",
                    headers=self.headers,
                    json={"content": encoded, "encoding": "base64"},
                ) as resp:
                    blob_data = await resp.json()
                    tree_items.append({
                        "path": file_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_data["sha"],
                    })

            # 4. Crée le nouveau tree
            async with session.post(
                f"{self._repo_url}/git/trees",
                headers=self.headers,
                json={"base_tree": base_tree_sha, "tree": tree_items},
            ) as resp:
                tree_data = await resp.json()
                new_tree_sha = tree_data["sha"]

            # 5. Crée le commit
            async with session.post(
                f"{self._repo_url}/git/commits",
                headers=self.headers,
                json={
                    "message": message,
                    "tree": new_tree_sha,
                    "parents": [base_commit_sha],
                },
            ) as resp:
                commit_data = await resp.json()
                new_commit_sha = commit_data["sha"]

            # 6. Met à jour la référence de la branche
            async with session.patch(
                f"{self._repo_url}/git/refs/heads/{branch}",
                headers=self.headers,
                json={"sha": new_commit_sha},
            ) as resp:
                if resp.status == 200:
                    logger.info(f"  ✓ Commit GitHub: {new_commit_sha[:8]}")
                else:
                    text = await resp.text()
                    raise RuntimeError(f"Échec mise à jour ref: {text}")

        return new_commit_sha

    # ──────────────────────────────────────────────────────────────
    #  Pull Request
    # ──────────────────────────────────────────────────────────────

    async def _create_pull_request(
        self, branch: str, user_story: UserStory, test_result: TestResult
    ):
        """Ouvre une Pull Request GitHub ou met à jour la PR existante."""
        body = f"""##  Généré par AI-SDLC Pipeline

**User Story**: `{user_story.id}` — {user_story.title}

### Description
{user_story.description[:500]}

### Résultats des Tests
| Métrique | Valeur |
|----------|--------|
| Couverture | {test_result.coverage}% |
| Fichiers de test | {len(test_result.test_files)} |
| Statut | {' PASSED' if test_result.passed else '❌ FAILED'} |

### Critères d'Acceptation
{chr(10).join(f"- [ ] {ac}" for ac in user_story.acceptance_criteria)}

---
> *Code généré automatiquement — à relire avant de merger*
"""

        payload = {
            "title": f"[AI] [{user_story.id}] {user_story.title}",
            "body": body,
            "head": branch,
            "base": self.config.default_branch,
            "draft": True,          # PR en brouillon pour review obligatoire
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._repo_url}/pulls",
                headers=self.headers,
                json=payload,
            ) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    logger.info(f"  ✓ Pull Request créée: {data.get('html_url')}")
                    # Ajoute le label "ai-generated"
                    await self._add_label(data["number"], session)
                elif resp.status == 422:
                    existing_pr = await self._find_open_pr_for_branch(branch, session)
                    if not existing_pr:
                        text = await resp.text()
                        logger.warning(f"   Création PR: {resp.status} - {text[:200]}")
                        return

                    pr_number = existing_pr["number"]
                    updated = await self._update_pull_request(
                        pr_number=pr_number,
                        title=payload["title"],
                        body=payload["body"],
                        session=session,
                    )
                    if updated:
                        logger.info(
                            f"  ✓ PR existante mise à jour: {existing_pr.get('html_url')}"
                        )
                        await self._add_label(pr_number, session)
                    else:
                        logger.warning(
                            f"   PR existante détectée mais impossible à mettre à jour: #{pr_number}"
                        )
                else:
                    text = await resp.text()
                    logger.warning(f"   Création PR: {resp.status} - {text[:200]}")

    async def _find_open_pr_for_branch(
        self, branch: str, session: aiohttp.ClientSession
    ) -> Optional[dict]:
        """Retourne la PR ouverte pour owner:branch si elle existe."""
        params = {
            "state": "open",
            "head": f"{self.config.owner}:{branch}",
            "base": self.config.default_branch,
        }
        async with session.get(
            f"{self._repo_url}/pulls",
            headers=self.headers,
            params=params,
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if isinstance(data, list) and data:
                return data[0]
            return None

    async def _update_pull_request(
        self,
        pr_number: int,
        title: str,
        body: str,
        session: aiohttp.ClientSession,
    ) -> bool:
        """Met à jour le titre et la description d'une PR existante."""
        async with session.patch(
            f"{self._repo_url}/pulls/{pr_number}",
            headers=self.headers,
            json={"title": title, "body": body},
        ) as resp:
            return resp.status == 200

    async def _add_label(self, pr_number: int, session: aiohttp.ClientSession):
        """Ajoute le label 'ai-generated' à la PR (le crée si nécessaire)."""
        # Crée le label s'il n'existe pas
        await session.post(
            f"{self._repo_url}/labels",
            headers=self.headers,
            json={"name": "ai-generated", "color": "0075ca"},
        )
        # Applique le label
        await session.post(
            f"{self._repo_url}/issues/{pr_number}/labels",
            headers=self.headers,
            json={"labels": ["ai-generated"]},
        )

    # ──────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────

    def _collect_files(
        self, generated_code: GeneratedCode, test_result: TestResult
    ) -> Dict[str, str]:
        """Rassemble tous les fichiers à committer."""
        files = {}
        files.update(generated_code.files)
        files.update(test_result.test_files)

        if generated_code.pom_xml:
            files["pom.xml"] = generated_code.pom_xml
        if generated_code.readme:
            files["README.md"] = generated_code.readme

        files[".ai-sdlc/test-report.json"] = json.dumps(
            test_result.to_dict(), indent=2
        )
        return files

    def _build_commit_message(self, user_story: UserStory, test_result: TestResult) -> str:
        return f"""feat({user_story.id}): {user_story.title}

Généré par AI-SDLC Pipeline

- Couverture de tests : {test_result.coverage}%
- Tests               : JUnit 5 + Mockito + AssertJ

User Story : {user_story.id}
Co-authored-by: AI-SDLC-Pipeline <ai-sdlc@noreply.github.com>"""
