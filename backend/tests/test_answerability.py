from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from repo_explorer.api import create_app
from repo_explorer.config import Settings
from repo_explorer.generation import ExtractiveGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import builtin_registry
from repo_explorer.schemas import DraftAnswer
from repo_explorer.service import RunService
from repo_explorer.workflow import build_workflow

CORPUS = Path(__file__).resolve().parents[2] / "examples/repository"


def configured_app(tmp_path, draft):
    calls = []

    class Generator:
        def generate(self, *args):
            calls.append(args)
            return draft

    settings = Settings(
        corpus_dir=CORPUS,
        data_dir=tmp_path,
        mode="live",
        model="fixture",
    )
    registry = builtin_registry()
    registry.factories["generators"]["chat"] = lambda *args: Generator()
    return settings, registry, calls


@pytest.mark.parametrize("assessment", ["complete", "partial"])
def test_review_preserves_assessment_and_limitations_across_restart(tmp_path, assessment):
    limitations = ["The supplied excerpt omits error handling."] if assessment == "partial" else []
    draft = {
        "answer": "Checkpointed review brief [S1].",
        "citation_ids": ["S1"],
        "answerability": assessment,
        "limitations": limitations,
    }
    settings, registry, calls = configured_app(tmp_path, draft)
    with TestClient(create_app(settings, registry)) as client:
        run = client.post(
            "/api/runs",
            json={
                "question": "human review checkpoint",
                "intent": "review",
            },
        ).json()
        assert run["status"] == "awaiting_review"
        assert run["answerability"] == assessment
        assert run["limitations"] == limitations
    with TestClient(create_app(settings, registry)) as client:
        assert client.get(f"/api/runs/{run['id']}").json() == run
        decision = client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).json()
        assert decision["status"] == "approved"
        assert decision["answerability"] == assessment
        assert decision["limitations"] == limitations
        assert decision["answer"] == draft["answer"]
    assert len(calls) == 1


@pytest.mark.parametrize("cited", [False, True])
@pytest.mark.parametrize("intent", ["question", "review"])
def test_model_abstention_keeps_explanation_and_never_offers_review(tmp_path, cited, intent):
    answer = "The production region is absent from the supplied evidence."
    draft = {
        "answer": answer + (" [S1]" if cited else ""),
        "citation_ids": ["S1"] if cited else [],
        "answerability": "insufficient_evidence",
        "limitations": ["Deployment configuration was not supplied."],
    }
    settings, registry, calls = configured_app(tmp_path, draft)
    with TestClient(create_app(settings, registry)) as client:
        run = client.post(
            "/api/runs",
            json={
                "question": "Which production region hosts human review?",
                "intent": intent,
            },
        ).json()
        assert run["status"] == "insufficient_evidence"
        assert run["answerability"] == "insufficient_evidence"
        assert run["answer"] == draft["answer"]
        assert run["limitations"] == draft["limitations"]
        assert run["steps"] == ["retrieve", "compose", "validate"]
        assert (
            client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).status_code
            == 409
        )
        assert client.get(f"/api/runs/{run['id']}").json() == run
    assert len(calls) == 1


@pytest.mark.parametrize("assessment", ["complete", "partial", "insufficient_evidence"])
def test_assessment_cannot_bypass_citation_validation(tmp_path, assessment):
    draft = {
        "answer": "Unverifiable reference [S999].",
        "citation_ids": ["S999"],
        "answerability": assessment,
        "limitations": [] if assessment == "complete" else ["Missing context."],
    }
    settings, registry, _ = configured_app(tmp_path, draft)
    with TestClient(create_app(settings, registry)) as client:
        run = client.post(
            "/api/runs",
            json={
                "question": "human review checkpoint",
                "intent": "review",
            },
        ).json()
    assert run["status"] == "invalid_citations"
    assert run["answerability"] == "not_assessed"
    assert run["citations"] == []
    assert "S999" not in run["answer"]
    assert "review" not in run["steps"]


@pytest.mark.parametrize(
    "assessment,limitations",
    [
        ("complete", ["Missing context."]),
        ("partial", []),
        ("insufficient_evidence", []),
        ("partial", [" "]),
    ],
)
def test_model_classification_requires_consistent_qualifications(assessment, limitations):
    with pytest.raises(ValidationError):
        DraftAnswer(
            answer="Answer [S1].",
            citation_ids=["S1"],
            answerability=assessment,
            limitations=limitations,
        )


def test_citations_inside_limitations_are_validated_too(tmp_path):
    settings, registry, _ = configured_app(
        tmp_path,
        {
            "answer": "Known implementation [S1].",
            "citation_ids": ["S1"],
            "answerability": "partial",
            "limitations": ["Deployment was omitted [S999]."],
        },
    )
    with TestClient(create_app(settings, registry)) as client:
        run = client.post("/api/runs", json={"question": "human review checkpoint"}).json()
    assert run["status"] == "invalid_citations"
    assert run["limitations"] == []


def test_older_checkpoint_can_resume_without_reclassifying_its_answer(tmp_path):
    settings = Settings(corpus_dir=CORPUS, data_dir=tmp_path)
    index = KnowledgeIndex(settings)
    graph = build_workflow(index, ExtractiveGenerator(), InMemorySaver())
    service = RunService(graph)
    run_id = "legacy"
    graph.update_state(
        service.config(run_id),
        {
            "question": "human review checkpoint",
            "intent": "review",
            "status": "validated",
            "answer": "Previously saved brief [S1].",
            "citation_ids": ["S1"],
            "sources": index.search("human review checkpoint"),
            "steps": ["retrieve", "compose", "validate"],
            "mode": "live",
        },
        as_node="validate",
    )
    graph.invoke(None, service.config(run_id))
    assert service.get(run_id).status == "awaiting_review"
    assert service.get(run_id).answerability == "not_assessed"
    resumed = service.decide(run_id, True)
    assert resumed.status == "approved"
    assert resumed.answerability == "not_assessed"
    assert resumed.limitations == []
