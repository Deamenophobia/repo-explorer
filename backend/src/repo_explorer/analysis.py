"""Snapshot-bound syntax metadata, independent of retrieval ranking and execution."""

import ast
import hashlib
import platform
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from repo_explorer.config import Settings
from repo_explorer.schemas import SourceAnalysis, SourceRelationship, SourceSymbol
from repo_explorer.sources import CorpusSnapshot


class SourceAnalyzer(Protocol):
    def analyze(self, source: dict) -> SourceAnalysis | None: ...


class NoSourceAnalyzer:
    def __init__(self, settings: Settings, corpus: CorpusSnapshot):
        pass

    def analyze(self, source: dict) -> None:
        return None


@dataclass(frozen=True)
class Definition:
    symbol: SourceSymbol
    start: int
    end: int
    parent_id: str | None


@dataclass(frozen=True)
class ParsedSource:
    content: bytes
    offsets: tuple[int, ...]
    definitions: tuple[Definition, ...]
    status: str


def parse_python(path: str, revision: str, text: str) -> ParsedSource:
    content = text.encode("utf-8")
    # AST columns are UTF-8 byte offsets. Split only on LF, like source ingestion.
    offsets = [0]
    offsets.extend(index + 1 for index, byte in enumerate(content) if byte == 10)
    offsets.append(len(content))
    definitions = []
    try:
        tree = ast.parse(text)
        pending = [(tree, ())]
        while pending:
            node, scope = pending.pop()
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = (
                    "class"
                    if isinstance(node, ast.ClassDef)
                    else "method"
                    if scope and scope[-1][1] == "class"
                    else "function"
                )
                qualified = ".".join([*(name for name, _, _ in scope), node.name])
                start_line = min([node.lineno, *(item.lineno for item in node.decorator_list)])
                start = offsets[start_line - 1] + node.col_offset
                end = offsets[node.end_lineno - 1] + node.end_col_offset
                identity = f"{path}:{revision}:{qualified}:{start}:{end}"
                symbol_id = hashlib.sha256(identity.encode()).hexdigest()[:20]
                definitions.append(
                    Definition(
                        SourceSymbol(
                            id=symbol_id,
                            qualified_name=qualified,
                            kind=kind,
                            is_async=isinstance(node, ast.AsyncFunctionDef),
                            start_line=start_line,
                            end_line=node.end_lineno,
                            coverage="partial",
                        ),
                        start,
                        end,
                        scope[-1][2] if scope else None,
                    )
                )
                scope = (*scope, (node.name, kind, symbol_id))
            pending.extend((child, scope) for child in reversed(list(ast.iter_child_nodes(node))))
    except (SyntaxError, ValueError, RecursionError):
        return ParsedSource(content, tuple(offsets), (), "parse_error")
    return ParsedSource(content, tuple(offsets), tuple(definitions), "analyzed")


class PythonSourceAnalyzer:
    def __init__(self, settings: Settings, corpus: CorpusSnapshot):
        self.limit = settings.source_symbol_limit
        self.parser_version = platform.python_version()
        self.parsed = {
            (file["path"], file["revision"]): parse_python(
                file["path"], file["revision"], corpus.texts[file["path"]]
            )
            for file in corpus.files
            if PurePosixPath(file["path"]).suffix in {".py", ".pyi"}
            and file["path"] in corpus.texts
        }

    def analyze(self, source: dict) -> SourceAnalysis:
        result = SourceAnalysis(
            method="python_ast",
            status="source_unavailable",
            parser_version=self.parser_version,
        )
        if PurePosixPath(source["path"]).suffix not in {".py", ".pyi"}:
            result.status = "unsupported_language"
            return result
        parsed = self.parsed.get((source["path"], source["revision"]))
        if parsed is None:
            return result
        start_line, end_line = source["start_line"], source["end_line"]
        excerpt = source["excerpt"].encode("utf-8")
        result.status = "source_mismatch"
        if not excerpt or not 1 <= start_line <= end_line < len(parsed.offsets):
            return result
        lower, upper = parsed.offsets[start_line - 1], parsed.offsets[end_line]
        start = parsed.content.find(excerpt, lower, upper)
        if (
            start < lower
            or start >= parsed.offsets[start_line]
            or start_line + excerpt.count(b"\n") != end_line
            or parsed.content.find(excerpt, start + 1, upper) != -1
        ):
            return result
        if parsed.status != "analyzed":
            result.status = "parse_error"
            return result
        end = start + len(excerpt)
        overlaps = [item for item in parsed.definitions if item.start < end and start < item.end]
        result.status = "analyzed"
        result.omitted_symbols = max(0, len(overlaps) - self.limit)
        result.symbols = [
            item.symbol.model_copy(
                update={
                    "coverage": "full" if start <= item.start and item.end <= end else "partial"
                }
            )
            for item in overlaps[: self.limit]
        ]
        result.relationships = [
            SourceRelationship(parent_id=item.parent_id, child_id=item.symbol.id)
            for item in overlaps[: self.limit]
        ]
        return result
