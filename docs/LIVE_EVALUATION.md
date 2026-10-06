# Evaluate the live AI pipeline

The live runner exercises the application's `KnowledgeIndex`, `ChatAnswerGenerator`,
and LangGraph workflow on a hash-verified source snapshot. It keeps retrieval coverage,
structural citation validation, and human judgments of answer quality separate.
The [recorded comparisons](LIVE_OBSERVATIONS.md) include real Codex responses on
public teaching fixtures. Local contract tests separately use explicit model doubles;
those tests do not establish remote-provider compatibility or answer quality.

## Prepare an experiment without model calls

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config evaluations/live.example.json --output .repo-explorer/evaluations/live-preflight
```

Omitting `--execute` only checks the source snapshot, annotations, ingestion, adapter
names, and configured credential presence. It never instantiates chat or embedding
providers, checks connectivity, or downloads models. `preflight.json` lists the
selected cases, chunk count, indexed characters, policy size, provider configuration,
and configuration issues. `configuration_ready` means these local checks succeeded;
it does not mean a provider or model works.

The example intentionally leaves live mode and the chat model unset. It can run a
preflight immediately, and reports what still needs configuration. Each output
directory must be new; previous experiments are preserved.

## Configure an explicit provider experiment

Copy `evaluations/live.example.json` to `.repo-explorer/live-eval.json`. Edit its
`workspace` object to select your supported chat model and providers, for example:

```json
{
  "workspace": {
    "mode": "live",
    "chat_provider": "ollama",
    "model": "your-installed-chat-model",
    "base_url": "http://localhost:11434",
    "embedding_provider": "tfidf",
    "lexical_tokenization": "code_identifiers",
    "request_timeout": 45,
    "max_retries": 0
  },
  "max_cases": 10,
  "stop_on_error": true
}
```

This is a configuration shape, not a model recommendation. Install the appropriate
optional adapter from the [configuration guide](CONFIGURATION.md) and prepare its
service/models separately. The chat model must support the adapter's structured-output
contract. The built-in chat choices are `openai`, `anthropic`, `ollama`, and `codex`;
embedding choices are `tfidf`, `openai`, `ollama`, and optional local `fastembed`.

The [Codex CLI adapter](CODEX.md) is a local sign-in alternative for generation.
Use `evaluations/codex.example.json`, replace its model placeholder, and keep chat
endpoint/key fields empty. It records CLI version and completed-turn usage when
available. A saved sign-in is not a connectivity check: the first attempt here
timed out because the CLI lacked the proxy route used by this machine. Supplying
that route completed the same public-fixture question with citations. Set an optional
`REPO_EXPLORER_CODEX_PROXY_URL` in the evaluation process environment, never in its
public JSON configuration. Broader answer-quality review remains separate.

The [first live comparisons](LIVE_OBSERVATIONS.md) document actual explanations,
context limits, and the next contract change suggested by the observed behavior.
They include assistant source inspection, with independent human review pending.

Hosted credentials are read from server environment variables or the root `.env`.
Use `chat_api_key_env` and `embedding_api_key_env` to select other variable names.
The built-in hosted adapters otherwise use their standard provider key variables.
Only variable names belong in experiment JSON. URLs cannot contain credentials,
queries, or fragments. A compatible endpoint that needs a placeholder credential
must receive that value through the environment as required by its adapter.

The experiment supplies all public workspace defaults explicitly, so saved
`repo-explorer.json` and `REPO_EXPLORER_*` environment defaults do not change it.
Credentials are the deliberate exception. Provider SDK defaults can still apply
when an endpoint is omitted; set explicit endpoints when that distinction matters.
The CLI uses built-in adapters without loading installed plugin entry points or
uploading LangSmith traces. Normal application plugin discovery is unchanged.

Source loading is fixed to the copied snapshot and an in-memory vector store.
`corpus_dir` and `extensions` are derived from that snapshot; other applicable
workspace settings, including policy path, exclusions, chunking, retrieval threshold,
tokenization, and context expansion, remain configurable. Every selected file must
survive ingestion. Gold reference notes and evidence ranges never enter indexing or
the generation prompt. Include any required policy file in the snapshot manifest;
the runner cannot read a policy outside that copied corpus.

Optional `case_ids` selects named cases in the supplied order; an empty list selects
all suite cases. Exceeding `max_cases` fails without silently truncating the suite.
The graph attempts generation at most once per case and skips it when retrieval
is empty. SDK retries and embedding batches can create additional network requests;
the case limit is not a billing cap. `max_retries=0` disables retries for the shipped
hosted adapters; Ollama uses its adapter's behavior and the configured timeout.

## Execute and inspect

Run a preflight with your edited configuration, then execute into a new directory:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config .repo-explorer/live-eval.json --output .repo-explorer/evaluations/live-baseline --execute
```

Remote embeddings receive indexed source chunks and questions. Chat receives the
question, retrieved or expanded passages, and policy. Start with the authored public
fixtures; keep private suites, copied source, and reports under ignored local output.
The command does not modify the running app's configuration, index, or saved runs.

Each execution saves the shared `corpus/`, `suite.json`, and `replay-suite.json` plus:

| Artifact | What it establishes |
| --- | --- |
| `config.json`, `effective-workspace.json` | Requested settings and effective snapshot ingestion settings |
| `preflight.json`, `policy.txt` | Local readiness checks, data boundary, and exact policy |
| `report.json` | Snapshot and implementation fingerprints, dependencies, original and expanded passages, evidence coverage, parsed draft, final answer, saved evidence map, workflow steps, timing, and failures |
| `report.md` | Readable drafts, final answers, context, map block labels, and withheld reference notes |
| `review.json` | Initially pending human judgments, bound to the exact report hash |

