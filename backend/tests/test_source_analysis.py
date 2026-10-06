import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda
from repo_explorer.analysis import PythonSourceAnalyzer
from repo_explorer.api import create_app
from repo_explorer.config import Settings
from repo_explorer.generation import ChatAnswerGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import builtin_registry
from repo_explorer.schemas import DraftAnswer, SourceAnalysis
from repo_explorer.sources import CorpusSnapshot

CORPUS = Path(__file__).resolve().parents[2] / "examples/symbol-repository"


def analyzer_for(text, path="sample.py", limit=8):
    revision = hashlib.sha256(text.encode()).hexdigest()[:12]
    corpus = CorpusSnapshot([], [{"path": path, "revision": revision}], "", {path: text})
    analyzer = PythonSourceAnalyzer(Settings(_env_file=None, source_symbol_limit=limit), corpus)
    return analyzer, revision


def passage(text, excerpt, revision, path="sample.py"):
    start = text.index(excerpt)
    line = text[:start].count("\n") + 1
    return {
        "path": path,
        "revision": revision,
        "start_line": line,
        "end_line": line + excerpt.count("\n"),
        "excerpt": excerpt,
    }


def test_same_named_methods_are_qualified_without_assigning_one_owner_to_whole_passage():
    text = (
        "class First:\n    def expire(self):\n        return 1\n\n"
        "class Second:\n    def expire(self):\n        return 2\n"
    )
    analyzer, revision = analyzer_for(text)
    result = analyzer.analyze(passage(text, "return 1", revision))
    assert [s.qualified_name for s in result.symbols] == ["First", "First.expire"]
    assert all(s.coverage == "partial" for s in result.symbols)
    both = analyzer.analyze(passage(text, text, revision))
    assert [s.qualified_name for s in both.symbols] == [
        "First",
        "First.expire",
        "Second",
        "Second.expire",
    ]
    assert all(s.coverage == "full" for s in both.symbols)
    assert result.symbols[1].id == both.symbols[1].id
    changed, other_revision = analyzer_for(text + "# next revision\n")
    assert (
        changed.analyze(passage(text, "return 1", other_revision)).symbols[1].id
        != result.symbols[1].id
    )


def test_utf8_columns_and_decorators_do_not_overstate_full_definition_coverage():
    text = "@decorator\nasync def café(): return 'é'\n"
    analyzer, revision = analyzer_for(text)
    body = analyzer.analyze(passage(text, "async def café(): return 'é'", revision))
    assert body.symbols[0].coverage == "partial"
    assert body.symbols[0].is_async is True
    assert body.symbols[0].start_line == 1
    assert analyzer.analyze(passage(text, text, revision)).symbols[0].coverage == "full"
    fragment = analyzer.analyze(passage(text, "return 'é'", revision))
    assert fragment.symbols[0].coverage == "partial"


def test_nested_definitions_and_limits_are_explicit():
    text = (
        "class Outer:\n    def method(self):\n        def inner():\n"
        "            return 1\n        return inner()\n"
    )
    analyzer, revision = analyzer_for(text)
    symbols = analyzer.analyze(passage(text, "return 1", revision)).symbols
    assert [(s.qualified_name, s.kind) for s in symbols] == [
        ("Outer", "class"),
        ("Outer.method", "method"),
        ("Outer.method.inner", "function"),
    ]
    limited, _ = analyzer_for(text, limit=2)
    result = limited.analyze(passage(text, "return 1", revision))
    assert len(result.symbols) == 2
    assert result.omitted_symbols == 1


def test_analysis_reports_absent_unsupported_invalid_and_mismatched_sources():
    text = "def broken(:\n    pass\n"
    analyzer, revision = analyzer_for(text)
    source = passage(text, "pass", revision)
    assert analyzer.analyze(source).status == "parse_error"
    assert analyzer.analyze({**source, "path": "client.ts"}).status == "unsupported_language"
    assert analyzer.analyze({**source, "revision": "stale"}).status == "source_unavailable"
    assert analyzer.analyze({**source, "excerpt": "invented"}).status == "source_mismatch"
    assert analyzer.analyze({**source, "start_line": 1}).status == "source_mismatch"
    unavailable = PythonSourceAnalyzer(Settings(), CorpusSnapshot([], [], ""))
    assert unavailable.analyze(source).status == "source_unavailable"
    repeated = "def f(): return 'same', 'same'\n"
    analyzer, revision = analyzer_for(repeated)
    assert analyzer.analyze(passage(repeated, "'same'", revision)).status == "source_mismatch"


