"""Compare fixed lexical methods; reference answers never enter indexing."""

import json
import re
from bisect import bisect_right
from pathlib import Path
from time import perf_counter

from langchain_core.vectorstores import InMemoryVectorStore
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from repo_explorer.analysis import NoSourceAnalyzer
from repo_explorer.config import Settings, WorkspaceConfig
from repo_explorer.context import LineWindowExpander, NoContextExpander
from repo_explorer.evaluation.artifacts import (
    environment_metadata,
    implementation_fingerprint,
    prepare_snapshot,
)
from repo_explorer.evaluation.models import EvaluationCase, EvaluationSuite, RetrievalConfig
from repo_explorer.evaluation.snapshot import digest, snapshot_id
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import PluginRegistry, TfidfEmbeddings
from repo_explorer.sources import local_source


def keyword_search(index: KnowledgeIndex, question: str) -> list[dict]:
    def terms(text: str) -> set[str]:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        return (
            words - ENGLISH_STOP_WORDS if index.settings.lexical_stop_words == "english" else words
        )

    query = terms(question)
    ranked = []
    for doc in index.documents:
        score = len(query & terms(doc.page_content)) / max(len(query), 1)
        if score:
            ranked.append({**doc.metadata, "excerpt": doc.page_content, "score": round(score, 4)})
    # Stable source ordering breaks ties; the cosine threshold is not applicable here.
    ranked.sort(key=lambda item: (-item["score"], item["path"], item["start_line"]))
    return ranked[: index.settings.retrieval_limit]


def score_evidence(case: EvaluationCase, hits: list[dict], sources: dict[str, str]) -> dict:
    coverage = []
    for expected in case.evidence:
        source = sources[expected.path]
        offsets = [0]
        # Match ingestion's LF-based source coordinates, including Unicode separators in code.
        for line in re.findall(r"[^\n]*\n|[^\n]+$", source):
            offsets.append(offsets[-1] + len(line))
        covered = set()
        for hit in hits:
            if hit["path"] == expected.path:
                # The splitter may stop mid-line. Line-number overlap alone is insufficient.
                start = source.find(hit["excerpt"], offsets[hit["start_line"] - 1])
                if start >= 0 and start < offsets[hit["start_line"]]:
                    covered.update(range(start, start + len(hit["excerpt"])))
        needed = {
            position
            for position in range(offsets[expected.start_line - 1], offsets[expected.end_line])
            if not source[position].isspace()
        }
        missing_lines = sorted({bisect_right(offsets, position) for position in needed - covered})
        coverage.append(
            {
                "id": expected.id,
                "path": expected.path,
                "covered": needed <= covered,
                "missing_lines": missing_lines,
            }
        )
    return {
        "evidence": coverage,
        "evidence_coverage": sum(item["covered"] for item in coverage) / len(coverage)
        if coverage
        else None,
        "missing_evidence": [item["id"] for item in coverage if not item["covered"]],
        "retrieved_count": len(hits),
        "returned_context_on_unanswerable": bool(hits) if case.unanswerable else None,
    }


def markdown_report(report: dict) -> str:
    lines = [
        f"# {report['suite_name']}",
        "",
        report["scope"],
        "",
        f"Snapshot: `{report['snapshot_id']}`",
        "",
        "This is an offline retrieval report. Evidence coverage requires the non-whitespace "
        "source text in each annotated line range, "
        "not answer correctness. Reference notes were withheld from every retriever.",
        "",
        "No model responses, assistant comparison, token costs, or semantic judgments "
        "were evaluated. Unanswerable labels apply only to this selected corpus.",
        "",
        "The context-expansion method keeps the identifier retriever's seed ranking but "
        "has an additional character budget. Its similarity scores still describe the "
        "original matched passages. Compare evidence gains with the extra context size.",
        "",
    ]
    for case in report["cases"]:
        lines.extend([f"## {case['id']}", "", case["question"], ""])
        if case["distinct_evidence_files"] > report["config"]["retrieval_limit"]:
            lines.extend(
                [
                    "The retrieval limit is smaller than the number of required source files; "
                    "complete coverage is impossible with one passage per result.",
                    "",
                ]
            )
        for method, result in case["methods"].items():
            lines.extend([f"### {method}", ""])
            lines.extend([f"Context characters: {result['context_chars']}", ""])
            if trace := result.get("context_expansion"):
                lines.extend(
                    [
                        f"Expansion: {trace['added_chars']} added characters; "
                        f"stop reason `{trace['stop_reason']}`.",
                        "",
                    ]
                )
            if case["unanswerable"]:
                lines.append(
                    "Returned context despite missing answer evidence."
                    if result["retrieved_count"]
                    else "Returned no context."
                )
            else:
                lines.append(
                    "Missing evidence: " + (", ".join(result["missing_evidence"]) or "none")
                )
            lines.extend(["", "Retrieved passages:", ""])
            lines.extend(
                f"- `{hit['path']}:{hit['start_line']}-{hit['end_line']}` (score {hit['score']})"
                for hit in result["hits"]
            )
            lines.append("")
        lines.extend(
            ["Curated reference notes (withheld from retrieval):", "", case["reference_notes"], ""]
        )
    return "\n".join(lines)


