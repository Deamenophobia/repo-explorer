"""Evaluation data is separate from prompts and never passed to the retriever."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} or part.startswith(".") for part in value.split("/"))
        or any(character in value for character in ("\\", ":", "\x00", "\n", "\r"))
    ):
        raise ValueError("Use a relative, non-hidden POSIX file path without traversal.")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceFile(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _path = field_validator("path")(safe_path)


class SnapshotSpec(StrictModel):
    kind: Literal["files", "git"] = "files"
    revision: str | None = Field(default=None, pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    files: list[SourceFile] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_snapshot(self):
        if (self.kind == "git") != (self.revision is not None):
            raise ValueError("Git snapshots require a full commit hash; file snapshots omit it.")
        if len({file.path.casefold() for file in self.files}) != len(self.files):
            raise ValueError("Snapshot file paths must be unique, including on Windows.")
        return self


class Evidence(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1)

    _path = field_validator("path")(safe_path)

    @model_validator(mode="after")
    def validate_lines(self):
        if self.end_line < self.start_line:
            raise ValueError("Evidence line ranges must be ordered.")
        return self


class EvaluationCase(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    question: str = Field(min_length=3)
    evidence: list[Evidence] = Field(default_factory=list)
    unanswerable: bool = False
    reference_notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.unanswerable == bool(self.evidence):
            raise ValueError("Answerable cases need evidence; unanswerable cases must omit it.")
        if len({item.id for item in self.evidence}) != len(self.evidence):
            raise ValueError("Evidence IDs must be unique within a case.")
        return self


class EvaluationSuite(StrictModel):
    version: Literal[1] = 1
    name: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    snapshot: SnapshotSpec
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique.")
        paths = {file.path for file in self.snapshot.files}
        if any(item.path not in paths for case in self.cases for item in case.evidence):
            raise ValueError("Every evidence path must belong to the snapshot.")
        return self


class RetrievalConfig(StrictModel):
    chunk_size: int = Field(default=1100, ge=100, le=20_000)
    chunk_overlap: int = Field(default=150, ge=0, le=10_000)
    retrieval_limit: int = Field(default=4, ge=1, le=50)
    minimum_score: float = Field(default=0.12, ge=-1, le=1)
    lexical_stop_words: Literal["english", "none"] = "english"
    lexical_ngram_max: int = Field(default=2, ge=1, le=3)
    context_window_lines: int = Field(default=8, ge=1, le=100)
    context_max_added_chars: int = Field(default=4000, ge=0, le=50_000)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        return self