def test_parser_does_not_execute_module_and_distinguishes_module_level_text(tmp_path):
    target = tmp_path / "must-not-exist"
    text = f"open({str(target)!r}, 'w').write('executed')\n\ndef example():\n    return 1\n"
    analyzer, revision = analyzer_for(text)
    result = analyzer.analyze(passage(text, text.split("\n")[0], revision))
    assert result.status == "analyzed" and result.symbols == []
    assert not target.exists()


def settings_for(tmp_path, **overrides):
    return Settings(
        _env_file=None,
        **{
            "corpus_dir": CORPUS,
            "data_dir": tmp_path / "runtime",
            "config_file": tmp_path / "settings.json",
            "source_analyzer": "python_ast",
            "chunk_size": 200,
            "chunk_overlap": 30,
            "retrieval_limit": 1,
            "lexical_tokenization": "code_identifiers",
            **overrides,
        },
    )


def test_annotations_leave_ranked_text_unchanged_and_follow_expanded_snapshot(tmp_path):
    configured = settings_for(tmp_path, context_expander="line_window", context_window_lines=8)
    annotated = KnowledgeIndex(configured)
    plain = KnowledgeIndex(settings_for(tmp_path, source_analyzer="none"))
    hit = annotated.search("deadline has arrived")[0]
    assert {**hit, "source_analysis": None} == plain.search("deadline has arrived")[0]
    assert "class DeadlineCache" not in hit["excerpt"]
    assert hit["source_analysis"]["symbols"][1]["qualified_name"] == "DeadlineCache.expire"
    assert hit["source_analysis"]["symbols"][1]["coverage"] == "partial"
    result = annotated.expand_context([hit])
    method = next(
        s
        for s in result.sources[0]["source_analysis"]["symbols"]
        if s["qualified_name"] == "DeadlineCache.expire"
    )
    assert method["coverage"] == "full"
    assert method["id"] == hit["source_analysis"]["symbols"][1]["id"]
    assert hit["source_analysis"]["symbols"][1]["coverage"] == "partial"


def test_review_retains_metadata_after_reconfiguration_disk_change_and_restart(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    file = source / "caches.py"
    file.write_text((CORPUS / "caches.py").read_text())
    settings = settings_for(tmp_path, corpus_dir=source)
    with TestClient(create_app(settings)) as client:
        run = client.post(
            "/api/runs", json={"question": "deadline has arrived", "intent": "review"}
        ).json()
        assert run["citations"][0]["source_analysis"]["status"] == "analyzed"
        assert [node["label"] for node in run["evidence_map"]["nodes"]] == [
            "caches.py",
            "DeadlineCache",
            "DeadlineCache.expire",
        ]
        file.write_text("class Changed:\n    pass\n")
        values = client.get("/api/settings").json()["values"]
        assert (
            client.put(
                "/api/settings",
                json={**values, "source_analyzer": "none", "evidence_map_node_limit": 2},
            ).status_code
            == 200
        )
    with TestClient(
        create_app(settings_for(tmp_path, corpus_dir=source, source_analyzer="none"))
    ) as client:
        assert client.get(f"/api/runs/{run['id']}").json() == run
        approved = client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).json()
        assert approved["citations"] == run["citations"]
        assert approved["evidence_map"] == run["evidence_map"]


def test_analyzer_can_be_registered_and_its_result_reaches_generation(tmp_path):
    calls = []

    class Analyzer:
        def __init__(self, settings, corpus):
            assert corpus.texts

        def analyze(self, source):
            calls.append(source["path"])
            return SourceAnalysis(method="custom", status="analyzed")

    registry = builtin_registry()
    registry.register("analyzers", "custom", Analyzer)
    index = KnowledgeIndex(settings_for(tmp_path, source_analyzer="custom"), registry)
    sources = index.search("deadline has arrived")
    prompts = []

    class Model:
        def with_structured_output(self, schema):
            def respond(prompt):
                prompts.append(prompt.to_string())
                return DraftAnswer(
                    answer="Visible example [S1].",
                    citation_ids=["S1"],
                    answerability="complete",
                    limitations=[],
                )

            return RunnableLambda(respond)

    generator = ChatAnswerGenerator(Settings(mode="live", model="fixture"), Model())
    generator.generate("question", "question", sources, "")
    assert calls == ["caches.py"]
    assert '"source_analysis": {"method": "custom"' in prompts[0]
