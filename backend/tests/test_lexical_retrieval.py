from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from repo_explorer.api import create_app
from repo_explorer.config import Settings, load_settings
from repo_explorer.knowledge import KnowledgeIndex

CORPUS = Path(__file__).resolve().parents[2] / "examples" / "identifier-repository"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        corpus_dir=CORPUS,
        config_file=tmp_path / "settings.json",
        data_dir=tmp_path / "data",
        mode="demo",
        embedding_provider="tfidf",
        lexical_tokenization="standard",
    )


@pytest.mark.parametrize("query", ["cache_lookup", "cacheLookup", "CacheLookup", "cache lookup"])
def test_identifier_queries_find_both_spellings_with_original_evidence(settings, query):
    index = KnowledgeIndex(
        Settings(**{**settings.model_dump(), "lexical_tokenization": "code_identifiers"})
    )
    hits = index.search(query)
    assert {hit["path"] for hit in hits} == {"cache_store.py", "cache_client.ts"}
    for hit in hits:
        source = (CORPUS / hit["path"]).read_text(encoding="utf-8")
        assert hit["excerpt"] in source
        assert hit["excerpt"] in "\n".join(
            source.splitlines()[hit["start_line"] - 1 : hit["end_line"]]
        )


def test_acronym_queries_find_camel_case_names_without_inventing_synonyms(settings):
    index = KnowledgeIndex(
        Settings(**{**settings.model_dump(), "lexical_tokenization": "code_identifiers"})
    )
    assert index.search("HTTP transport")[0]["path"] == "http_transport.py"
    assert index.search("zyzzyva quokka nebula") == []
    assert index.search("remembered object missing") == []


def test_api_setting_changes_retrieval_and_survives_restart(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:
        before = client.post("/api/runs", json={"question": "cache lookup"}).json()
        assert before["status"] == "insufficient_evidence"
        values = client.get("/api/settings").json()["values"]
        changed = client.put(
            "/api/settings", json={**values, "lexical_tokenization": "code_identifiers"}
        )
        assert changed.status_code == 200
        assert client.get("/api/corpus").json()["retrieval"] == "TF-IDF / code identifiers"
        result = client.post("/api/runs", json={"question": "cache lookup"}).json()
        assert result["status"] == "completed"
        assert result["retrieval"] == "TF-IDF / code identifiers"
        assert {citation["path"] for citation in result["citations"]} == {
            "cache_store.py",
            "cache_client.ts",
        }
        assert client.get(f"/api/runs/{before['id']}").json() == before
    monkeypatch.setenv("REPO_EXPLORER_CONFIG_FILE", str(settings.config_file))
    monkeypatch.setenv("REPO_EXPLORER_DATA_DIR", str(settings.data_dir))
    with TestClient(create_app(load_settings())) as client:
        assert client.get("/api/settings").json()["values"]["lexical_tokenization"] == (
            "code_identifiers"
        )
        assert client.get(f"/api/runs/{result['id']}").json() == result
