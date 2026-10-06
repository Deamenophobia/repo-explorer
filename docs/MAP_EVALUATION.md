# Inspecting repository evidence on HTTPX

The first evidence map shows definitions and their containing files or classes.
We checked that behavior on HTTPX after developing it with an authored fixture
and Cachetools. The useful question was whether it exposes missing context and
supported identity when the source spans several modules.

This was an assistant's developer inspection on 6 October 2026 (Singapore time).
It compares available information and records failures. Independent readers,
investigation time, and an advantage over IDE navigation remain unmeasured.

## Fix the source and questions first

The [protocol](../evaluations/httpx-map-protocol.md) and
[reference suite](../evaluations/httpx.json) were written before pipeline execution.
The source is HTTPX 0.28.1 at commit
`26d48e0634e6ee9cdc0533996db289ce4b430177`: all Python files under `httpx/`.
Tests, documentation, HTTPcore implementation, and applications using HTTPX are
outside this corpus. Its [BSD license](../evaluations/httpx-LICENSE.md) is retained.
Git blobs supply the snapshot; repository code is never imported or executed.

The three questions ask about `Response.raise_for_status`, the synchronous path
from `httpx.get` to a transport's `handle_request`, and an application's production
cloud region. Source inspection established the expected evidence before looking
at retrieval results. It used definition searches, enclosing classes, and explicit
call sites in the pinned source. The assistant may already know HTTPX; no unfamiliar
human-reader claim follows from this procedure.

The baseline uses local `BAAI/bge-small-en-v1.5` embeddings, 1,100-character chunks,
150-character overlap, two passages, no score cutoff, and no context expansion.
Python AST analysis is enabled with eight definitions per passage and forty map
blocks. Generation uses the Codex adapter, requested model `gpt-6-astra`, medium
reasoning, a 120-second timeout, and zero retries. The recorded CLI version is
0.160.0. The manifest covers 23 source files and produces 341 chunks at these settings.
These dimensions describe this package check; they establish no large-repository
capacity claim.

## What the baseline showed

| Question | Supplied evidence | Observed result |
| --- | --- | --- |
| Who owns `raise_for_status`, and what does it do? | `_models.py:794–818` and an exception-class example | A partial answer cites the method fragment. Its saved map contains the file, `Response`, and `Response.raise_for_status`. The model reports the missing final raise. |
| How does synchronous `httpx.get` reach a transport? | `_transports/base.py:34–62` and `_transports/default.py:217–250` | The context lacks the public API and client delegation path. Generation fails with `CodexInvocationError`, code `invalid_response`; no parsed draft, final answer, or map is available. |
| Which production region hosts an application using the library? | No execution in this baseline | The configured stop-on-error behavior leaves this case `not_run`. A separate continuation is recorded below. |

### Identity and behavior require different evidence

