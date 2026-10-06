"""Public workspace configuration and server-only settings have separate schemas."""

import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_name: str = Field(default="My workspace", min_length=1, max_length=80)
    repository_name: str = Field(
        default="repo-explorer / reference-repository", min_length=1, max_length=100
    )
    corpus_description: str = Field(default="Curated teaching corpus", max_length=180)
    suggestions: list[str] = Field(
        default_factory=lambda: [
            "How does repository ingestion preserve source references?",
            "How do checkpoints make human review durable?",
            "What are the application architecture boundaries?",
        ],
        max_length=8,
    )
    mode: Literal["demo", "live"] = "demo"
    generator: str = "chat"
    chat_provider: str = "openai"
    model: str = ""
    base_url: str | None = None
    chat_api_key_env: str = Field(
        default="", pattern=r"^([A-Za-z_][A-Za-z0-9_]*)?$", max_length=120
    )
    request_timeout: float = Field(default=45, ge=1, le=300)
    max_retries: int = Field(default=1, ge=0, le=5)
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    demo_excerpt_limit: int = Field(default=2, ge=1, le=50)
    source_provider: str = "local"
    corpus_dir: Path = Field(default_factory=lambda: Path("examples/repository"))
    policy_file: str = "POLICY.md"
    extensions: list[str] = Field(default_factory=lambda: [".md", ".py", ".ts", ".tsx", ".rs"])
    excluded_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "node_modules",
            ".repo-explorer",
            "dist",
            "__pycache__",
        ]
    )
    max_file_bytes: int = Field(default=200_000, ge=100, le=10_000_000)
    max_chunks: int = Field(default=2000, ge=1, le=20_000)
    chunk_size: int = Field(default=1100, ge=100, le=20_000)
    chunk_overlap: int = Field(default=150, ge=0, le=10_000)
    embedding_provider: str = "tfidf"
    embedding_model: str = ""
    embedding_base_url: str | None = None
    embedding_api_key_env: str = Field(
        default="", pattern=r"^([A-Za-z_][A-Za-z0-9_]*)?$", max_length=120
    )
    vector_store: str = "memory"
    retrieval_limit: int = Field(default=4, ge=1, le=50)
    minimum_score: float = Field(default=0.12, ge=-1, le=1)
    lexical_stop_words: Literal["english", "none"] = "english"
    lexical_ngram_max: int = Field(default=2, ge=1, le=3)
    lexical_tokenization: Literal["standard", "code_identifiers"] = "standard"
    context_expander: str = "none"
    context_window_lines: int = Field(default=8, ge=1, le=100)
    context_max_added_chars: int = Field(default=4000, ge=0, le=50_000)
    source_analyzer: str = "none"
    source_symbol_limit: int = Field(default=8, ge=1, le=100)
    evidence_map_node_limit: int = Field(default=40, ge=2, le=200)
    plugin_options: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_combinations(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        if self.mode == "live" and not self.model.strip():
            raise ValueError("Choose a model for live mode.")
        if self.chat_provider == "codex" and (self.base_url or self.chat_api_key_env):
            raise ValueError(
                "Codex uses CLI sign-in; leave chat endpoint and credential fields empty."
            )
        if self.embedding_provider != "tfidf":
            if self.mode == "demo":
                raise ValueError(
                    "Demo mode uses local TF-IDF. Choose live mode for other embeddings."
                )
            if not self.embedding_model.strip():
                raise ValueError("Choose an embedding model for the selected adapter.")
        if self.embedding_provider == "fastembed" and (
            self.embedding_base_url or self.embedding_api_key_env
        ):
            raise ValueError(
                "FastEmbed runs locally; leave embedding endpoint and credential empty."
            )
        policy = Path(self.policy_file)
        if policy.is_absolute() or ".." in policy.parts:
            raise ValueError("Policy file must be relative to the corpus directory.")
        if not self.extensions or any(not item.startswith(".") for item in self.extensions):
            raise ValueError("File extensions must begin with a dot.")
        for endpoint in (self.base_url, self.embedding_base_url):
            if endpoint:
                parsed = urlsplit(endpoint)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    raise ValueError("Provider endpoints must be HTTP or HTTPS URLs.")
                if parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError("Keep credentials and query parameters out of provider URLs.")
        return self


class Settings(WorkspaceConfig, BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPO_EXPLORER_", env_file=".env", extra="ignore")
    data_dir: Path = Path(".repo-explorer")
    config_file: Path = Path("repo-explorer.json")
    codex_executable: str = ""
    codex_proxy_url: SecretStr | None = Field(default=None, repr=False)
    fastembed_cache_dir: Path = Path(".repo-explorer/models")
    fastembed_threads: int = Field(default=2, ge=1, le=64)
    fastembed_local_files_only: bool = False
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("codex_proxy_url")
    @classmethod
    def validate_codex_proxy(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value():
            return None
        raw = value.get_secret_value()
        parsed = urlsplit(raw)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in raw)
        ):
            raise ValueError("Codex proxy must be an HTTP or HTTPS proxy URL.")
        _ = parsed.port
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or any(character.isspace() for character in origin)
                or "*" in origin
            ):
                raise ValueError(
                    "CORS origins must be explicit HTTP or HTTPS origins, "
                    "without credentials, paths, trailing slashes, queries, or fragments."
                )
            # Accessing port validates its syntax and range even though origins remain strings.
            _ = parsed.port
        return origins

    def public(self) -> WorkspaceConfig:
        return WorkspaceConfig.model_validate(
            self.model_dump(include=set(WorkspaceConfig.model_fields))
        )

    def credential(self, variable: str) -> str | None:
        return os.environ.get(variable) or dotenv_values(".env").get(variable)


def load_settings() -> Settings:
    path = Path(
        os.environ.get("REPO_EXPLORER_CONFIG_FILE")
        or dotenv_values(".env").get("REPO_EXPLORER_CONFIG_FILE")
        or "repo-explorer.json"
    )
    overrides = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    unknown = set(overrides) - set(WorkspaceConfig.model_fields)
    if unknown:
        raise ValueError(f"Unknown public configuration fields: {', '.join(sorted(unknown))}")
    return Settings(**overrides, config_file=path)
