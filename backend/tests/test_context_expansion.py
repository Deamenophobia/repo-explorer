from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from repo_explorer.analysis import PythonSourceAnalyzer
from repo_explorer.api import create_app
from repo_explorer.config import Settings
from repo_explorer.context import ExpansionResult, LineWindowExpander
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import default_registry
from repo_explorer.sources import CorpusSnapshot

CORPUS = Path(__file__).resolve().parents[2] / "examples" / "context-repository"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        corpus_dir=CORPUS,
        data_dir=tmp_path / "data",
        config_file=tmp_path / "settings.json",
        mode="demo",
        embedding_provider="tfidf",
        lexical_tokenization="code_identifiers",
        chunk_size=200,
        chunk_overlap=30,
        retrieval_limit=1,
        context_expander="line_window",
    )


def test_expansion_recovers_function_tail_without_reranking_or_changing_snapshot(settings):
    index = KnowledgeIndex(settings)
    hits = index.search("publish_record")
    assert len(hits) == 1
    assert "pending.replace(destination)" not in hits[0]["excerpt"]
    original = dict(hits[0])
    result = index.expand_context(hits)
    assert hits[0] == original
    assert "pending.replace(destination)" in result.sources[0]["excerpt"]
    for key in ("id", "path", "revision", "score"):
        assert result.sources[0][key] == original[key]
    trace = result.trace
    assert trace.added_chars == len(result.sources[0]["excerpt"]) - len(original["excerpt"])
    assert 0 < trace.added_chars <= settings.context_max_added_chars
    assert trace.changes[0].status == "expanded"
    assert trace.changes[0].original_start_line == original["start_line"]
    lines = (CORPUS / original["path"]).read_text().splitlines()
    expanded = result.sources[0]
    assert expanded["excerpt"] == "\n".join(
        lines[expanded["start_line"] - 1 : expanded["end_line"]]
    )


def test_tight_budget_keeps_seed_whole(settings):
    configured = Settings(**{**settings.model_dump(), "context_max_added_chars": 1})
    index = KnowledgeIndex(configured)
    hits = index.search("publish_record")
    result = index.expand_context(hits)
    assert result.sources == hits
    assert result.trace.added_chars == 0
    assert result.trace.stop_reason == "budget_limited"


def test_line_ranges_follow_newlines_even_with_unicode_separators(settings):
    text = "before\nvalue = 'one\u2028two'\nafter\n"
    corpus = CorpusSnapshot(
        [], [{"path": "unicode.py", "revision": "v1"}], "", {"unicode.py": text}
    )
    seed = dict(
        id="S1",
        path="unicode.py",
        revision="v1",
        score=0.5,
        start_line=2,
        end_line=2,
        excerpt="value = 'one\u2028two'",
    )
    result = LineWindowExpander(settings, corpus).expand([seed])
    assert result.sources[0]["start_line"] == 1
    assert result.sources[0]["end_line"] == 3
    assert result.sources[0]["excerpt"] == text.rstrip("\n")


@pytest.mark.parametrize("tail", ["\n\n", "\n\n\ndef elsewhere():\n    pass\n"])
def test_window_ending_in_blank_lines_preserves_definition_analysis(settings, tail):
    text = "class Response:\n    def ready(self):\n        return True\n" + tail
    corpus = CorpusSnapshot(
        [], [{"path": "response.py", "revision": "v1"}], "", {"response.py": text}
    )
    configured = Settings(**{**settings.model_dump(), "context_window_lines": 2})
    seed = dict(
        id="S1",
        path="response.py",
        revision="v1",
        score=0.5,
        start_line=3,
        end_line=3,
        excerpt="return True",
    )
    result = LineWindowExpander(configured, corpus).expand([seed])
    expanded = result.sources[0]
    assert expanded["start_line"] == 1
    assert expanded["end_line"] == result.trace.changes[0].end_line == 3
    assert expanded["excerpt"] == text[: text.index("True") + len("True")]
    analysis = PythonSourceAnalyzer(configured, corpus).analyze(expanded)
    assert analysis.status == "analyzed"
    assert [(symbol.qualified_name, symbol.coverage) for symbol in analysis.symbols] == [
        ("Response", "full"),
        ("Response.ready", "full"),
    ]


