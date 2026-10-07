"""
Centralized project configuration.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


AGENT_MODEL_DEFAULTS = {
    "advisor": os.getenv("MODEL_ADVISOR", "Qwen/Qwen2.5-72B-Instruct"),
    "developer": os.getenv("MODEL_DEVELOPER", "Qwen/Qwen2.5-Coder-32B-Instruct"),
    "tester": os.getenv("MODEL_TESTER", "meta-llama/Llama-3.1-8B-Instruct"),
    "reviewer": os.getenv("MODEL_REVIEWER", "Qwen/Qwen2.5-72B-Instruct"),
    "analyzer": os.getenv("MODEL_ANALYZER", "Qwen/Qwen2.5-72B-Instruct"),
    "planner": os.getenv("MODEL_PLANNER", "Qwen/Qwen2.5-72B-Instruct"),
    "fixer": os.getenv("MODEL_FIXER", "Qwen/Qwen2.5-Coder-32B-Instruct"),
}


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _split_csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class EncryptionConfig:
    key: str = field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", ""))

    def is_configured(self) -> bool:
        return bool(self.key)


@dataclass
class AuthConfig:
    secret_key: str = field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-a-long-random-string"))
    algorithm: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    )


@dataclass
class AppConfig:
    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    debug: bool = field(default_factory=lambda: env_bool("APP_DEBUG", default=False))
    cors_allow_origins: list[str] = field(
        default_factory=lambda: _split_csv_env("CORS_ALLOW_ORIGINS", "*")
    )

    def is_production(self) -> bool:
        return self.env.lower() == "production"


@dataclass
class JiraConfig:
    url: str = field(default_factory=lambda: os.getenv("JIRA_URL", "https://yourcompany.atlassian.net"))
    username: str = field(default_factory=lambda: os.getenv("JIRA_USERNAME", ""))
    api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))
    project_key: str = field(default_factory=lambda: os.getenv("JIRA_PROJECT_KEY", "PROJ"))


@dataclass
class GitHubConfig:
    token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    owner: str = field(default_factory=lambda: os.getenv("GITHUB_OWNER", ""))
    repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))
    default_branch: str = field(default_factory=lambda: os.getenv("GITHUB_DEFAULT_BRANCH", "main"))
    base_branch: str = field(default_factory=lambda: os.getenv("GITHUB_BASE_BRANCH", ""))


@dataclass
class HuggingFaceConfig:
    api_key: str = field(default_factory=lambda: os.getenv("HF_TOKEN", ""))
    base_url: str = "https://api-inference.huggingface.co/v1"
    max_tokens: int = 4096
    temperature: float = 0.2

    model_advisor: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["advisor"])
    model_developer: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["developer"])
    model_tester: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["tester"])
    model_reviewer: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["reviewer"])
    model_analyzer: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["analyzer"])
    model_planner: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["planner"])
    model_fixer: str = field(default_factory=lambda: AGENT_MODEL_DEFAULTS["fixer"])

    def resolve_model(self, model: str) -> str:
        return model


@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())

    def is_configured(self) -> bool:
        return bool(self.url)


@dataclass
class PipelineConfig:
    min_test_coverage: float = field(
        default_factory=lambda: float(os.getenv("MIN_TEST_COVERAGE", "80.0"))
    )
    max_skipped_tests: int = field(
        default_factory=lambda: int(os.getenv("MAX_SKIPPED_TESTS", "0"))
    )
    max_duplicate_code_percent: float = field(
        default_factory=lambda: float(os.getenv("MAX_DUPLICATE_CODE_PERCENT", "5.0"))
    )
    max_method_lines: int = field(
        default_factory=lambda: int(os.getenv("MAX_METHOD_LINES", "50"))
    )
    max_cyclomatic_complexity: int = field(
        default_factory=lambda: int(os.getenv("MAX_CYCLOMATIC_COMPLEXITY", "10"))
    )
    min_review_score: float = field(
        default_factory=lambda: float(os.getenv("MIN_REVIEW_SCORE", "70"))
    )
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./output/generated"))
    )
    docs_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DOCS_DIR", "./docs"))
    )
    logs_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LOGS_DIR", "./output/logs"))
    )
    artifacts_dir: Path = field(
        default_factory=lambda: Path(os.getenv("ARTIFACTS_DIR", "./output/artifacts"))
    )
    target_repo_path: Path = field(
        default_factory=lambda: Path(os.getenv("TARGET_REPO_PATH", "./base-spring-project"))
    )
    java_version: str = "21"
    spring_boot_version: str = "3.2.0"

    def get_project_root(self) -> Path:
        return Path(__file__).parent.parent.resolve()

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.get_project_root() / path


@dataclass
class Settings:
    app: AppConfig = field(default_factory=AppConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)
    jira: JiraConfig = field(default_factory=JiraConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    hf: HuggingFaceConfig = field(default_factory=HuggingFaceConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    def __post_init__(self):
        self.pipeline.output_dir = self.pipeline.resolve_path(self.pipeline.output_dir)
        self.pipeline.docs_dir = self.pipeline.resolve_path(self.pipeline.docs_dir)
        self.pipeline.logs_dir = self.pipeline.resolve_path(self.pipeline.logs_dir)
        self.pipeline.artifacts_dir = self.pipeline.resolve_path(self.pipeline.artifacts_dir)
        self.pipeline.target_repo_path = self.pipeline.resolve_path(self.pipeline.target_repo_path)

    def validate(self):
        errors = []
        if not self.hf.api_key:
            errors.append("HF_TOKEN manquant")
        if not self.github.token:
            errors.append("GITHUB_TOKEN manquant")
        if errors:
            raise ValueError(f"Configuration invalide: {', '.join(errors)}")
        return True
