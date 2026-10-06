"""Validate human review records without pretending to judge semantic correctness."""

import argparse
import json
from pathlib import Path
from typing import Literal

from repo_explorer.evaluation.live_models import AnswerReview
from repo_explorer.evaluation.models import StrictModel
from repo_explorer.evaluation.snapshot import digest


class ReviewFile(StrictModel):
    report_sha256: str
    target: Literal["draft_if_available_else_final"]
    cases: dict[str, AnswerReview]


def validate_review(report_path: Path, review_path: Path) -> ReviewFile:
    content = report_path.read_bytes()
    report = json.loads(content)
    review = ReviewFile.model_validate_json(review_path.read_text(encoding="utf-8"))
    if review.report_sha256 != digest(content):
        raise ValueError("The review does not identify this exact report.")
    cases = {case["id"]: case for case in report["cases"]}
    if review.cases.keys() != cases.keys():
        raise ValueError("The review must identify every report case exactly once.")
    for case_id, judgment in review.cases.items():
        case = cases[case_id]
        if judgment.status != "reviewed":
            continue
        if case["outcome"] in {"not_run", "error"}:
            raise ValueError("Cases without a finished response must remain pending.")
        known = {hit["id"] for hit in case["retrieval"]["context_hits"]}
        for claim in judgment.claims:
            if set(claim.citation_ids) - known:
                raise ValueError("Review claims must reference the supplied context IDs.")
            if claim.verdict != "not_in_context" and not claim.citation_ids:
                raise ValueError("Supported/contradicted judgments need source IDs.")
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a source-support review record.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        review = validate_review(args.report, args.review)
    except (ValueError, OSError, KeyError, TypeError):
        parser.exit(
            2, "Invalid review: check report identity, case IDs, source IDs, and rubric fields.\n"
        )
    pending = any(case.status == "pending" for case in review.cases.values())
    print("Review structure valid. This does not verify the reviewer's factual judgments.")
    if pending:
        print("Some answer judgments are still pending.")
        if args.require_complete:
            parser.exit(1)


if __name__ == "__main__":
    main()
