"""Explicit experiment settings and human judgments, separate from runtime prompts."""

from typing import Literal

from pydantic import Field, model_validator

from repo_explorer.config import WorkspaceConfig
from repo_explorer.evaluation.models import StrictModel


class LiveEvaluationConfig(StrictModel):
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    case_ids: list[str] = Field(default_factory=list)
    max_cases: int = Field(default=10, ge=1, le=100)
    stop_on_error: bool = True

    @model_validator(mode="after")
    def validate_experiment(self):
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("Case IDs must be unique.")
        if self.workspace.source_provider != "local" or self.workspace.vector_store != "memory":
            raise ValueError("Evaluation uses the pinned local corpus and an in-memory store.")
        if self.workspace.generator != "chat":
            raise ValueError("Live evaluation requires the chat generator.")
        if self.workspace.plugin_options:
            raise ValueError("The CLI uses built-in adapters; plugin options are not supported.")
        return self


class ClaimReview(StrictModel):
    claim: str = Field(min_length=1)
    verdict: Literal["supported", "contradicted", "not_in_context"]
    citation_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)


class AnswerReview(StrictModel):
    status: Literal["pending", "reviewed"] = "pending"
    reviewer: str | None = None
    answer_assessment: Literal["complete", "partial", "incorrect", "abstained"] | None = None
    abstention_appropriate: bool | None = None
    claims: list[ClaimReview] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def validate_review(self):
        if self.status == "reviewed":
            if not self.reviewer or not self.reviewer.strip() or self.answer_assessment is None:
                raise ValueError("A completed review needs a reviewer and answer assessment.")
            if self.answer_assessment == "abstained":
                if self.abstention_appropriate is None:
                    raise ValueError("Review whether the abstention was appropriate.")
            elif not self.claims:
                raise ValueError("Assess material claims against their supplied context.")
            if self.answer_assessment == "complete" and (
                self.missing_points or any(claim.verdict != "supported" for claim in self.claims)
            ):
                raise ValueError("A complete answer cannot have missing or unsupported claims.")
        return self
