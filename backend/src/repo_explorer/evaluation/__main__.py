"""Run with python -m repo_explorer.evaluation --help."""

import argparse
import json
from pathlib import Path

from repo_explorer.evaluation.models import EvaluationSuite, RetrievalConfig
from repo_explorer.evaluation.runner import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline, snapshot-pinned retrieval evaluation.")
    parser.add_argument("--suite", type=Path, required=True, help="Evaluation suite JSON")
    parser.add_argument(
        "--repository", type=Path, required=True, help="Source checkout or fixture directory"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New local artifact directory; must not exist"
    )
    parser.add_argument("--config", type=Path, help="Optional retrieval settings JSON")
    args = parser.parse_args()
    try:
        suite = EvaluationSuite.model_validate_json(args.suite.read_text(encoding="utf-8"))
        config = (
            RetrievalConfig.model_validate(json.loads(args.config.read_text()))
            if args.config
            else None
        )
        report = run_evaluation(suite, args.repository, args.output, config)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Evaluation could not run: {exc}\n")
    print(f"Report: {args.output.resolve() / 'report.md'}")
    print(f"Snapshot: {report['snapshot_id']}; model calls: 0")


if __name__ == "__main__":
    main()
