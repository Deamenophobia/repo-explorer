"""Shared boundary types use snake_case fields and PascalCase model names."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ModelAnswerability = Literal["complete", "partial", "insufficient_evidence"]
Answerability = ModelAnswerability | Literal["not_assessed"]


class RunRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    intent: Literal["question", "review"] = "question"

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Enter a question with at least three characters.")
        return value.strip()


class ReviewDecision(BaseModel):
    approved: bool


class SourceSymbol(BaseModel):
    id: str
    qualified_name: str
    kind: Literal["class", "function", "method"]
    is_async: bool = False
    start_line: int
    end_line: int
    coverage: Literal["full", "partial"]


class SourceRelationship(BaseModel):
    kind: Literal["contains"] = "contains"
    parent_id: str | None = None
    child_id: str


class SourceAnalysis(BaseModel):
    method: str
    status: Literal[
        "analyzed", "unsupported_language", "parse_error", "source_unavailable", "source_mismatch"
    ]
    parser_version: str | None = None
    symbols: list[SourceSymbol] = Field(default_factory=list)
    omitted_symbols: int = 0
    relationships: list[SourceRelationship] | None = None


class Citation(BaseModel):
    id: str
    path: str
    start_line: int
    end_line: int
    excerpt: str
    score: float
    revision: str
    source_analysis: SourceAnalysis | None = None


class MapSupport(BaseModel):
    source_id: str
    coverage: Literal["full", "partial"] | None = None


class MapNode(BaseModel):
    id: str
    kind: Literal["file", "class", "function", "method"]
    label: str
    path: str
    revision: str
    start_line: int | None = None
    end_line: int | None = None
    sources: list[MapSupport] = Field(default_factory=list)


class MapEdge(BaseModel):
    kind: Literal["contains"] = "contains"
    parent_id: str
    child_id: str
    method: str
    source_ids: list[str]


class MapIssue(BaseModel):
    source_id: str
    reason: str
    detail: str


class EvidenceMap(BaseModel):
    scope: Literal["cited_passages"] = "cited_passages"
    nodes: list[MapNode] = Field(default_factory=list)
    edges: list[MapEdge] = Field(default_factory=list)
    issues: list[MapIssue] = Field(default_factory=list)
    node_limit: int
    omitted_nodes: int = 0


class DraftAnswer(BaseModel):
    answer: str = Field(min_length=1)
    citation_ids: list[str]
    answerability: ModelAnswerability
    limitations: list[str] = Field(
        description="Missing information; empty for complete answers, required otherwise."
    )

    @field_validator("answer")
    @classmethod
    def require_answer_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The answer must contain text.")
        return value

    @field_validator("limitations")
    @classmethod
    def require_limitation_text(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Limitations must describe the missing information.")
        return [value.strip() for value in values]

    @model_validator(mode="after")
    def match_assessment(self):
        if self.answerability == "complete" and self.limitations:
            raise ValueError("A complete answer must not report missing information.")
        if self.answerability != "complete" and not self.limitations:
            raise ValueError("Partial and insufficient answers must describe missing information.")
        return self


class ContextChange(BaseModel):
    source_id: str
    path: str
    original_start_line: int
    original_end_line: int
    start_line: int
    end_line: int
    status: str
    added_chars: int = Field(ge=0)


class ContextExpansion(BaseModel):
    method: str
    reason: str
    stop_reason: str
    added_chars: int = Field(ge=0)
    max_added_chars: int = Field(ge=0)
    window_lines: int | None = None
    changes: list[ContextChange]


class RunView(BaseModel):
    id: str
    question: str
    intent: str
    status: str
    answer: str
    answerability: Answerability = "not_assessed"
    limitations: list[str] = Field(default_factory=list)
    citations: list[Citation]
    steps: list[str]
    mode: str
    retrieval: str
    snapshot: str
    context_expansion: ContextExpansion | None = None
    evidence_map: EvidenceMap | None = None