def run_evaluation(
    suite: EvaluationSuite, repository: Path, output: Path, config: RetrievalConfig | None = None
) -> dict:
    config = config or RetrievalConfig()
    output = output.resolve()
    sources = prepare_snapshot(suite, repository, output)
    corpus = output / "corpus"
    (output / "config.json").write_text(config.model_dump_json(indent=2), encoding="utf-8")
    # Explicit defaults isolate evaluation from the running application's .env and plugins.
    settings = Settings(
        _env_file=None,
        **{
            **WorkspaceConfig().model_dump(),
            **config.model_dump(),
            "corpus_dir": corpus,
            "extensions": sorted({Path(path).suffix for path in sources}),
        },
    )
    registry = PluginRegistry()
    registry.register("sources", "local", local_source)
    registry.register("embeddings", "tfidf", TfidfEmbeddings)
    registry.register("expanders", "none", NoContextExpander)
    registry.register("expanders", "line_window", LineWindowExpander)
    registry.register("analyzers", "none", NoSourceAnalyzer)
    registry.register(
        "stores", "memory", lambda settings, embeddings: InMemoryVectorStore(embeddings)
    )
    indexes = {}
    index_seconds = {}
    for method, tokenization, expander in (
        ("tfidf", "standard", "none"),
        ("tfidf_identifiers", "code_identifiers", "none"),
        ("tfidf_identifiers_context", "code_identifiers", "line_window"),
    ):
        started = perf_counter()
        indexes[method] = KnowledgeIndex(
            Settings(
                **{
                    **settings.model_dump(),
                    "lexical_tokenization": tokenization,
                    "context_expander": expander,
                }
            ),
            registry,
        )
        index_seconds[method] = perf_counter() - started
    index = indexes["tfidf"]
    if {item["path"] for item in index.files} != set(sources):
        raise ValueError(
            "Some suite files were excluded by ingestion; narrow or correct the suite."
        )
    report = {
        "version": 3,
        "suite_name": suite.name,
        "scope": suite.scope,
        "snapshot_id": snapshot_id(sources),
        "git_revision": suite.snapshot.revision,
        "suite_sha256": digest(suite.model_dump_json().encode()),
        "implementation_sha256": implementation_fingerprint(),
        "config": config.model_dump(),
        "method_configs": {
            method: {
                **config.model_dump(),
                "lexical_tokenization": candidate.settings.lexical_tokenization,
                "context_expander": candidate.settings.context_expander,
            }
            for method, candidate in indexes.items()
        }
        | {
            "keyword_overlap": {
                **config.model_dump(
                    exclude={
                        "minimum_score",
                        "lexical_ngram_max",
                        "context_window_lines",
                        "context_max_added_chars",
                    }
                ),
                "positive_matches_only": True,
            }
        },
        "files": len(sources),
        "chunks": len(index.documents),
        "index_seconds": index_seconds,
        "model_calls": 0,
        "environment": environment_metadata(),
        "cases": [],
    }
    for case in suite.cases:
        result = {
            "id": case.id,
            "question": case.question,
            "unanswerable": case.unanswerable,
            "distinct_evidence_files": len({item.path for item in case.evidence}),
            "reference_notes": case.reference_notes,
            "methods": {},
        }
        for method, search in (
            ("tfidf", index.search),
            ("tfidf_identifiers", indexes["tfidf_identifiers"].search),
            ("tfidf_identifiers_context", indexes["tfidf_identifiers_context"].search),
            ("keyword_overlap", lambda q: keyword_search(index, q)),
        ):
            started = perf_counter()
            hits = search(case.question)
            trace = None
            if method == "tfidf_identifiers_context" and hits:
                expansion = indexes[method].expand_context(hits)
                hits, trace = expansion.sources, expansion.trace.model_dump()
            elapsed = perf_counter() - started
            result["methods"][method] = {
                **score_evidence(case, hits, sources),
                "search_seconds": elapsed,
                "hits": hits,
                "context_chars": sum(len(hit["excerpt"]) for hit in hits),
                "context_expansion": trace,
            }
        report["cases"].append(result)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report
