"""Explicit factory registries; only installed server plugins execute Python code."""

from collections.abc import Callable
from importlib.metadata import entry_points

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from sklearn.feature_extraction.text import TfidfVectorizer

from repo_explorer.analysis import NoSourceAnalyzer, PythonSourceAnalyzer
from repo_explorer.config import Settings
from repo_explorer.context import LineWindowExpander, NoContextExpander
from repo_explorer.embeddings import FastEmbedEmbeddings
from repo_explorer.lexical import code_identifier_tokens
from repo_explorer.sources import local_source


class PluginRegistry:
    def __init__(self):
        self.factories: dict[str, dict[str, Callable]] = {
            kind: {}
            for kind in (
                "chat",
                "embeddings",
                "stores",
                "sources",
                "generators",
                "expanders",
                "analyzers",
            )
        }

    def register(self, kind: str, name: str, factory: Callable) -> None:
        if name in self.factories[kind]:
            raise ValueError(f"Duplicate {kind} adapter: {name}")
        self.factories[kind][name] = factory

    def build(self, kind: str, name: str, *args):
        if name not in self.factories[kind]:
            raise ValueError(f"Unknown {kind} adapter: {name}")
        return self.factories[kind][name](*args)

    def catalog(self) -> dict[str, list[str]]:
        return {kind: sorted(factories) for kind, factories in self.factories.items()}


class TfidfEmbeddings(Embeddings):
    def __init__(self, settings: Settings, texts: list[str]):
        tokenization = (
            {"tokenizer": code_identifier_tokens, "token_pattern": None, "lowercase": False}
            if settings.lexical_tokenization == "code_identifiers"
            else {}
        )
        self.vectorizer = TfidfVectorizer(
            stop_words=None if settings.lexical_stop_words == "none" else "english",
            ngram_range=(1, settings.lexical_ngram_max),
            **tokenization,
        ).fit(texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.vectorizer.transform(texts).toarray().tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def openai_chat(settings: Settings):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.credential(settings.chat_api_key_env or "OPENAI_API_KEY"),
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


def anthropic_chat(settings: Settings):
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ValueError("Install the anthropic extra: pip install -e '.[anthropic]'") from exc
    return ChatAnthropic(
        model_name=settings.model,
        base_url=settings.base_url,
        api_key=settings.credential(settings.chat_api_key_env or "ANTHROPIC_API_KEY"),
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


def ollama_chat(settings: Settings):
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ValueError("Install the ollama extra: pip install -e '.[ollama]'") from exc
    return ChatOllama(
        model=settings.model,
        base_url=settings.base_url,
        client_kwargs={"timeout": settings.request_timeout},
    )


def codex_chat(settings: Settings):
    from repo_explorer.codex_model import CodexChatModel, codex_version, resolve_codex_executable

    executable = resolve_codex_executable(settings.codex_executable)
    return CodexChatModel(
        executable=executable,
        cli_version=codex_version(executable),
        model_name=settings.model,
        timeout_seconds=settings.request_timeout,
        reasoning_effort=settings.codex_reasoning_effort,
        proxy_url=settings.codex_proxy_url,
    )


def openai_embeddings(settings: Settings, texts: list[str]):
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        api_key=settings.credential(settings.embedding_api_key_env or "OPENAI_API_KEY"),
        request_timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


def ollama_embeddings(settings: Settings, texts: list[str]):
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError as exc:
        raise ValueError("Install the ollama extra: pip install -e '.[ollama]'") from exc
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        client_kwargs={"timeout": settings.request_timeout},
    )


def builtin_registry() -> PluginRegistry:
    """Build the shipped adapters without importing installed plugin entry points."""
    from repo_explorer.generation import ChatAnswerGenerator

    registry = PluginRegistry()
    for name, factory in [
        ("openai", openai_chat),
        ("anthropic", anthropic_chat),
        ("ollama", ollama_chat),
        ("codex", codex_chat),
    ]:
        registry.register("chat", name, factory)
    for name, factory in [
        ("tfidf", TfidfEmbeddings),
        ("fastembed", FastEmbedEmbeddings),
        ("openai", openai_embeddings),
        ("ollama", ollama_embeddings),
    ]:
        registry.register("embeddings", name, factory)
    registry.register(
        "stores", "memory", lambda settings, embeddings: InMemoryVectorStore(embeddings)
    )
    registry.register("sources", "local", local_source)
    registry.register("expanders", "none", NoContextExpander)
    registry.register("expanders", "line_window", LineWindowExpander)
    registry.register("analyzers", "none", NoSourceAnalyzer)
    registry.register("analyzers", "python_ast", PythonSourceAnalyzer)
    registry.register(
        "generators",
        "chat",
        lambda settings, plugins: ChatAnswerGenerator(
            settings, plugins.build("chat", settings.chat_provider, settings)
        ),
    )
    return registry


def default_registry() -> PluginRegistry:
    registry = builtin_registry()
    for plugin in entry_points(group="repo_explorer.plugins"):
        plugin.load()(registry)
    return registry
