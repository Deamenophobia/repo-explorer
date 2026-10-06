import sys
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from repo_explorer.config import Settings
from repo_explorer.embeddings import FastEmbedEmbeddings
from repo_explorer.plugins import builtin_registry


def test_fastembed_uses_distinct_query_and_passage_paths_without_remote_credentials(monkeypatch):
    calls = []

    class Model:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def passage_embed(self, texts):
            calls.append(("passages", texts))
            yield from (np.array([1.0, 0.0]) for _ in texts)

        def query_embed(self, text):
            calls.append(("query", text))
            yield np.array([0.0, 1.0])

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=Model))
    settings = Settings(
        mode="live",
        model="chat-fixture",
        embedding_provider="fastembed",
        embedding_model="selected-model",
        fastembed_cache_dir="operator-cache",
        fastembed_threads=3,
        fastembed_local_files_only=True,
    )
    adapter = builtin_registry().build("embeddings", "fastembed", settings, [])
    assert adapter.embed_documents(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    assert adapter.embed_query("question") == [0.0, 1.0]
    assert adapter.embed_documents([]) == []
    assert calls[0] == {
        "model_name": "selected-model",
        "cache_dir": "operator-cache",
        "threads": 3,
        "local_files_only": True,
    }
    assert ("query", "question") in calls
    assert ("passages", ["a", "b"]) in calls
    assert not any(name.startswith("fastembed_") for name in settings.public().model_dump())


def test_missing_optional_package_fails_without_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)
    with pytest.raises(ValueError, match="Install the fastembed extra"):
        FastEmbedEmbeddings(Settings(), [])


@pytest.mark.parametrize(
    "overrides",
    [
        {"embedding_base_url": "http://localhost:9999"},
        {"embedding_api_key_env": "UNUSED_KEY"},
        {"embedding_model": ""},
    ],
)
def test_local_embedding_configuration_rejects_unused_or_missing_settings(overrides):
    with pytest.raises(ValidationError):
        Settings(
            **{
                "mode": "live",
                "model": "chat-fixture",
                "embedding_provider": "fastembed",
                "embedding_model": "selected-model",
                **overrides,
            }
        )


def test_failed_local_model_preparation_preserves_active_workspace(tmp_path, monkeypatch):
    from pathlib import Path

    from repo_explorer.api import create_app
    from repo_explorer.generation import ExtractiveGenerator

    settings = Settings(
        corpus_dir=Path(__file__).resolve().parents[2] / "examples/repository",
        config_file=tmp_path / "settings.json",
        data_dir=tmp_path / "runtime",
    )
    registry = builtin_registry()
    registry.factories["generators"]["chat"] = lambda *args: ExtractiveGenerator()
    attempted = []

    def unavailable(**kwargs):
        attempted.append(kwargs["model_name"])
        raise ValueError("Model unavailable in operator cache")

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=unavailable))
    with TestClient(create_app(settings, registry)) as client:
        current = client.get("/api/settings").json()
        assert "fastembed" in current["adapters"]["embeddings"]
        changed = {
            **current["values"],
            "mode": "live",
            "model": "chat-fixture",
            "embedding_provider": "fastembed",
            "embedding_model": "selected-model",
        }
        assert client.put("/api/settings", json=changed).status_code == 422
        assert client.get("/api/settings").json()["values"] == current["values"]
        assert not settings.config_file.exists()
    assert attempted == ["selected-model"]
