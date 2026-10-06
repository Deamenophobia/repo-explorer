import json
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import Field, ValidationError
from repo_explorer.config import WorkspaceConfig
from repo_explorer.evaluation.live import run_live_evaluation
from repo_explorer.evaluation.live_models import LiveEvaluationConfig
from repo_explorer.evaluation.models import EvaluationSuite
from repo_explorer.evaluation.review import validate_review
from repo_explorer.evaluation.snapshot import digest
from repo_explorer.plugins import builtin_registry

ROOT = Path(__file__).resolve().parents[2]


class RecordingChat(FakeMessagesListChatModel):
    seen: list = Field(default_factory=list)

    def with_structured_output(self, schema, **kwargs):
        return self | PydanticOutputParser(pydantic_object=schema)

    def _generate(self, messages, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, **kwargs)


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    source = "def approve_plan():\n    return 'approval accepted'\n"
    (root / "review.py").write_text(source, encoding="utf-8")
    suite = EvaluationSuite.model_validate(
        {
            "name": "Local contract fixture",
            "scope": "Not a real provider evaluation.",
            "snapshot": {"files": [{"path": "review.py", "sha256": digest(source.encode())}]},
            "cases": [
                {
                    "id": "approve",
                    "question": "What does approve_plan return?",
                    "reference_notes": "REFERENCE_WITHHELD_FROM_MODEL",
                    "evidence": [
                        {
                            "id": "return",
                            "path": "review.py",
                            "start_line": 1,
                            "end_line": 2,
                            "quote": "return 'approval accepted'",
                        }
                    ],
                },
                {
                    "id": "missing",
                    "question": "zyzzyva nebula quokka",
                    "unanswerable": True,
                    "reference_notes": "The snapshot cannot answer this question.",
                },
            ],
        }
    )
    config = LiveEvaluationConfig(
        workspace=WorkspaceConfig(
            mode="live",
            model="local-test-double",
            chat_provider="fixture",
            max_retries=0,
        )
    )
    registry = builtin_registry()
    chat = RecordingChat(
        responses=[
            AIMessage(
                content=json.dumps(
                    {
                        "answer": "Returns approval accepted [S1].",
                        "citation_ids": ["S1"],
                        "answerability": "complete",
                        "limitations": [],
                    }
                ),
                response_metadata={"model_name": "fixture-model"},
                usage_metadata={"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
            )
        ]
    )
    registry.register("chat", "fixture", lambda settings: chat)
    return root, suite, config, registry, chat


def test_preflight_never_instantiates_providers_or_loads_plugins(experiment, tmp_path, monkeypatch):
    root, suite, config, registry, _ = experiment

    def forbidden(*args, **kwargs):
        raise AssertionError("Preflight must not call providers or installed plugins")

    for kind in ("chat", "embeddings", "generators"):
        for key in registry.factories[kind]:
            registry.factories[kind][key] = forbidden
    monkeypatch.setattr("repo_explorer.plugins.entry_points", forbidden)
    monkeypatch.setenv("REPO_EXPLORER_CORPUS_DIR", "outside-pinned-corpus")
    monkeypatch.setenv("REPO_EXPLORER_CONFIG_FILE", "does-not-exist.json")
    monkeypatch.setenv("REPO_EXPLORER_MODEL", "ignored-environment-model")
    result = run_live_evaluation(suite, root, tmp_path / "preflight", config, registry=registry)
    assert result["configuration_ready"] is True
    assert result["provider_connectivity_checked"] is False
    assert result["chat"]["model"] == "local-test-double"
    assert result["max_generation_attempts"] == 2
    assert not (tmp_path / "preflight/report.json").exists()
    # The default CLI path also excludes entry points.
    default = run_live_evaluation(suite, root, tmp_path / "default", LiveEvaluationConfig())
    assert default["configuration_ready"] is False


def test_real_graph_and_prompt_preserve_draft_and_withhold_annotations(experiment, tmp_path):
    root, suite, config, registry, chat = experiment
    config.workspace.source_analyzer = "python_ast"
    output = tmp_path / "run"
    report = run_live_evaluation(suite, root, output, config, execute=True, registry=registry)
    assert report["execution"] == "completed"
    answer, missing = report["cases"]
    assert report["generation_attempts"] == 1
    assert answer["outcome"] == "answered"
    assert answer["workflow"]["steps"] == ["retrieve", "compose", "validate", "finish"]
    evidence_map = answer["workflow"]["evidence_map"]
    assert [node["label"] for node in evidence_map["nodes"]] == ["review.py", "approve_plan"]
    assert len(evidence_map["edges"]) == 1
    saved = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert saved["cases"][0]["workflow"]["evidence_map"] == evidence_map
    assert "Saved evidence map" in (output / "report.md").read_text(encoding="utf-8")
    assert answer["generation"]["draft"]["answer"] == answer["workflow"]["answer"]
    assert answer["generation"]["reported_chat_usage"]["fixture-model"]["total_tokens"] == 38
    assert answer["generation"]["cost_usd"] is None
    assert answer["retrieval"]["context_evidence"]["evidence_coverage"] == 1
    assert missing["outcome"] == "no_context"
    assert missing["workflow"]["evidence_map"] is None
    assert missing["generation"]["attempts"] == 0
    assert missing["generation"]["reported_chat_usage"] is None
    assert len(chat.seen) == 1
    prompt = "\n".join(message.content for message in chat.seen[0])
    assert "REFERENCE_WITHHELD_FROM_MODEL" not in prompt
    assert "return 'approval accepted'" in prompt
    assert "What does approve_plan return?" in prompt
    assert all(
        item.status == "pending"
        for item in validate_review(output / "report.json", output / "review.json").cases.values()
    )


@pytest.mark.parametrize(
    "answer, ids",
    [
        ("Invented reference [S99].", ["S99"]),
        ("Cannot determine this from the supplied text.", []),
    ],
)
def test_invalid_citation_or_unclassified_abstention_is_not_counted_as_no_context(
    experiment, tmp_path, answer, ids
):
    root, suite, config, registry, chat = experiment
    chat.responses = [
        AIMessage(
            content=json.dumps(
                {
                    "answer": answer,
                    "citation_ids": ids,
                    "answerability": "complete",
                    "limitations": [],
                }
            )
        )
    ]
    report = run_live_evaluation(
        suite, root, tmp_path / "run", config, execute=True, registry=registry
    )
    result = report["cases"][0]
    assert result["outcome"] == "invalid_citations"
    assert result["workflow"]["evidence_map"] is None
    assert result["generation"]["draft"]["answer"] == answer
    assert result["workflow"]["answer"] != answer
    assert result["generation"]["reported_chat_usage"] is None
    assert result["retrieval"]["context_hits"]


@pytest.mark.parametrize(
    "assessment,ids,outcome",
    [
        ("partial", ["S1"], "partial"),
        ("insufficient_evidence", [], "model_abstention"),
        ("insufficient_evidence", ["S1"], "model_abstention"),
    ],
)
def test_evaluation_distinguishes_model_assessment_from_retrieval_abstention(
    experiment, tmp_path, assessment, ids, outcome
):
    root, suite, config, registry, chat = experiment
    draft = {
        "answer": "The supplied context does not establish the deployment region."
        + (" [S1]" if ids else ""),
        "citation_ids": ids,
        "answerability": assessment,
        "limitations": ["Deployment configuration is missing."],
    }
    chat.responses = [AIMessage(content=json.dumps(draft))]
    report = run_live_evaluation(
        suite, root, tmp_path / "run", config, execute=True, registry=registry
    )
    result, missing = report["cases"]
    assert report["version"] == 2
    assert result["outcome"] == outcome
    assert result["workflow"]["answer"] == draft["answer"]
    assert result["workflow"]["limitations"] == draft["limitations"]
    assert result["workflow"]["answerability"] == assessment
    assert missing["outcome"] == "no_context"
    assert missing["generation"]["attempts"] == 0


@pytest.mark.parametrize("continue_after_error", [False, True])
@pytest.mark.parametrize("provider", ["generic", "codex"])
def test_provider_failure_preserves_context_and_never_serializes_exception_secrets(
    experiment, tmp_path, continue_after_error, provider
):
    root, suite, config, registry, _ = experiment

    class FailingGenerator:
        def generate(self, *args):
            if provider == "codex":
                from repo_explorer.codex_model import CodexInvocationError

                raise CodexInvocationError(
                    "SECRET_PROVIDER_REQUEST_BODY", code="turn_failed", exit_code=1
                )
            raise TimeoutError("SECRET_PROVIDER_REQUEST_BODY")

    registry.factories["generators"]["chat"] = lambda *args: FailingGenerator()
    config.stop_on_error = not continue_after_error
    output = tmp_path / "failed"
    report = run_live_evaluation(suite, root, output, config, execute=True, registry=registry)
    assert report["execution"] == "error"
    failure, later = report["cases"]
    assert failure["error"]["type"] == (
        "CodexInvocationError" if provider == "codex" else "TimeoutError"
    )
    readable = (output / "report.md").read_text()
    assert "### Failure" in readable
    assert "stage: generation" in readable
    if provider == "codex":
        assert failure["error"]["code"] == "turn_failed"
        assert failure["error"]["exit_code"] == 1
        assert "code: turn_failed" in readable
        assert "exit_code: 1" in readable
    assert failure["generation"]["attempts"] == 1
    assert failure["retrieval"]["context_hits"]
    assert later["outcome"] == ("no_context" if continue_after_error else "not_run")
    assert "SECRET_PROVIDER_REQUEST_BODY" not in (output / "report.json").read_text()
    assert "SECRET_PROVIDER_REQUEST_BODY" not in readable


def test_index_failure_is_not_reported_as_empty_retrieval(experiment, tmp_path):
    root, suite, config, registry, _ = experiment

    def fail(*args):
        raise RuntimeError("SECRET_EMBEDDING_ERROR")

    registry.factories["embeddings"]["tfidf"] = fail
    report = run_live_evaluation(
        suite, root, tmp_path / "failed", config, execute=True, registry=registry
    )
    assert report["error"]["stage"] == "index"
    assert report["generation_attempts"] == 0
    assert all(case["outcome"] == "not_run" for case in report["cases"])
    assert "SECRET_EMBEDDING_ERROR" not in json.dumps(report)


def test_bad_snapshot_and_oversized_case_selection_fail_before_calls(experiment, tmp_path):
    root, suite, config, registry, chat = experiment
    config.max_cases = 1
    with pytest.raises(ValueError, match="max_cases"):
        run_live_evaluation(
            suite, root, tmp_path / "too-many", config, execute=True, registry=registry
        )
    config.case_ids = ["approve"]
    (root / "review.py").write_text("edited source")
    with pytest.raises(ValueError, match="hash mismatch"):
        run_live_evaluation(
            suite, root, tmp_path / "drift", config, execute=True, registry=registry
        )
    assert not chat.seen
    assert not (tmp_path / "too-many").exists()
    assert not (tmp_path / "drift").exists()


def test_expansion_report_contains_exact_context_received_by_chat(experiment, tmp_path):
    _, _, config, registry, chat = experiment
    suite = EvaluationSuite.model_validate_json((ROOT / "evaluations/context.json").read_text())
    config.workspace = config.workspace.model_copy(
        update={
            "chunk_size": 200,
            "chunk_overlap": 30,
            "retrieval_limit": 1,
            "lexical_tokenization": "code_identifiers",
            "context_expander": "line_window",
        }
    )
    result = run_live_evaluation(
        suite,
        ROOT / "examples/context-repository",
        tmp_path / "context",
        config,
        execute=True,
        registry=registry,
    )["cases"][0]
    assert result["retrieval"]["seed_evidence"]["missing_evidence"]
    assert not result["retrieval"]["context_evidence"]["missing_evidence"]
    assert "expand_context" in result["workflow"]["steps"]
    assert "pending.replace(destination)" in str(chat.seen[0])


def test_human_review_is_bound_to_report_and_source_ids(experiment, tmp_path):
    root, suite, config, registry, _ = experiment
    output = tmp_path / "run"
    run_live_evaluation(suite, root, output, config, execute=True, registry=registry)
    review_path, report_path = output / "review.json", output / "report.json"
    review = json.loads(review_path.read_text())
    review["cases"]["approve"].update(
        status="reviewed",
        reviewer="Test reviewer",
        answer_assessment="complete",
        claims=[
            {
                "claim": "Returns approval accepted",
                "verdict": "supported",
                "citation_ids": ["S1"],
                "explanation": "The return statement supplies this value.",
            }
        ],
    )
    review_path.write_text(json.dumps(review))
    assert validate_review(report_path, review_path).cases["approve"].status == "reviewed"
    review["cases"]["approve"]["claims"][0]["citation_ids"] = ["S99"]
    review_path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="context IDs"):
        validate_review(report_path, review_path)
    review["cases"]["approve"]["claims"][0]["citation_ids"] = ["S1"]
    review_path.write_text(json.dumps(review))
    report_path.write_text(report_path.read_text() + "\n")
    with pytest.raises(ValueError, match="exact report"):
        validate_review(report_path, review_path)


