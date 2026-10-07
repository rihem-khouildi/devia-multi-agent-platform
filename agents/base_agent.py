"""
Agent de base avec fallback automatique entre providers LLM.
Ordre: AzureFoundry (Kimi) → Groq → Mistral → HuggingFace

Tokens nécessaires dans .env:
  AZURE_FOUNDRY_API_KEY=...   (clé du déploiement Azure AI Foundry)
  AZURE_FOUNDRY_BASE_URL=https://<resource>.swedencentral.models.ai.azure.com  (URI cible sans /chat/completions)
  AZURE_FOUNDRY_MODEL=Kimi-K2.6  (nom du déploiement)
  GROQ_API_KEY=gsk_...
  MISTRAL_API_KEY=mist_...
  HF_TOKEN=hf_...
"""

import json
import re
import asyncio
import aiohttp
import os
import random
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import HuggingFaceConfig, env_bool
from utils.logger import get_logger

logger = get_logger(__name__)

def _azure_foundry_base_url() -> str:
    """
    Retourne l'URL de base Azure AI Foundry.
    Exemple d'URL complète fournie par Azure :
      https://<resource>.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview
    On extrait uniquement la partie avant /chat/completions.
    """
    url = os.environ.get("AZURE_FOUNDRY_BASE_URL", "")
    # Retire la query string et le chemin /chat/completions
    if "?" in url:
        url = url.split("?")[0]
    for suffix in ("/chat/completions", "/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _azure_foundry_model() -> str:
    return os.environ.get("AZURE_FOUNDRY_MODEL", "Kimi-K2.6")


PROVIDERS = [
    {
        # Azure AI Foundry — Kimi-K2.6 (priorité 1)
        # URL: valeur de AZURE_FOUNDRY_BASE_URL (ex: https://<resource>.swedencentral.models.ai.azure.com)
        # Clé: valeur de AZURE_FOUNDRY_API_KEY
        "name": "AzureFoundry",
        "base_url": _azure_foundry_base_url(),
        "env_key": "AZURE_FOUNDRY_API_KEY",
        "model_map": {
            # Tous les modèles sont redirigés vers Kimi-K2.6
            "Qwen/Qwen2.5-7B-Instruct":        _azure_foundry_model(),
            "Qwen/Qwen2.5-72B-Instruct":       _azure_foundry_model(),
            "Qwen/Qwen2.5-Coder-7B-Instruct":  _azure_foundry_model(),
            "Qwen/Qwen2.5-Coder-32B-Instruct": _azure_foundry_model(),
            "meta-llama/Llama-3.1-8B-Instruct": _azure_foundry_model(),
            "meta-llama/Llama-3.3-70B-Instruct": _azure_foundry_model(),
        },
        "azure_foundry": True,
    },
    {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "model_map": {
            "Qwen/Qwen2.5-7B-Instruct": "llama-3.1-8b-instant",
            "Qwen/Qwen2.5-72B-Instruct": "llama-3.3-70b-versatile",
            "Qwen/Qwen2.5-Coder-7B-Instruct": "llama-3.1-8b-instant",
            "Qwen/Qwen2.5-Coder-32B-Instruct": "llama-3.3-70b-versatile",
            "meta-llama/Llama-3.1-8B-Instruct": "llama-3.1-8b-instant",
            "meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b-versatile",
        },
    },
    {
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "env_key": "MISTRAL_API_KEY",
        "model_map": {
            "Qwen/Qwen2.5-7B-Instruct": "open-mistral-nemo",
            "Qwen/Qwen2.5-72B-Instruct": "mistral-large-latest",
            "Qwen/Qwen2.5-Coder-7B-Instruct": "open-mistral-nemo",
            "Qwen/Qwen2.5-Coder-32B-Instruct": "mistral-large-latest",
            "meta-llama/Llama-3.1-8B-Instruct": "open-mistral-nemo",
            "meta-llama/Llama-3.3-70B-Instruct": "mistral-large-latest",
            "mistralai/Mistral-7B-Instruct-v0.3": "mistral-7b-instruct-v0.3",
            "mistralai/Mixtral-8x7B-Instruct-v0.1": "mixtral-8x7b-instruct-v0.1",
        },
    },
    {
        "name": "HuggingFace",
        "base_url": "https://router.huggingface.co/v1",
        "env_key": "HF_TOKEN",
        "models": {
            "default": None,
        },
    },
]

FALLBACK_CODES = {402, 401, 403, 404}
RETRY_CODES = {429}


class BaseAgent:
    """Classe de base pour tous les agents IA du pipeline."""

    _provider_health: Dict[str, bool] = {}
    _preflight_done: bool = False
    _preflight_lock = asyncio.Lock()

    def __init__(self, config: HuggingFaceConfig, agent_name: str, model: str = None):
        self.config = config
        self.agent_name = agent_name
        self.model = model or None
        self.providers = self._build_providers()
        logger.info(f"[{self.agent_name}] Providers actifs: {[p['name'] for p in self.providers]}")

    def _build_providers(self) -> List[dict]:
        providers: List[dict] = []
        azure_enabled = env_bool("AZURE_FOUNDRY_ENABLED", default=True)
        azure_api_key = os.getenv("AZURE_FOUNDRY_API_KEY")
        azure_base_url = _azure_foundry_base_url()

        for provider in PROVIDERS:
            if provider["name"] != "AzureFoundry":
                providers.append(provider)
                continue

            if azure_enabled and azure_api_key and azure_base_url:
                providers.append(provider)
            else:
                logger.info(
                    f"[{self.agent_name}] AzureFoundry desactive par configuration ou non configure"
                )

        return providers

    def _llm_cache_enabled(self) -> bool:
        return env_bool("LLM_CACHE_ENABLED", default=True)

    def _llm_cache_dir(self) -> Path:
        root = Path(os.getenv("LLM_CACHE_DIR", "./output/artifacts/llm_cache"))
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _llm_cache_key(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
        cache_namespace: str = "",
    ) -> str:
        payload = {
            "agent": self.agent_name,
            "model": model,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cache_namespace": cache_namespace,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _read_cached_llm(self, cache_key: str) -> Optional[str]:
        cache_file = self._llm_cache_dir() / f"{cache_key}.txt"
        if not cache_file.exists():
            return None
        return cache_file.read_text(encoding="utf-8")

    def _write_cached_llm(self, cache_key: str, content: str) -> None:
        cache_file = self._llm_cache_dir() / f"{cache_key}.txt"
        cache_file.write_text(content, encoding="utf-8")

    def _get_api_key(self, provider: dict) -> Optional[str]:
        if provider["name"] == "HuggingFace":
            return self.config.api_key
        return os.environ.get(provider["env_key"])

    async def preflight_providers(self) -> None:
        """Teste rapidement la disponibilité des providers et désactive ceux indisponibles."""
        if BaseAgent._preflight_done:
            return

        async with BaseAgent._preflight_lock:
            if BaseAgent._preflight_done:
                return

            for provider in self.providers:
                provider_name = provider["name"]
                api_key = self._get_api_key(provider)
                if not api_key:
                    BaseAgent._provider_health[provider_name] = False
                    logger.warning(
                        f"[{self.agent_name}] preflight: {provider_name} désactivé (clé manquante)"
                    )
                    continue

                headers = {"Authorization": f"Bearer {api_key}"}
                if provider_name == "OpenRouter":
                    headers["HTTP-Referer"] = "https://ai-sdlc-pipeline"
                    headers["X-Title"] = "AI SDLC Pipeline"

                try:
                    # Azure AI Foundry n'a pas d'endpoint /models — on vérifie juste
                    # que la clé est présente et que l'URL est configurée.
                    if provider.get("azure_foundry"):
                        if not provider["base_url"]:
                            BaseAgent._provider_health[provider_name] = False
                            logger.warning(
                                f"[{self.agent_name}] preflight: {provider_name} désactivé "
                                "(AZURE_FOUNDRY_BASE_URL manquant)"
                            )
                        else:
                            BaseAgent._provider_health[provider_name] = True
                            logger.info(
                                f"[{self.agent_name}] preflight: {provider_name} ✓ "
                                f"(clé présente, url={provider['base_url'][:50]}...)"
                            )
                        continue

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{provider['base_url']}/models",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=8),
                        ) as resp:
                            if resp.status in (200, 404, 405):
                                BaseAgent._provider_health[provider_name] = True
                                continue

                            if resp.status in (401, 403):
                                BaseAgent._provider_health[provider_name] = False
                                logger.warning(
                                    f"[{self.agent_name}] preflight: {provider_name} désactivé ({resp.status})"
                                )
                                continue

                            BaseAgent._provider_health[provider_name] = True
                except aiohttp.ClientError:
                    BaseAgent._provider_health[provider_name] = False
                    logger.warning(
                        f"[{self.agent_name}] preflight: {provider_name} désactivé (réseau)"
                    )

            BaseAgent._preflight_done = True

    def _active_providers(self) -> List[dict]:
        """Retourne les providers disponibles selon le preflight."""
        available = []
        for provider in self.providers:
            name = provider["name"]
            if BaseAgent._provider_health.get(name, True):
                available.append(provider)

        priority = {
            "AzureFoundry": 0,
            "Groq": 1,
            "Mistral": 2,
            "HuggingFace": 3,
        }
        return sorted(available, key=lambda provider: priority.get(provider["name"], 99))

    def _resolve_model(self, provider: dict, original_model: str) -> str:
        """Résout le nom de modèle pour un provider donné."""
        if provider["name"] == "HuggingFace":
            return original_model
        model_map = provider.get("model_map", {})
        if provider["name"] == "AzureFoundry":
            return model_map.get(original_model, _azure_foundry_model())
        return model_map.get(original_model, "llama-3.1-8b-instant")

    async def _call_provider(
        self,
        provider: dict,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """
        Appelle un provider spécifique avec retry sur 429/503/504.
        Retourne le texte ou lève une exception.
        """
        api_key = self._get_api_key(provider)
        if not api_key:
            raise RuntimeError(
                f"[{self.agent_name}] Clé API manquante pour {provider['name']} "
                f"(variable: {provider['env_key']})"
            )

        resolved_model = self._resolve_model(provider, model)
        base_url = provider["base_url"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if provider["name"] == "OpenRouter":
            headers["HTTP-Referer"] = "https://ai-sdlc-pipeline"
            headers["X-Title"] = "AI SDLC Pipeline"

        # Azure AI Foundry utilise un endpoint différent avec api-version
        is_azure_foundry = provider.get("azure_foundry", False)
        if is_azure_foundry:
            chat_url = f"{base_url}/chat/completions?api-version=2024-05-01-preview"
        else:
            chat_url = f"{base_url}/chat/completions"

        payload = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        max_attempts = max(1, int(os.getenv("LLM_MAX_RETRIES", "2")))
        base_wait = float(os.getenv("LLM_RETRY_BASE_SECONDS", "5"))
        max_wait = float(os.getenv("LLM_RETRY_MAX_SECONDS", "15"))

        # Azure Foundry (Kimi K2.6) est un très grand modèle — timeout plus élevé
        if is_azure_foundry:
            timeout_seconds = int(os.getenv("LLM_AZURE_FOUNDRY_TIMEOUT_SECONDS",
                                            os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120")))
        else:
            timeout_seconds = int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "45"))

        import time
        for attempt in range(1, max_attempts + 1):
            t_start = time.monotonic()
            logger.info(
                f"[{self.agent_name}] → {provider['name']}: {resolved_model} "
                f"(tentative {attempt}/{max_attempts}, timeout={timeout_seconds}s)"
            )
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        chat_url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"]
                            elapsed = time.monotonic() - t_start
                            if not text or not text.strip():
                                raise FallbackException(
                                    f"[{self.agent_name}] {provider['name']} retourné réponse vide "
                                    f"en {elapsed:.1f}s — fallback au provider suivant",
                                    disable_provider=False,
                                )
                            logger.info(
                                f"[{self.agent_name}] ✓ {len(text)} chars reçus "
                                f"({provider['name']}) en {elapsed:.1f}s"
                            )
                            return text

                        if resp.status in FALLBACK_CODES:
                            body = await resp.text()
                            logger.warning(
                                f"[{self.agent_name}] {provider['name']} HTTP {resp.status} "
                                f"— réponse: {body[:400]}"
                            )
                            # Ne pas désactiver définitivement AzureFoundry sur 401/403
                            # (peut être un quota temporaire ou un header manquant)
                            disable = not is_azure_foundry
                            raise FallbackException(
                                f"[{self.agent_name}] {provider['name']} {resp.status} "
                                f"→ fallback: {body[:200]}",
                                disable_provider=disable,
                            )

                        if resp.status in RETRY_CODES:
                            if attempt < max_attempts:
                                wait = min(base_wait * (2 ** (attempt - 1)), max_wait)
                                wait += random.uniform(0, 1.5)
                                logger.warning(
                                    f"[{self.agent_name}] ⏳ {provider['name']} {resp.status} "
                                    f"→ attente {wait:.1f}s..."
                                )
                                await asyncio.sleep(wait)
                                continue
                            raise FallbackException(
                                f"[{self.agent_name}] {provider['name']} persistant "
                                f"après {max_attempts} tentatives ({resp.status})",
                                disable_provider=False,
                            )

                        body = await resp.text()
                        logger.warning(
                            f"[{self.agent_name}] {provider['name']} HTTP {resp.status} "
                            f"— réponse: {body[:400]}"
                        )
                        raise FallbackException(
                            f"[{self.agent_name}] {provider['name']} {resp.status}: "
                            f"{body[:300]}",
                            disable_provider=False,
                        )

            except FallbackException:
                raise

            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if current_task and current_task.cancelling():
                    raise

                if attempt < max_attempts:
                    wait = min(base_wait * (2 ** (attempt - 1)), max_wait)
                    wait += random.uniform(0, 1.5)
                    logger.warning(
                        f"[{self.agent_name}] Requête annulée côté transport {provider['name']} "
                        f"→ retry {attempt}/{max_attempts}"
                    )
                    await asyncio.sleep(wait)
                    continue

                raise FallbackException(
                    f"[{self.agent_name}] {provider['name']} requête annulée côté transport",
                    disable_provider=False,
                )

            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t_start
                # On timeout, immediately fallback to the next provider — do NOT retry.
                # Retrying on the same slow provider wastes time when others are available.
                logger.warning(
                    f"[{self.agent_name}] ⏱ Timeout {provider['name']} "
                    f"après {elapsed:.1f}s → fallback immédiat au provider suivant"
                )
                raise FallbackException(
                    f"[{self.agent_name}] {provider['name']} timeout après {elapsed:.0f}s",
                    disable_provider=False,
                )

            except aiohttp.ClientError as e:
                if attempt < max_attempts:
                    wait = min(base_wait * (2 ** (attempt - 1)), max_wait)
                    wait += random.uniform(0, 1.5)
                    logger.warning(
                        f"[{self.agent_name}] Erreur réseau {provider['name']} "
                        f"→ retry {attempt}/{max_attempts}"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise FallbackException(
                    f"[{self.agent_name}] {provider['name']} erreur réseau: {e}",
                    disable_provider=False,
                )

        raise FallbackException(
            f"[{self.agent_name}] {provider['name']} échec après {max_attempts} tentatives",
            disable_provider=False,
        )

    async def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        model: str = None,
        max_tokens: int = None,
        temperature: float = None,
        use_cache: bool = True,
        cache_namespace: str = "",
    ) -> str:
        """
        Appelle les providers dans l'ordre: Groq → Mistral → HuggingFace.
        Bascule automatiquement si un provider échoue.
        """
        resolved_model = model or self.model
        if not resolved_model:
            raise ValueError(f"[{self.agent_name}] Aucun modèle configuré")

        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        cache_key = self._llm_cache_key(
            model=resolved_model,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
            cache_namespace=cache_namespace,
        )
        cache_allowed = use_cache and self._llm_cache_enabled()
        if cache_allowed:
            cached = self._read_cached_llm(cache_key)
            if cached is not None:
                logger.info(f"[{self.agent_name}] ♻️ Réponse LLM récupérée depuis le cache")
                return cached

        await self.preflight_providers()

        providers = self._active_providers()
        if not providers:
            raise RuntimeError(
                f"[{self.agent_name}] Aucun provider actif après preflight. "
                "Vérifier les clés API et la connectivité."
            )

        last_error = None
        provider_names = [p["name"] for p in providers]
        logger.info(f"[{self.agent_name}] Providers actifs: {provider_names}")

        for idx, provider in enumerate(providers):
            next_provider = providers[idx + 1]["name"] if idx + 1 < len(providers) else "aucun"
            try:
                response = await self._call_provider(
                    provider=provider,
                    model=resolved_model,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if cache_allowed:
                    self._write_cached_llm(cache_key, response)
                return response
            except FallbackException as e:
                last_error = str(e)
                if e.disable_provider:
                    BaseAgent._provider_health[provider["name"]] = False
                logger.warning(
                    f"[{self.agent_name}] ⚠️  {provider['name']} échoué → "
                    f"provider suivant: {next_provider}"
                )
                continue

        raise RuntimeError(
            f"[{self.agent_name}] Tous les providers ont échoué: {provider_names}\n"
            f"Dernière erreur: {last_error}"
        )

    def extract_json(self, text: str) -> Dict[str, Any]:
        """Extrait un bloc JSON d'une réponse LLM."""
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        match = re.search(r"```\s*([\[\{].*?)\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        stripped = text.strip()
        if stripped.startswith(("{", "[")):
            return json.loads(stripped)
        raise ValueError(f"Impossible d'extraire JSON: {text[:200]}")

    def _normalize_path(self, path: str, lang: str) -> str:
        path = path.strip()

        is_tester = self.agent_name.lower() == "tester"

        if "/" not in path and (lang == "java" or path.endswith(".java")):
            java_root = "src/test/java" if is_tester else "src/main/java"
            return f"{java_root}/{path}"

        if "/" not in path:
            return path

        if path.startswith("src/"):
            return path

        if lang == "java" or path.endswith(".java"):
            for prefix in ("java/", "main/java/", "src/main/java/"):
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    break
            java_root = "src/test/java" if is_tester else "src/main/java"
            return f"{java_root}/{path}"

        if lang in ("properties", "yaml", "yml") or any(
            path.endswith(ext) for ext in (".properties", ".yaml", ".yml")
        ):
            for prefix in ("resources/", "main/resources/"):
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    break
            return f"src/main/resources/{path}"

        if path.endswith(".xml") and "pom" not in path.lower():
            return f"src/main/resources/{path}"

        return path

    def extract_code_blocks(self, text: str) -> Dict[str, str]:
        """Extrait les blocs de code annotés et normalise les chemins."""
        files = {}

        pattern1 = re.compile(
            r"```(java|xml|properties|yaml|groovy):([^\n]+)\n(.*?)```",
            re.DOTALL,
        )
        for match in pattern1.finditer(text):
            lang = match.group(1).strip()
            raw_path = match.group(2).strip()
            content = match.group(3).strip()
            if not content:
                continue
            normalized = self._normalize_path(raw_path, lang)
            files[normalized] = content

        if not files:
            pattern2 = re.compile(r"```(java|xml|properties|yaml)\s*(.*?)```", re.DOTALL)
            for match in pattern2.finditer(text):
                lang = match.group(1).strip()
                content = match.group(2).strip()
                if not content:
                    continue

                if lang == "java":
                    file_path = self._deduce_java_file_path(content)
                    if file_path:
                        normalized = self._normalize_path(file_path, lang)
                        files[normalized] = content

        return files

    def _deduce_java_file_path(self, java_content: str) -> str:
        package_match = re.search(r"package\s+([\w.]+);", java_content)
        class_match = re.search(r"(?:public\s+)?(?:class|interface|enum)\s+(\w+)", java_content)

        if package_match and class_match:
            package = package_match.group(1)
            class_name = class_match.group(1)
            package_path = package.replace(".", "/")
            return f"src/main/java/{package_path}/{class_name}.java"

        return None

    def extract_single_code_block(self, text: str, language: str = "java") -> str:
        match = re.search(rf"```{language}\s*(.*?)\s*```", text, re.DOTALL)
        return match.group(1).strip() if match else text.strip()


class FallbackException(Exception):
    """Exception interne pour déclencher le passage au provider suivant."""

    def __init__(self, message: str, disable_provider: bool = False):
        super().__init__(message)
        self.disable_provider = disable_provider
