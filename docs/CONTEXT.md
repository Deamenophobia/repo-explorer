# Bounded source-context expansion

Finding the right chunk does not mean retrieving all the relevant code. A chunk
can contain a function name and setup while stopping before the operation needed
to explain its behavior. Repo Explorer offers a small, optional expansion step
for that failure mode.

## Enable it

In **Settings → Evidence context**, choose `line_window`, set **Surrounding lines**
and **Maximum added characters**, then apply. The default `none` leaves the original
workflow unchanged. These are public workspace settings, so a custom frontend can
set them through [the API](API.md) too.

The LangGraph path becomes:

```text
retrieve → expand_context → compose → validate → finish or human review
```

Without retrieved evidence, the graph goes directly to abstention. The expansion
node runs once before generation; it does not loop or ask an LLM to judge sufficiency.
Its trigger is the user's configured strategy, not a claim that the system detected
missing logic. Retrieval rankings and the number of returned sources stay unchanged.

## How the bound works

For each matched passage, in retrieval order:

1. Find the full text captured at indexing time for the same path and revision.
2. Confirm the seed excerpt is present within its reported line range.
3. Request complete lines above and below that range, clamped to the file boundaries.
4. Expand only when the entire candidate fits the remaining added-character budget.
5. Otherwise keep the original passage and record why it was not expanded.

The default window is eight lines on each side, with a shared allowance of 4,000
added characters. Completing a partly retrieved first/last line also consumes that
allowance. A candidate that is too large is skipped rather than cut mid-line;
later candidates can still use the remaining allowance. A zero allowance retains
the seed text. Overlapping windows can repeat context, and that repetition counts
against the budget. The allowance excludes the original seed text, policy, and
prompt overhead, so it is not a total prompt-size or token-cost limit.

The built-in expander uses immutable strings captured by the source adapter. A
checkout change after indexing does not replace that text. A source adapter that
does not provide full snapshot text produces a visible `source_unavailable` result.
Inconsistent seed metadata produces `source_mismatch`; neither case triggers a
filesystem read or fabricated source text.

## Inspect the saved result

The run response adds `context_expansion`, or `null` when the node did not run.
It records the method, trigger reason, stop reason, effective limits, added
characters, and one change entry per retrieved source. Each entry identifies the
source, original and resulting line ranges, added characters, and a status:

| Status | Meaning |
| --- | --- |
| `expanded` | A larger source window was included |
| `unchanged` | The proposed window contains no additional text |
| `budget_limited` | The complete window did not fit; the seed was preserved |
| `source_unavailable` | No full text matched the seed's path and revision |
| `source_mismatch` | The seed excerpt or line range disagreed with the snapshot |

The run-level stop reason is `budget_limited` if any candidate did not fit;
otherwise it is `pass_complete`. Neither reason asserts that the evidence is
sufficient. Expand **Context expansion details** in the workbench trace to inspect
the ranges and statuses. The trace describes every seed, while answer citations
contain only the sources used by the generator.

Citations carry the expanded excerpt and its actual line range, retaining the
original source ID and revision. The similarity score still belongs to the original
retrieved chunk; the UI labels this distinction. The expanded evidence and trace
are checkpointed before human review. Reloading, restarting, or applying different
settings does not re-expand a pending brief when the review decision resumes.

Trailing blank lines are trimmed from an expanded excerpt. Its ending line and
the trace describe the retained text, so snapshot-based source analysis can verify
the same range. The [HTTPX inspection](MAP_EVALUATION.md) exposed and corrected a
range mismatch at this boundary. Existing saved runs retain their original evidence.

## Reproduce the boundary failure

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation --suite evaluations/context.json --repository examples/context-repository --config evaluations/context-config.json --output .repo-explorer/evaluations/context-example
```

The authored `publish_record.py` example uses small chunks to expose the boundary.
For `publish_record`, the identifier retriever returns lines 5–7, which end before
the pending file is written and replaces the destination. Expansion returns lines
1–10, including those operations. Context grows from 184 to 359 characters. This
is an explicit extra-context tradeoff, not a quality comparison at equal prompt size.

The same method also expands the function for a question about its production
region, although that answer is absent. A no-vocabulary query still returns no
seed and therefore receives no expansion. These cases distinguish context growth
from answerability. The fixture was authored during implementation and is not a
held-out benchmark; the evaluator never executes its write operation.

In the original private investigation, the same strategy recovers missing write
and rename lines but still misses the separate command consumer. This supports an
optional local context strategy, not a claim of complete cross-component analysis.

A separate comparison increased the retrieval chunk size while keeping the other
retrieval settings unchanged. Larger chunks also recovered the write sequence and
recovered a serialization rule that this fixed line window still missed. For the
write question, line-window expansion returned less text than that larger-chunk
configuration. Neither approach solved the broad path or its paraphrase. This is
a small curated case, so it supports keeping both choices configurable rather
than declaring expansion universally better than larger chunks.

## Code and limits

[`context.py`](../backend/src/repo_explorer/context.py) implements the expander
protocol and built-in strategies. [`workflow.py`](../backend/src/repo_explorer/workflow.py)
owns the conditional node and checkpointed state. Custom adapters register through
the [expander factory contract](CONFIGURATION.md#add-an-installed-adapter).

A line window does not parse a function, guarantee a complete body, resolve symbols,
follow calls, find unreturned files, or understand synonyms. More nearby text can
also add irrelevant material. Syntax-aware boundaries and question-driven follow-up
retrieval remain separate improvements to evaluate. Live answer correctness and
semantic sufficiency have not been established by these offline comparisons.