def test_evaluation_rejects_sources_outside_pinned_snapshot():
    with pytest.raises(ValidationError, match="pinned local corpus"):
        LiveEvaluationConfig(workspace=WorkspaceConfig(source_provider="uncontrolled-loader"))


def test_learned_embedding_adapter_receives_only_source_chunks_and_questions(experiment, tmp_path):
    root, suite, config, registry, _ = experiment
    seen = []

    class RecordingEmbeddings(Embeddings):
        def embed_documents(self, texts):
            seen.extend(texts)
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text):
            seen.append(text)
            return [1.0, 0.0]

    registry.register("embeddings", "fixture-vectors", lambda *args: RecordingEmbeddings())
    config.workspace = config.workspace.model_copy(
        update={
            "embedding_provider": "fixture-vectors",
            "embedding_model": "test-vectors",
        }
    )
    report = run_live_evaluation(
        suite, root, tmp_path / "vectors", config, execute=True, registry=registry
    )
    assert report["generation_attempts"] == 2  # Even the absent answer gets related context.
    assert suite.cases[0].question in seen
    assert "REFERENCE_WITHHELD_FROM_MODEL" not in "\n".join(seen)
    assert any("return 'approval accepted'" in text for text in seen)
    assert (
        report["cases"][1]["retrieval"]["context_evidence"]["returned_context_on_unanswerable"]
        is True
    )


def test_valid_citations_do_not_silently_grade_unsupported_claims(experiment, tmp_path):
    root, suite, config, registry, chat = experiment
    chat.responses = [
        AIMessage(
            content=json.dumps(
                {
                    "answer": "This service runs in an Antarctic cloud region [S1].",
                    "citation_ids": ["S1"],
                    "answerability": "complete",
                    "limitations": [],
                }
            )
        )
    ]
    output = tmp_path / "unsupported"
    report = run_live_evaluation(suite, root, output, config, execute=True, registry=registry)
    assert report["cases"][0]["outcome"] == "answered"
    review = validate_review(output / "report.json", output / "review.json")
    assert review.cases["approve"].status == "pending"
    assert review.cases["approve"].answer_assessment is None
