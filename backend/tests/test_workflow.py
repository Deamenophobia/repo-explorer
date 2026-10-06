from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from repo_explorer.api import create_app
from repo_explorer.config import Settings
from repo_explorer.generation import ExtractiveGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.workflow import build_workflow

CORPUS = Path(__file__).resolve().parents[2] / "examples" / "repository"


@pytest.fixture
def settings(tmp_path):
    return Settings(corpus_dir=CORPUS, data_dir=tmp_path, mode="demo", embedding_model="")


def test_answer_has_exact_source_provenance(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/runs", json={"question": "How does repository ingestion work?"}
        )
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "completed"
        assert run["citations"]
        cited = {source["id"] for source in run["citations"]}
        assert {
            support["source_id"]
            for node in run["evidence_map"]["nodes"]
            for support in node["sources"]
        } == cited
        for citation in run["citations"]:
            source = (CORPUS / citation["path"]).read_text(encoding="utf-8")
            assert citation["excerpt"] in source
            lines = source.splitlines()[citation["start_line"] - 1 : citation["end_line"]]
            assert citation["excerpt"] in "\n".join(lines)


@pytest.mark.parametrize("approved,status", [(True, "approved"), (False, "rejected")])
def test_review_survives_app_restart_and_decision_is_final(settings, approved, status):
    with TestClient(create_app(settings)) as client:
        run = client.post(
            "/api/runs",
            json={
                "question": "Review the human review checkpoint policy",
                "intent": "review",
            },
        ).json()
        assert run["status"] == "awaiting_review"
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/runs/{run['id']}").json()["status"] == "awaiting_review"
        response = client.post(f"/api/runs/{run['id']}/decision", json={"approved": approved})
        assert response.json()["status"] == status
        assert response.json()["answer"] == run["answer"]
        assert (
            client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).status_code
            == 409
        )


def test_missing_evidence_does_not_call_generator(settings):
    class ForbiddenGenerator:
        def generate(self, *args):
            raise AssertionError("Generation must not run without evidence")

    graph = build_workflow(KnowledgeIndex(settings), ForbiddenGenerator(), InMemorySaver())
    result = graph.invoke(
        {"question": "zyzzyva quokka nebula", "intent": "question"},
        {"configurable": {"thread_id": "missing"}},
    )
    assert result["status"] == "insufficient_evidence"
    assert result["steps"] == ["retrieve", "abstain"]


def test_unknown_citation_cannot_reach_review(settings):
    class InvalidGenerator:
        def generate(self, *args):
            return {"answer": "Invented claim [S999]", "citation_ids": ["S999"]}

    graph = build_workflow(KnowledgeIndex(settings), InvalidGenerator(), InMemorySaver())
    result = graph.invoke(
        {"question": "checkpoint review", "intent": "review"},
        {"configurable": {"thread_id": "invalid"}},
    )
    assert result["status"] == "invalid_citations"
    assert result["evidence_map"] is None
    assert "__interrupt__" not in result


def test_hidden_files_and_dependencies_are_not_indexed(tmp_path):
    (tmp_path / "safe.md").write_text("Repository checkpoint review evidence", encoding="utf-8")
    (tmp_path / ".secret.md").write_text("secret", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.md").write_text("hidden", encoding="utf-8")
    index = KnowledgeIndex(Settings(corpus_dir=tmp_path, mode="demo", embedding_model=""))
    assert [item["path"] for item in index.files] == ["safe.md"]


def test_policy_is_passed_even_when_not_retrieved(settings):
    class PolicyObserver(ExtractiveGenerator):
        def generate(self, question, intent, sources, policy):
            assert "Human review" in policy
            return super().generate(question, intent, sources, policy)

    graph = build_workflow(KnowledgeIndex(settings), PolicyObserver(), InMemorySaver())
    result = graph.invoke(
        {"question": "ingestion chunks", "intent": "question"},
        {"configurable": {"thread_id": "policy"}},
    )
    assert result["status"] == "completed"


def test_http_validation(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/runs", json={"question": "   "}).status_code == 422
        assert client.get("/api/runs/00000000-0000-0000-0000-000000000000").status_code == 404
