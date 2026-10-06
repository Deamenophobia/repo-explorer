import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from repo_explorer.api import create_app
from repo_explorer.config import Settings, load_settings
from repo_explorer.generation import ExtractiveGenerator
from repo_explorer.plugins import default_registry

CORPUS = Path(__file__).resolve().parents[2] / "examples" / "repository"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        corpus_dir=CORPUS, data_dir=tmp_path / "data", config_file=tmp_path / "settings.json"
    )


def test_saved_configuration_changes_retrieval_and_survives_restart(settings, monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_KEY", "secret-value-never-serialized")
    with TestClient(create_app(settings)) as client:
        values = client.get("/api/settings").json()["values"]
        values.update(
            workspace_name="My engineering team",
            retrieval_limit=1,
            chat_api_key_env="PRIVATE_CHAT_KEY",
        )
        response = client.put("/api/settings", json=values)
        assert response.status_code == 200
        assert "secret-value" not in response.text
        run = client.post("/api/runs", json={"question": "repository ingestion"}).json()
        assert len(run["citations"]) == 1
    monkeypatch.setenv("REPO_EXPLORER_CONFIG_FILE", str(settings.config_file))
    monkeypatch.setenv("REPO_EXPLORER_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("REPO_EXPLORER_WORKSPACE_NAME", "Environment fallback")
    restarted = load_settings()
    assert restarted.workspace_name == "My engineering team"
    assert "secret-value" not in settings.config_file.read_text()
    with TestClient(create_app(restarted)) as client:
        assert client.get("/api/corpus").json()["workspace_name"] == "My engineering team"


@pytest.mark.parametrize(
    "changes",
    [
        {"chunk_size": 100, "chunk_overlap": 150},
        {"source_provider": "missing-adapter"},
        {"corpus_dir": "does-not-exist"},
        {"chat_api_key_env": "sk-secret-value"},
        {"base_url": "https://user:secret@example.com"},
    ],
)
def test_invalid_updates_keep_active_configuration(settings, changes):
    with TestClient(create_app(settings)) as client:
        original = client.get("/api/settings").json()["values"]
        assert client.put("/api/settings", json={**original, **changes}).status_code == 422
        assert client.get("/api/settings").json()["values"] == original
        assert not settings.config_file.exists()


def test_write_failure_keeps_active_configuration(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:
        original = client.get("/api/settings").json()["values"]

        def fail(*args):
            raise OSError("disk unavailable")

        monkeypatch.setattr("repo_explorer.runtime.os.replace", fail)
        assert (
            client.put("/api/settings", json={**original, "workspace_name": "unsaved"}).status_code
            == 422
        )
        assert client.get("/api/settings").json()["values"] == original


def test_pending_review_retains_evidence_after_reconfiguration(settings):
    with TestClient(create_app(settings)) as client:
        run = client.post(
            "/api/runs", json={"question": "human review checkpoint policy", "intent": "review"}
        ).json()
        assert run["status"] == "awaiting_review"
        values = client.get("/api/settings").json()["values"]
        assert client.put("/api/settings", json={**values, "retrieval_limit": 1}).status_code == 200
        resumed = client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).json()
        assert resumed["status"] == "approved"
        assert resumed["citations"] == run["citations"]
        assert resumed["answer"] == run["answer"]


def test_custom_generator_registered_without_graph_changes(settings):
    registry = default_registry()
    calls = []

    def factory(config, plugins):
        calls.append(config.model)
        return ExtractiveGenerator(1)

    registry.register("generators", "custom", factory)
    configured = Settings(
        **{**settings.model_dump(), "mode": "live", "model": "custom-local", "generator": "custom"}
    )
    with TestClient(create_app(configured, registry)) as client:
        assert "custom" in client.get("/api/settings").json()["adapters"]["generators"]
        assert (
            client.post("/api/runs", json={"question": "repository ingestion"}).json()["status"]
            == "completed"
        )
    assert calls == ["custom-local"]


def test_file_extensions_and_chunking_are_effective(settings, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "guide.txt").write_text("Repository ingestion evidence. " * 40)
    values = settings.public().model_dump(mode="json")
    values.update(corpus_dir=str(corpus), extensions=[".txt"], chunk_size=200, chunk_overlap=20)
    with TestClient(create_app(settings)) as client:
        assert client.put("/api/settings", json=values).status_code == 200
        result = client.get("/api/corpus").json()
        assert [file["path"] for file in result["files"]] == ["guide.txt"]
        assert result["chunks"] > 1
    assert json.loads(settings.config_file.read_text())["chunk_size"] == 200


def test_chat_and_embedding_configuration_are_independent(settings, monkeypatch):
    import langchain_openai
    from repo_explorer.plugins import openai_chat, openai_embeddings

    monkeypatch.setenv("TEST_CHAT_KEY", "chat-dummy")
    monkeypatch.setenv("TEST_EMBED_KEY", "embedding-dummy")
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **kwargs: kwargs)
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", lambda **kwargs: kwargs)
    configured = Settings(
        **{
            **settings.model_dump(),
            "mode": "live",
            "model": "chat-model",
            "base_url": "https://chat.example/v1",
            "chat_api_key_env": "TEST_CHAT_KEY",
            "embedding_provider": "openai",
            "embedding_model": "embedding-model",
            "embedding_base_url": "https://embeddings.example/v1",
            "embedding_api_key_env": "TEST_EMBED_KEY",
        }
    )
    chat = openai_chat(configured)
    embeddings = openai_embeddings(configured, [])
    assert chat["base_url"] == "https://chat.example/v1"
    assert chat["api_key"] == "chat-dummy"
    assert chat["model"] == "chat-model"
    assert embeddings["base_url"] == "https://embeddings.example/v1"
    assert embeddings["api_key"] == "embedding-dummy"
    assert embeddings["model"] == "embedding-model"


@pytest.mark.parametrize(
    "provider,module", [("anthropic", "langchain_anthropic"), ("ollama", "langchain_ollama")]
)
def test_optional_chat_adapter_constructs_structured_pipeline(
    settings, monkeypatch, provider, module
):
    pytest.importorskip(module)
    from repo_explorer.generation import ChatAnswerGenerator

    monkeypatch.setenv("REPO_EXPLORER_TEST_KEY", "dummy-not-a-real-key")
    config = Settings(
        **{
            **settings.model_dump(),
            "mode": "live",
            "model": "test-model",
            "chat_provider": provider,
            "chat_api_key_env": "REPO_EXPLORER_TEST_KEY",
        }
    )
    adapter = default_registry().build("chat", provider, config)
    assert ChatAnswerGenerator(config, adapter) is not None


def test_optional_ollama_embedding_adapter_constructs(settings):
    pytest.importorskip("langchain_ollama")
    config = Settings(
        **{
            **settings.model_dump(),
            "mode": "live",
            "model": "test-chat",
            "embedding_provider": "ollama",
            "embedding_model": "test-embedding",
            "embedding_base_url": "http://127.0.0.1:11434",
        }
    )
    adapter = default_registry().build("embeddings", "ollama", config, [])
    assert adapter.model == "test-embedding"
    assert adapter.base_url == "http://127.0.0.1:11434"