The optional `workflow.evidence_map` records the production graph's actual map
after citation validation. It contains only cited passages; retrieval artifacts
also retain uncited context. Inspect node coverage, containment provenance, and
reported omissions when assessing a visualization. Older reports can lack this
field. A missing map or an empty edge list supplies no inferred relationship.

The report observes the production graph's
[node updates](https://docs.langchain.com/oss/python/langgraph/streaming), without
adding evaluation annotations to graph state. These question runs use no persistent
checkpointer or human-review interruption; persistence and review decisions are
covered by the application's separate behavior checks.

`reported_chat_usage` contains LangChain callback usage only when the adapter supplies
compatible usage metadata. Missing usage is `null`. Embedding token usage, retry
charges, and total monetary cost are not measured; `cost_usd` is deliberately `null`.
Context characters are not token counts. Stage timings include graph/callback
overhead and are elapsed intervals, not provider-only latency.

| Case outcome | Interpretation |
| --- | --- |
| `answered` | The model reported a complete answer and citations passed structural checks; correctness is ungraded |
| `partial` | The model reported a partial explanation and identified missing information |
| `model_abstention` | Context was supplied, but the model reported insufficient evidence; its explanation is retained |
| `no_context` | Retrieval found nothing; the graph abstained without calling chat |
| `invalid_citations` | A parsed draft failed the existing citation contract |
| `not_assessed` | A legacy generator supplied an unclassified response |
| `error` | Retrieval, expansion, generation, or response parsing failed |
| `not_run` | Preparation failed or an earlier error stopped the experiment |

Report version 2 records `answerability` and `limitations` in the final workflow
state. A declared insufficient response may omit citations; references it does use
are still validated. Complete or partial responses without citations are rejected.
Model abstention is distinct from empty retrieval, and both remain subject to source
inspection. The original draft is preserved even when citation checks reject it.

Version 1 reports predate this contract: their `answered` outcome means only that
the response had valid citations, including cited abstentions. Their citation-free
abstentions were rejected. Keep historical reports unchanged when comparing versions.
Model-reported completeness is never counted as an independent quality judgment.

The default stops after the first case error; set `stop_on_error=false` to inspect
later cases. Completed case results are saved as the run progresses. Error stage
and exception type are retained, but provider exception bodies are omitted because
they may contain credentials or request text. Codex failures also include a
[diagnostic code](CODEX.md#interpret-a-failed-generation) and the child process
`exit_code` when available, in both JSON and Markdown reports. The codes separate
CLI events, incomplete output, and answer-schema failures. Historical
`invalid_response` results cannot be retrospectively assigned a more precise cause.

The evaluation command's own exit codes are 0 for a completed
experiment or a completed preflight, 1 for execution errors, and 2 for invalid input
or unresolved configuration. A preflight with listed issues still exits 0: inspect
`configuration_ready` before automation decides to execute.

## Review support before claiming quality

For each case, inspect the parsed draft if present; otherwise inspect the final
workflow answer. Keep the final outcome alongside the judgment, because an accurate
draft rejected by validation is still an application failure.

1. Break the answer into material claims. Mark each as `supported`, `contradicted`,
   or `not_in_context`. For supported or contradicted claims, record the supplied
   citation IDs and explain which statement establishes the judgment. Merely pointing
   at a real ID is insufficient.
2. Compare against withheld reference notes and spans. Record missing points and
   qualifications, including unproven links between independently retrieved files.
3. Set `answer_assessment` to `complete`, `partial`, `incorrect`, or `abstained`.
   `complete` requires all reviewed claims to be supported and no missing points.
   For abstentions, set `abstention_appropriate` using what the supplied context
   actually supports; a retriever can miss an answer that exists in the full snapshot.
4. Enter `reviewer`, mark the case `reviewed`, and retain pending status for failures
   without a finished answer. Record annotation disagreements in `notes`.

Validate the edited record:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.review --report .repo-explorer/evaluations/live-baseline/report.json --review .repo-explorer/evaluations/live-baseline/review.json --require-complete
```

The validator checks record structure, report identity, source IDs, and required
rubric fields. It cannot certify the reviewer's judgment, guarantee every claim was
reviewed, or establish independent review. Omitting `--require-complete` permits work
in progress. No automatic judge score or pass percentage is produced.

## Compare one change at a time

Begin with live chat plus TF-IDF. Copy the experiment configuration and change only
the embedding provider/model/endpoint to compare learned retrieval, preserving chat,
questions, source snapshot, chunking, context budget, and policy. Keep both results.
Use the copied `replay-suite.json` and `corpus/` to avoid checkout drift.

Compare seed/context evidence coverage first, then supported claims, missing points,
abstentions, context size, and latency. A model can produce different answers even
with identical input, so one pair of runs is exploratory. Cosine thresholds are
model-specific; report any threshold change as an additional variable, and use
separate tuning cases before claiming general improvements. This runner does not
cache remote embeddings or promise deterministic provider responses.

The identifier suite's paraphrase and missing-deployment questions are useful controls,
but these authored cases are not a held-out benchmark. A broader independently
reviewed suite and an ordinary search/assistant comparison remain necessary before
claiming a practical advantage. Publish observed explanations and failure analyses;
do not substitute automated test totals for an engineering case study.
