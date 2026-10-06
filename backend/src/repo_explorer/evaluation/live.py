"""Evaluate the production graph with explicit providers and inspectable local artifacts."""

import argparse
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langsmith import tracing_context

from repo_explorer.config import Settings
from repo_explorer.evaluation.artifacts import (
    environment_metadata,
    implementation_fingerprint,
    prepare_snapshot,
    write_json,
)
from repo_explorer.evaluation.live_models import AnswerReview, LiveEvaluationConfig
from repo_explorer.evaluation.models import EvaluationSuite
from repo_explorer.evaluation.runner import score_evidence
from repo_explorer.evaluation.snapshot import digest, snapshot_id
from repo_explorer.generation import AnswerGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import PluginRegistry, builtin_registry
from repo_explorer.schemas import RunRequest
from repo_explorer.sources import local_source
from repo_explorer.workflow import build_workflow


class ObservedGenerator:
    """Observe the existing generation contract without changing its prompt or result."""

    def __init__(self, delegate: AnswerGenerator):
        self.delegate = delegate
        self.attempts = 0
        self.seconds = 0.0
        self.draft: dict | None = None

    def generate(self, question: str, intent: str, sources: list[dict], policy: str) -> dict:
        self.attempts += 1
        started = perf_counter()
        try:
            self.draft = deepcopy(self.delegate.generate(question, intent, sources, policy))
            return self.draft
        finally:
            self.seconds += perf_counter() - started


