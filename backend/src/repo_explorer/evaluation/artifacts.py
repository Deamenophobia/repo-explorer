"""Shared, local experiment artifacts; never overwrite an earlier run."""

import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from repo_explorer.evaluation.models import EvaluationSuite
from repo_explorer.evaluation.snapshot import digest, read_snapshot


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare_snapshot(suite: EvaluationSuite, repository: Path, output: Path) -> dict[str, str]:
    sources = read_snapshot(suite, repository)
    output.mkdir(parents=True, exist_ok=False)
    for name, text in sources.items():
        path = output / "corpus" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    write_json(output / "suite.json", suite.model_dump())
    replay = suite.model_dump()
    replay["snapshot"].update(kind="files", revision=None)
    write_json(output / "replay-suite.json", replay)
    return sources


def implementation_fingerprint() -> str:
    root = Path(__file__).parents[1]
    manifest = {
        path.relative_to(root).as_posix(): digest(path.read_text(encoding="utf-8").encode())
        for path in sorted(root.rglob("*.py"))
    }
    return digest(json.dumps(manifest, sort_keys=True).encode())


def environment_metadata() -> dict:
    result = {"python": platform.python_version()}
    for name in (
        "repo-explorer",
        "langgraph",
        "langchain-core",
        "langsmith",
        "langchain-text-splitters",
        "scikit-learn",
        "langchain-openai",
        "langchain-anthropic",
        "langchain-ollama",
        "fastembed",
        "onnxruntime",
        "tokenizers",
    ):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            continue
    return result
