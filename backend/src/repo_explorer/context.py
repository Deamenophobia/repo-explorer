"""One-pass context expansion over an indexed snapshot, with a shared growth budget."""

import re
from dataclasses import dataclass
from typing import Protocol

from repo_explorer.config import Settings
from repo_explorer.schemas import ContextChange, ContextExpansion
from repo_explorer.sources import CorpusSnapshot


@dataclass
class ExpansionResult:
    sources: list[dict]
    trace: ContextExpansion


class ContextExpander(Protocol):
    def expand(self, sources: list[dict]) -> ExpansionResult: ...


class NoContextExpander:
    def __init__(self, settings: Settings, corpus: CorpusSnapshot):
        self.budget = settings.context_max_added_chars

    def expand(self, sources: list[dict]) -> ExpansionResult:
        return ExpansionResult(
            sources,
            ContextExpansion(
                method="none",
                reason="disabled",
                stop_reason="disabled",
                added_chars=0,
                max_added_chars=self.budget,
                changes=[],
            ),
        )


class LineWindowExpander:
    def __init__(self, settings: Settings, corpus: CorpusSnapshot):
        self.window = settings.context_window_lines
        self.budget = settings.context_max_added_chars
        # Keep the indexed text, not file paths to reopen after a checkout changes.
        self.lines = {
            (file["path"], file["revision"]): tuple(
                re.findall(r"[^\n]*\n|[^\n]+$", corpus.texts[file["path"]])
            )
            for file in corpus.files
            if file["path"] in corpus.texts
        }

    def expand(self, sources: list[dict]) -> ExpansionResult:
        expanded, changes = [], []
        added = 0
        for source in sources:
            result = dict(source)
            change = ContextChange(
                source_id=source["id"],
                path=source["path"],
                original_start_line=source["start_line"],
                original_end_line=source["end_line"],
                start_line=source["start_line"],
                end_line=source["end_line"],
                status="source_unavailable",
                added_chars=0,
            )
            lines = self.lines.get((source["path"], source["revision"]))
            if lines is not None:
                start, end = source["start_line"], source["end_line"]
                if (
                    not 1 <= start <= end <= len(lines)
                    or not source["excerpt"]
                    or source["excerpt"] not in "".join(lines[start - 1 : end])
                ):
                    change.status = "source_mismatch"
                else:
                    window_start = max(1, start - self.window)
                    window_end = min(len(lines), end + self.window)
                    excerpt = "".join(lines[window_start - 1 : window_end]).rstrip("\r\n")
                    # Trailing blank lines may have been trimmed from the selected window.
                    # Provenance must describe the retained excerpt for snapshot analysis.
                    excerpt_end = window_start + excerpt.count("\n")
                    growth = len(excerpt) - len(source["excerpt"])
                    if source["excerpt"] not in excerpt:
                        change.status = "source_mismatch"
                    elif growth <= 0:
                        change.status = "unchanged"
                    elif added + growth > self.budget:
                        # Keep the seed intact; never cut a candidate mid-line to fit the budget.
                        change.status = "budget_limited"
                    else:
                        result.update(
                            start_line=window_start, end_line=excerpt_end, excerpt=excerpt
                        )
                        change.start_line, change.end_line = window_start, excerpt_end
                        change.status, change.added_chars = "expanded", growth
                        added += growth
            expanded.append(result)
            changes.append(change)
        return ExpansionResult(
            expanded,
            ContextExpansion(
                method="line_window",
                reason="configured_neighbor_context",
                stop_reason="budget_limited"
                if any(change.status == "budget_limited" for change in changes)
                else "pass_complete",
                added_chars=added,
                max_added_chars=self.budget,
                window_lines=self.window,
                changes=changes,
            ),
        )