def preflight_issues(settings: Settings, registry: PluginRegistry) -> list[str]:
    issues = []
    if settings.mode != "live" or not settings.model.strip():
        issues.append("Choose live mode and a supported chat model in the experiment config.")
    if settings.chat_provider == "codex":
        from repo_explorer.codex_model import resolve_codex_executable

        try:
            resolve_codex_executable(settings.codex_executable)
        except ValueError:
            issues.append("Configure a native Codex CLI executable on the server.")
    for kind, name in (
        ("chat", settings.chat_provider),
        ("embeddings", settings.embedding_provider),
        ("expanders", settings.context_expander),
        ("analyzers", settings.source_analyzer),
    ):
        if name not in registry.factories[kind]:
            issues.append(f"Unknown {kind} adapter in the experiment config.")
    for role, provider, variable in (
        ("chat", settings.chat_provider, settings.chat_api_key_env),
        ("embedding", settings.embedding_provider, settings.embedding_api_key_env),
    ):
        required = variable or {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(
            provider, ""
        )
        if required and not settings.credential(required):
            issues.append(f"Missing {role} credential; set its configured environment variable.")
    return issues


def safe_error(stage: str, error: Exception) -> dict:
    # Provider exception text can contain request bodies, credentials, or service HTML.
    from repo_explorer.codex_model import CodexInvocationError

    result = {"stage": stage, "type": type(error).__name__, "details": "Exception text omitted."}
    if isinstance(error, CodexInvocationError):
        result["code"] = error.code
        if error.exit_code is not None:
            result["exit_code"] = error.exit_code
    return result


def evaluate_case(case, index, generator, sources: dict[str, str]) -> dict:
    observed = ObservedGenerator(generator)
    usage = UsageMetadataCallbackHandler()
    graph = build_workflow(index, observed, checkpointer=None)
    state = {"question": RunRequest(question=case.question).question, "intent": "question"}
    stages, seeds, error = [], [], None
    started = perf_counter()
    stage_started = started
    try:
        for event in graph.stream(state, config={"callbacks": [usage]}, stream_mode="updates"):
            for node, update in event.items():
                now = perf_counter()
                stages.append({"node": node, "seconds": now - stage_started})
                stage_started = now
                state.update(update)
                if node == "retrieve":
                    seeds = deepcopy(update["sources"])
    except Exception as exc:
        # Stop/continue is decided by the caller; preserve the context even on compose failure.
        stage = (
            "generation" if observed.attempts else ("context_expansion" if stages else "retrieval")
        )
        error = safe_error(stage, exc)
    context = state.get("sources", [])
    if error:
        outcome = "error"
    elif "abstain" in state.get("steps", []):
        outcome = "no_context"
    elif state.get("status") == "invalid_citations":
        outcome = "invalid_citations"
    elif state.get("answerability") == "insufficient_evidence":
        outcome = "model_abstention"
    elif state.get("answerability") == "partial":
        outcome = "partial"
    elif state.get("answerability") == "not_assessed":
        outcome = "not_assessed"
    else:
        outcome = "answered"
    return {
        "id": case.id,
        "question": state["question"],
        "outcome": outcome,
        "unanswerable": case.unanswerable,
        "reference_notes": case.reference_notes,
        "expected_evidence": [item.model_dump() for item in case.evidence],
        "seconds": perf_counter() - started,
        "stages": stages,
        "error": error,
        "retrieval": {
            "seed_hits": seeds,
            "context_hits": context,
            "seed_evidence": score_evidence(case, seeds, sources),
            "context_evidence": score_evidence(case, context, sources),
            "context_chars": sum(len(hit["excerpt"]) for hit in context),
            "context_expansion": state.get("context_expansion"),
        },
        "generation": {
            "attempts": observed.attempts,
            "seconds": observed.seconds,
            "draft": observed.draft,
            "reported_chat_usage": usage.usage_metadata or None,
            "cost_usd": None,
        },
        "workflow": {
            key: state.get(key)
            for key in (
                "status",
                "answer",
                "answerability",
                "limitations",
                "citation_ids",
                "steps",
                "evidence_map",
            )
        },
    }


def fenced_text(value: str) -> str:
    """Keep source/model data literal even when it contains Markdown or HTML."""
    longest = max((len(match) for match in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def markdown_report(report: dict) -> str:
    lines = [
        f"# {report['suite_name']} — pipeline evaluation",
        "",
        report["scope"],
        "",
        f"Execution: `{report['execution']}`. Snapshot: `{report['snapshot_id']}`.",
        "",
        "Citation validation is structural. Answers remain ungraded until a reviewer checks "
        "material claims against the exact supplied passages and the withheld reference.",
        "",
        "Token usage is provider-reported when available; missing usage and monetary cost "
        "are unknown, not zero. Embedding usage and costs are not measured.",
        "",
    ]
    if report.get("error"):
        lines.extend([f"Preparation failed at `{report['error']['stage']}`; see report.json.", ""])
    for case in report["cases"]:
        lines.extend([f"## {case['id']}", "", f"Outcome: `{case['outcome']}`.", ""])
        if case["outcome"] == "not_run":
            continue
        if failure := case.get("error"):
            lines.extend(
                [
                    "### Failure",
                    "",
                    fenced_text(
                        "\n".join(
                            f"{key}: {failure[key]}"
                            for key in ("stage", "type", "code", "exit_code")
                            if key in failure
                        )
                    ),
                    "",
                ]
            )
        lines.extend(
            [
                fenced_text(case["question"]),
                "",
                f"Context characters: {case['retrieval']['context_chars']}.",
                "",
                "Missing annotated evidence: "
                + (", ".join(case["retrieval"]["context_evidence"]["missing_evidence"]) or "none")
                + (" (no gold spans for this unanswerable case)." if case["unanswerable"] else "."),
                "",
                "### Draft before citation validation",
                "",
                fenced_text((case["generation"]["draft"] or {}).get("answer", "No parsed draft.")),
                "",
                "### Final workflow answer",
                "",
                fenced_text(case["workflow"]["answer"] or "No final answer."),
                "",
                "Answerability: " + str(case["workflow"].get("answerability", "not_assessed")),
                "",
                "### Missing information reported by the workflow",
                "",
                fenced_text(
                    "\n".join(case["workflow"].get("limitations") or []) or "None reported."
                ),
                "",
                "### Supplied context",
                "",
            ]
        )
        for hit in case["retrieval"]["context_hits"]:
            lines.extend(
                [
                    fenced_text(
                        f"[{hit['id']}] {hit['path']}:{hit['start_line']}-{hit['end_line']}\n"
                        f"revision={hit['revision']} score={hit['score']}\n\n{hit['excerpt']}"
                    ),
                    "",
                ]
            )
        evidence_map = case["workflow"].get("evidence_map")
        if evidence_map is not None:
            lines.extend(
                [
                    "### Saved evidence map",
                    "",
                    "The map in report.json covers cited passages. Containment comes from saved "
                    "source analysis; inspect each node's passage coverage and the map's issues.",
                    "",
                    fenced_text(
                        "\n".join(
                            f"{node['kind']}: {node['label']} "
                            f"({node['path']}, revision {node['revision']})"
                            for node in evidence_map["nodes"]
                        )
                    ),
                    "",
                ]
            )
        lines.extend(
            [
                "### Reference notes (withheld from the pipeline)",
                "",
                fenced_text(case["reference_notes"]),
                "",
                "Fill review.json using the source-support rubric "
                "before drawing quality conclusions.",
                "",
            ]
        )
    return "\n".join(lines)


def save_report(output: Path, report: dict) -> None:
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")


def run_live_evaluation(
    suite: EvaluationSuite,
    repository: Path,
    output: Path,
    config: LiveEvaluationConfig,
    *,
    execute: bool = False,
    registry: PluginRegistry | None = None,
) -> dict:
    selected = config.case_ids or [case.id for case in suite.cases]
    by_id = {case.id: case for case in suite.cases}
    if set(selected) - by_id.keys() or len(selected) > config.max_cases:
        raise ValueError(
            "Select known case IDs within max_cases; cases are never silently dropped."
        )
    cases = [by_id[case_id] for case_id in selected]
    for case in cases:
        RunRequest(question=case.question)
    output = output.resolve()
    sources = prepare_snapshot(suite, repository, output)
    write_json(output / "config.json", config.model_dump(mode="json"))
    settings = Settings(
        _env_file=None,
        **{
            **config.workspace.model_dump(),
            "corpus_dir": output / "corpus",
            "extensions": sorted({Path(name).suffix for name in sources}),
            "data_dir": output / "runtime",
            "config_file": output / "unused-settings.json",
            "cors_origins": [],
        },
    )
    registry = registry or builtin_registry()
    corpus = local_source(settings)
    if not corpus.documents or {file["path"] for file in corpus.files} != set(sources):
        raise ValueError("Some snapshot files were excluded by ingestion; correct the config.")
    write_json(output / "effective-workspace.json", settings.public().model_dump(mode="json"))
    (output / "policy.txt").write_text(corpus.policy, encoding="utf-8")
    issues = preflight_issues(settings, registry)
    plan = {
        "kind": "live_evaluation_preflight",
        "snapshot_id": snapshot_id(sources),
        "suite_name": suite.name,
        "case_ids": selected,
        "issues": issues,
        "configuration_ready": not issues,
        "provider_connectivity_checked": False,
        "files": len(sources),
        "chunks": len(corpus.documents),
        "max_generation_attempts": len(cases),
        "provider_retries": settings.max_retries,
        "chat": {
            "provider": settings.chat_provider,
            "model": settings.model,
            "endpoint": settings.base_url,
            "input": "question, retrieved context, policy",
        },
        "embeddings": {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "endpoint": settings.embedding_base_url,
            "input": "indexed chunks and questions"
            if settings.embedding_provider != "tfidf"
            else "local computation only",
        },
        "policy_chars": len(corpus.policy),
        "indexed_chars": sum(len(doc.page_content) for doc in corpus.documents),
    }
    write_json(output / "preflight.json", plan)
    if not execute:
        return plan
    if issues:
        raise ValueError("Preflight has configuration issues; inspect preflight.json.")
    report = {
        "version": 2,
        "kind": "live_pipeline_evaluation",
        "execution": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite.name,
        "scope": suite.scope,
        "snapshot_id": snapshot_id(sources),
        "git_revision": suite.snapshot.revision,
        "suite_sha256": digest(suite.model_dump_json().encode()),
        "implementation_sha256": implementation_fingerprint(),
        "environment": environment_metadata(),
        "config": config.model_dump(mode="json"),
        "policy_sha256": digest(corpus.policy.encode()),
        "index_seconds": None,
        "generation_attempts": 0,
        "error": None,
        "cases": [{"id": case.id, "outcome": "not_run"} for case in cases],
    }
    save_report(output, report)
    stage = "chat_adapter"
    # Run locally observable callbacks only, even if this shell has LangSmith tracing enabled.
    with tracing_context(enabled=False):
        try:
            generator = registry.build("generators", "chat", settings, registry)
            report["provider_runtime"] = getattr(generator, "runtime_metadata", {})
            stage = "index"
            started = perf_counter()
            index = KnowledgeIndex(settings, registry)
            report["index_seconds"] = perf_counter() - started
        except Exception as exc:
            report.update(execution="error", error=safe_error(stage, exc))
        else:
            for position, case in enumerate(cases):
                result = evaluate_case(case, index, generator, sources)
                report["cases"][position] = result
                report["generation_attempts"] += result["generation"]["attempts"]
                save_report(output, report)
                if result["error"] and config.stop_on_error:
                    break
            report["execution"] = (
                "completed"
                if all(case["outcome"] not in {"error", "not_run"} for case in report["cases"])
                else "error"
            )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_report(output, report)
    write_json(
        output / "review.json",
        {
            "report_sha256": digest((output / "report.json").read_bytes()),
            "target": "draft_if_available_else_final",
            "cases": {case.id: AnswerReview().model_dump() for case in cases},
        },
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight or execute a snapshot-pinned AI pipeline."
    )
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New local artifact directory")
    parser.add_argument("--config", type=Path, required=True, help="Explicit experiment JSON")
    parser.add_argument("--execute", action="store_true", help="Enable configured provider calls")
    args = parser.parse_args()
    try:
        suite = EvaluationSuite.model_validate_json(args.suite.read_text(encoding="utf-8"))
        config = LiveEvaluationConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        report = run_live_evaluation(
            suite, args.repository, args.output, config, execute=args.execute
        )
    except (ValueError, OSError):
        parser.exit(
            2,
            "Evaluation could not run. Check suite/config, source hashes, credentials, "
            "and a new output path; inspect preflight.json if created.\n",
        )
    artifact = "report.json" if args.execute else "preflight.json"
    print(f"Artifact: {args.output.resolve() / artifact}")
    if args.execute:
        print(f"Execution: {report['execution']}; answer quality requires review.")
        if report["execution"] != "completed":
            parser.exit(1)
    else:
        print("Preflight only: no provider calls. Connectivity has not been checked.")
        for issue in report["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