The first passage begins at the method definition. The owning class starts at
[`_models.py:515`](https://github.com/encode/httpx/blob/26d48e0634e6ee9cdc0533996db289ce4b430177/httpx/_models.py#L515),
well outside the excerpt. The parser establishes its identity from the full
indexed file, so the map can place the method inside `Response`. Both definitions
carry partial-span coverage. The second retrieved passage is uncited and does
not appear in the map.

The existing source cards already expose the same definition names and coverage.
The map adds a grouped presentation and navigation to those passages. This check
does not establish faster investigation or additional semantic knowledge from the
map itself.

The answer describes the missing-request guard and the `is_success` return, both
present in its source. It qualifies the non-success explanation because the actual
[`HTTPStatusError` raise at line 829](https://github.com/encode/httpx/blob/26d48e0634e6ee9cdc0533996db289ce4b430177/httpx/_models.py#L829)
is absent. The source's docstring mentions that exception, but the returned body
ends during message construction. A supported class identity cannot fill that gap.

Strict gold-span coverage reports missing evidence when the complete annotated
text is absent. That includes the class header, even though analysis establishes
the owner. Text coverage, definition identity, and supported behavior must be
inspected separately.

### A call path needs evidence across modules

Source inspection follows `get → request → Client.request → send →
_send_handling_auth → _send_handling_redirects → _send_single_request →
transport.handle_request`. The relevant delegation begins in
[`_api.py`](https://github.com/encode/httpx/blob/26d48e0634e6ee9cdc0533996db289ce4b430177/httpx/_api.py#L195)
and continues through
[`_client.py`](https://github.com/encode/httpx/blob/26d48e0634e6ee9cdc0533996db289ce4b430177/httpx/_client.py#L1001).
Authentication and redirect handling can repeat work. Transport selection depends
on the configured mounts and client transport.

The retrieved transport fragments show the far end of this question. Neither
contains those API/client call sites. Containment metadata cannot establish their
sequence. Full-source inspection had a larger information budget than this
two-passage context. It supplies a reference reading for the gap; the different
budgets prevent a controlled comparison of tools.

The generation error is also an observed outcome. The runner preserves its stage
and safe error code; these do not identify the underlying cause. The original
failed run remains unchanged. There is no generated cross-file explanation or map
to grade for this case.

## Separate follow-ups

The first follow-up selected only `response-status` and enabled the existing
line-window expander with twelve neighboring lines and a 4,000-character growth
budget. It recovered the complete `raise_for_status` body, including the final
raise. Its answer explained that behavior but withheld the owning class.

Inspection exposed a provenance bug: expansion trimmed trailing blank lines from
the excerpt while retaining the window's original ending line. The returned text
ended at line 829 but was labeled through line 830. The strict analyzer returned
`source_mismatch`, so the saved map contained only the file and an explicit issue.
This was a reproducible integration failure between expansion and source analysis.

The correction makes the ending line describe the retained text, in both the
citation and expansion trace. Regression cases cover a window ending in blank
lines inside a file and at its end, including class/method analysis. The first
follow-up remains intact as `httpx-map-expanded-v1`; `httpx-map-expanded-v2` repeats
the same question and configuration with the correction.

The corrected run returned an answer identifying `Response`, the successful return,
the non-success exception, and the missing-request guard. Its map includes
`Response.raise_for_status` with full coverage, its containing class with partial
coverage, and the overlapping `has_redirect_location` fragment with partial
coverage. No map issue was reported. The before/after excerpts, scores, ordering,
snapshot, policy, and configuration match; the changed source fields are the
ending line and analysis metadata. The implementation fingerprint changes.

The model labeled this answer complete. Assistant inspection supports its stated
claims at the `self.is_success` branch level. The property definition identifying
success as 2xx remains outside the context, and the answer makes no status-range
claim. The gold-span metric still reports that definition and the class header as
missing. A full method span does not imply that all called predicates or dependencies
are present. This single corrected example establishes no general answer-quality gain.

The deployment question ran separately with the baseline workspace settings.
Retrieval supplied module imports and export bookkeeping. The model reported
`insufficient_evidence` and identified the missing application deployment
configuration. Its map contains two file blocks with no edges. A map can accompany
an explanation of missing evidence; its presence does not establish answerability.

### Retry the failed cross-file question with better diagnostics

The initial `invalid_response` grouped several possible failures. The adapter now
records distinct [failure codes](CODEX.md#interpret-a-failed-generation) for CLI
events, missing completion or answer, malformed events, and schema validation.
Available process exit status is retained; raw error bodies remain excluded.

The separate `httpx-path-diagnostics-v1` run repeats only `sync-request-path`.
Its question, workspace settings, policy, snapshot, and exact analyzed passages
match the original failed case. This request completed and returned a partial
answer: it describes `HTTPTransport.handle_request` constructing an HTTPcore
request and calling its pool, identifies the base transport stub, and explicitly
states that the API/client path is absent. Assistant inspection supports those
limited claims. Its map groups definitions within the two transport files and
contains no cross-file call relationship.

The successful repeat cannot explain the historical failure or establish provider
reliability. It demonstrates that the missing call-path evidence persists when
generation completes. Both runs remain intact, with independent human review pending.

### Check the existing passage limit before adding a new workflow

An offline check fixed passage limits at two, four, and eight before inspecting
their results. It used one index and prefixes of the top eight results, with the
same question, embeddings, chunking, cutoff, and analysis. No chat model was called.
The first two results match the original context exactly.

| Passage limit | Context characters | Evidence recovered |
| --- | --- | --- |
| Two | 2,128 | The two transport fragments from the original run |
| Four | 4,026 | More transport and client lifecycle text; the annotated call path remains absent |
| Eight | 6,950 | The public `get → request` and `request → client.request` delegations appear; synchronous client dispatch, authentication, redirects, and transport selection remain absent |

The larger context also includes asynchronous transport code and
`AsyncClient._transport_for_url`, although the question asks about synchronous
execution. Definition metadata makes this distinction inspectable. Selecting
passages by similar names alone would risk joining different paths.

Increasing the existing limit recovers part of the entry point on this case. It
does not recover the complete path within these bounds, and no answer-quality
claim follows from this offline check. Defaults remain unchanged. The report is
`httpx-path-limits-v1`; these development questions still need broader evaluation.

## Reproduce the inspection

Install the optional embedding adapter using the
[learned-retrieval setup](SEMANTIC_RETRIEVAL.md#reproduce-the-comparison).
The [model manifest](../evaluations/semantic-model-manifest.json) records the
ONNX and tokenizer identities used by that setup. Model names alone do not pin
downloaded bytes. Copy
[`httpx-map.example.json`](../evaluations/httpx-map.example.json) to an ignored
local configuration, select an accessible model, and supply credentials and any
proxy in the process environment as described in [live evaluation](LIVE_EVALUATION.md).

```powershell
git clone --no-checkout --depth 1 --branch 0.28.1 https://github.com/encode/httpx.git .repo-explorer/external/httpx-0.28.1
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/httpx.json --repository .repo-explorer/external/httpx-0.28.1 --config .repo-explorer/httpx-map.json --output .repo-explorer/evaluations/httpx-preflight
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/httpx.json --repository .repo-explorer/external/httpx-0.28.1 --config .repo-explorer/httpx-map.json --output .repo-explorer/evaluations/httpx-baseline --execute
```

Use an existing matching clone if already present. The suite verifies the commit,
canonical file hashes, and annotated source anchors. Each output directory must
be new. Preflight makes no provider calls; execution can download embedding weights
and calls the selected chat provider. The recorded runs used cached embedding files
with `REPO_EXPLORER_FASTEMBED_LOCAL_FILES_ONLY=true` and tracing disabled.

For the expansion follow-up, copy the baseline configuration, select
`"case_ids": ["response-status"]`, and set these workspace fields:

```json
{
  "context_expander": "line_window",
  "context_window_lines": 12,
  "context_max_added_chars": 4000
}
```

For the deployment continuation, keep the original workspace settings and select
`"case_ids": ["missing-deployment"]`. Run each with a new output directory.
Questions, gold annotations, ranking settings, and model selection stay fixed.
Generation is variable, so these executions cannot guarantee identical answers.
For the diagnostic retry, select `"case_ids": ["sync-request-path"]` with the
baseline workspace settings and use the updated adapter.

Local artifacts remain under `.repo-explorer/evaluations/`: `httpx-map-v1`,
`httpx-map-expanded-v1`, `httpx-map-expanded-v2`, and `httpx-map-deployment-v1`.
The diagnostic retry is `httpx-path-diagnostics-v1`.
The source-inspection record
is `httpx-source-inspection-v1/navigation.json`. Reports retain exact passages,
configuration, implementation fingerprints, outcomes, and the production graph's
saved map. Separate assistant assessments are bound to the report hashes;
`review.json` remains pending for independent human review.

### Repeat the offline limit check

With the same source clone and local configuration prepared above, run this Python
recipe from the repository root using the project's virtual environment. Choose a
new output directory. It uses the existing source verifier and `KnowledgeIndex`;
chat providers are never instantiated. Cached local embeddings can be required
through `REPO_EXPLORER_FASTEMBED_LOCAL_FILES_ONLY=true` after the model is downloaded.

```python
from pathlib import Path
from repo_explorer.config import Settings
from repo_explorer.evaluation.artifacts import prepare_snapshot, write_json
from repo_explorer.evaluation.live_models import LiveEvaluationConfig
from repo_explorer.evaluation.models import EvaluationSuite
from repo_explorer.evaluation.runner import score_evidence
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import builtin_registry

suite = EvaluationSuite.model_validate_json(Path("evaluations/httpx.json").read_text())
config = LiveEvaluationConfig.model_validate_json(
    Path(".repo-explorer/httpx-map.json").read_text()
)
output = Path(".repo-explorer/evaluations/httpx-limits-repeat").resolve()
sources = prepare_snapshot(suite, Path(".repo-explorer/external/httpx-0.28.1"), output)
settings = Settings(_env_file=None, **{
    **config.workspace.model_dump(),
    "retrieval_limit": 8,
    "corpus_dir": output / "corpus",
    "extensions": [".py"],
    "data_dir": output / "runtime",
    "config_file": output / "unused-settings.json",
})
case = next(item for item in suite.cases if item.id == "sync-request-path")
index = KnowledgeIndex(settings, builtin_registry())
hits = index.search(case.question)
write_json(output / "limits.json", {
    "question": case.question,
    "workspace": settings.public().model_dump(mode="json"),
    "results": [{
        "limit": limit,
        "context_chars": sum(len(hit["excerpt"]) for hit in hits[:limit]),
        "evidence": score_evidence(case, hits[:limit], sources),
        "hits": hits[:limit],
    } for limit in (2, 4, 8)],
})
```

## What this changes next

The next retrieval experiment should address the missing synchronous client call
sites with a bounded evidence-gathering step. It needs to record why each additional
passage was selected and stop when the required source remains unavailable.
LangGraph can coordinate those steps while LangChain adapters supply retrieval
and generation. A call edge would also need its own source-analysis contract and
call-site provenance before the UI could display it.

That proposal still needs evaluation against the preserved baseline. Broader
languages, frontend/backend boundaries, independent reader studies, embedding
truncation effects, and large-repository performance remain open. The public
articles describe these observations; their screenshots continue to use authored
teaching sources.
