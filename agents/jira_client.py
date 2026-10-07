"""
Client Jira pour récupérer les User Stories.
Utilise l'API REST Jira Cloud.
"""

import aiohttp
import base64
from typing import Optional
from config.settings import JiraConfig
from core.models import UserStory
from utils.logger import get_logger

logger = get_logger(__name__)


class JiraClient:
    """Client Jira REST API."""

    def __init__(self, config: JiraConfig):
        self.config = config
        self.base_url = f"{config.url}/rest/api/3"
        self._auth = base64.b64encode(
            f"{config.username}:{config.api_token}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {self._auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_user_story(self, issue_id: str) -> UserStory:
        """Récupère une User Story depuis Jira."""
        url = f"{self.base_url}/issue/{issue_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 404:
                    raise ValueError(f"Issue Jira introuvable: {issue_id}")
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Erreur Jira {resp.status}: {text}")
                
                data = await resp.json()
                return self._parse_issue(data)

    async def get_project_stories(self, max_results: int = 50) -> list:
         """Fetch issues for the configured project with a simple Jira query."""
         jql = f'project = "{self.config.project_key}" ORDER BY created DESC'
         url = f"{self.base_url}/search/jql"
         params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,description,priority,labels"
        }
         
         async with aiohttp.ClientSession() as session:
             async with session.get(url, headers=self.headers, params=params) as resp:
                if resp.status != 200:
                  text = await resp.text()
                  raise RuntimeError(f"Jira search failed {resp.status}: {text}")
                data = await resp.json()
                return [self._parse_issue(issue) for issue in data.get("issues", [])]
            
    async def update_status(self, issue_id: str, status: str):
        """Met à jour le statut d'une issue Jira."""
        # 1. Récupère les transitions disponibles
        url = f"{self.base_url}/issue/{issue_id}/transitions"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                data = await resp.json()
                transitions = data.get("transitions", [])
            
            # 2. Trouve la transition cible
            target = next(
                (t for t in transitions if t["name"].lower() == status.lower()),
                None
            )
            if not target:
                logger.warning(f"Transition '{status}' introuvable pour {issue_id}")
                return
            
            # 3. Applique la transition
            payload = {"transition": {"id": target["id"]}}
            async with session.post(url, headers=self.headers, json=payload) as resp:
                if resp.status in (204, 200):
                    logger.info(f"  ✓ Jira {issue_id} → {status}")
                else:
                    logger.warning(f"   Transition Jira échouée: {resp.status}")

    def _parse_issue(self, data: dict) -> UserStory:
        """Parse une issue Jira en UserStory."""
        fields = data["fields"]
        
        # Acceptance Criteria: souvent dans un champ custom ou dans la description
        description = self._extract_description(fields.get("description", {}))
        acceptance_criteria = self._extract_acceptance_criteria(
            fields.get("customfield_10016", ""),  # champ AC Jira standard
            description
        )
        
        return UserStory(
            id=data["key"],
            title=fields.get("summary", ""),
            description=description,
            acceptance_criteria=acceptance_criteria,
            priority=fields.get("priority", {}).get("name", "Medium"),
            story_points=fields.get("story_points") or fields.get("customfield_10016"),
            labels=fields.get("labels", []),
            epic=fields.get("customfield_10014"),  # Epic Link
            raw=data,
        )

    def _extract_description(self, description_obj) -> str:
        """Extrait le texte de la description (format ADF Jira)."""
        if not description_obj:
            return ""
        if isinstance(description_obj, str):
            return description_obj
        
        # Format ADF (Atlassian Document Format)
        texts = []
        def traverse(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                for child in node.get("content", []):
                    traverse(child)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)
        
        traverse(description_obj)
        return "\n".join(texts)

    def _extract_acceptance_criteria(self, ac_field: str, description: str) -> list:
       """Extrait les critères d'acceptation."""
    
    # Cherche dans la description après "Acceptance Criteria"
       text_to_parse = description
    
       if "acceptance criteria" in text_to_parse.lower():
           parts = text_to_parse.lower().split("acceptance criteria")
           # Récupère le texte original (pas lowercase) après "Acceptance Criteria"
           original_parts = description[description.lower().index("acceptance criteria") + len("acceptance criteria"):]
        
           # Sépare par tiret "-" ou par saut de ligne
           import re
           # Cherche tous les items qui commencent par "-"
           items = re.findall(r'-\s*([^-]+)', original_parts)
           cleaned = [item.strip().rstrip('-').strip() for item in items if item.strip()]
        
           if cleaned:
             return cleaned
    
       return ["Voir description de la User Story"]