def test_budget_is_shared_across_sources_and_later_windows_can_still_fit(settings):
    texts = {
        "large.py": "a long surrounding line\ntarget\nanother long line\n",
        "one.py": "before\ntarget\nafter\n",
        "two.py": "prefix\ntarget\nsuffix\n",
    }
    corpus = CorpusSnapshot([], [{"path": path, "revision": "v1"} for path in texts], "", texts)
    sources = [
        dict(
            id=f"S{i}",
            path=path,
            revision="v1",
            score=0.5,
            start_line=2,
            end_line=2,
            excerpt="target",
        )
        for i, path in enumerate(texts, start=1)
    ]
    configured = Settings(**{**settings.model_dump(), "context_max_added_chars": 13})
    result = LineWindowExpander(configured, corpus).expand(sources)
    assert result.trace.added_chars == 13
    assert [change.status for change in result.trace.changes] == [
        "budget_limited",
        "expanded",
        "budget_limited",
    ]
    assert result.sources[0] == sources[0]
    assert result.sources[2] == sources[2]


def test_expansion_reads_indexed_text_after_disk_changes(settings, tmp_path):
    corpus = tmp_path / "source"
    corpus.mkdir()
    source = (CORPUS / "publish_record.py").read_text()
    (corpus / "publish_record.py").write_text(source)
    configured = Settings(**{**settings.model_dump(), "corpus_dir": corpus})
    index = KnowledgeIndex(configured)
    hits = index.search("publish_record")
    (corpus / "publish_record.py").write_text("different revision after indexing")
    result = index.expand_context(hits)
    assert "pending.replace(destination)" in result.sources[0]["excerpt"]
    assert "different revision" not in result.sources[0]["excerpt"]


def test_source_adapter_without_full_text_or_consistent_provenance_is_explicit(settings):
    index = KnowledgeIndex(settings)
    hits = index.search("publish_record")
    unavailable = LineWindowExpander(settings, CorpusSnapshot([], index.files, "")).expand(hits)
    assert unavailable.sources == hits
    assert unavailable.trace.changes[0].status == "source_unavailable"
    mismatched = index.expand_context([{**hits[0], "excerpt": "not in the indexed source"}])
    assert mismatched.trace.changes[0].status == "source_mismatch"
    other_revision = index.expand_context([{**hits[0], "revision": "different"}])
    assert other_revision.trace.changes[0].status == "source_unavailable"


def test_graph_expands_once_and_review_preserves_context_across_reconfigure_and_restart(settings):
    with TestClient(create_app(settings)) as client:
        run = client.post(
            "/api/runs", json={"question": "publish_record", "intent": "review"}
        ).json()
        assert run["status"] == "awaiting_review"
        assert run["steps"] == ["retrieve", "expand_context", "compose", "validate"]
        assert "pending.replace(destination)" in run["citations"][0]["excerpt"]
        assert run["context_expansion"]["added_chars"] > 0
        values = client.get("/api/settings").json()["values"]
        assert (
            client.put("/api/settings", json={**values, "context_expander": "none"}).status_code
            == 200
        )
        plain = client.post("/api/runs", json={"question": "publish_record"}).json()
        assert plain["context_expansion"] is None
        assert "expand_context" not in plain["steps"]
    disabled = Settings(**{**settings.model_dump(), "context_expander": "none"})
    with TestClient(create_app(disabled)) as client:
        saved = client.get(f"/api/runs/{run['id']}").json()
        assert saved == run
        approved = client.post(f"/api/runs/{run['id']}/decision", json={"approved": True}).json()
        assert approved["status"] == "approved"
        assert approved["context_expansion"] == run["context_expansion"]
        assert approved["citations"] == run["citations"]
        assert approved["steps"].count("expand_context") == 1


def test_custom_expander_is_pluggable_and_not_called_without_seed_evidence(settings):
    calls = []

    class ObservedExpander(LineWindowExpander):
        def expand(self, sources: list[dict]) -> ExpansionResult:
            calls.append(len(sources))
            return super().expand(sources)

    registry = default_registry()
    registry.register("expanders", "observed", ObservedExpander)
    configured = Settings(**{**settings.model_dump(), "context_expander": "observed"})
    with TestClient(create_app(configured, registry)) as client:
        absent = client.post("/api/runs", json={"question": "zyzzyva quokka nebula"}).json()
        assert absent["steps"] == ["retrieve", "abstain"]
        assert calls == []
        assert client.post("/api/runs", json={"question": "publish_record"}).status_code == 200
        assert calls == [1]
