# Backend API and custom clients

Repo Explorer is a Python backend with an optional React frontend. The backend
can ingest a configured repository, retrieve evidence, generate an answer, and
persist or resume a review without starting or building React. A custom frontend,
CLI, or other application uses the same HTTP API.

This guide describes the current local prototype. It has one active workspace
per server and serializes workflow operations and configuration changes within
one backend process. It is not a multi-user or background-job API.

## Start the backend independently

Install the Python dependencies from [Getting started](GETTING_STARTED.md#start-locally), then
run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --workers 1
```

On macOS/Linux, activate `.venv` and use `python -m uvicorn` with the same arguments.
Change `--port` if needed. Node.js is only needed for the bundled frontend and its
development tooling. Stop a manually launched backend with Ctrl+C.

At the example port:

- API base: `http://127.0.0.1:8018/api`
- Interactive endpoint documentation: [Swagger UI](http://127.0.0.1:8018/docs)
- Request and run-response schemas: [OpenAPI JSON](http://127.0.0.1:8018/openapi.json)

Default demo mode uses the bundled teaching corpus, TF-IDF retrieval, and an
extractive generator. It runs the actual LangGraph workflow without model calls.
To use a different repository or model, see [configuration](CONFIGURATION.md).
`corpus_dir` is a path on the backend machine; it is not a browser upload or a
Git URL. The current API does not clone repositories or synchronize Git hosts.

## What stays in the backend

| Component | Responsibility | Code entry point |
| --- | --- | --- |
| FastAPI | Validate HTTP inputs and translate service results into JSON | [`api.py`](../backend/src/repo_explorer/api.py), [`schemas.py`](../backend/src/repo_explorer/schemas.py) |
| Workspace runtime | Prepare adapters, rebuild the index, and apply public settings atomically | [`runtime.py`](../backend/src/repo_explorer/runtime.py) |
| Run service | Create IDs, read checkpoints, serialize operations, and resume pending reviews | [`service.py`](../backend/src/repo_explorer/service.py) |
| LangGraph workflow | Retrieve, compose, validate citation references, finish or interrupt for review | [`workflow.py`](../backend/src/repo_explorer/workflow.py) |
| RAG and LangChain adapters | Load and chunk sources, retrieve passages, and integrate configurable embeddings and models | [`knowledge.py`](../backend/src/repo_explorer/knowledge.py), [`plugins.py`](../backend/src/repo_explorer/plugins.py) |
| SQLite checkpointer | Persist graph state for reload and review resumption | Created during API startup in `api.py` |

Clients own presentation and interaction. They should display the returned
evidence, status, and workflow steps rather than reimplementing the pipeline or
calling model providers themselves. Provider keys remain in the backend environment.
The [plugin contracts](CONFIGURATION.md#add-an-installed-adapter) describe how to
extend ingestion, embeddings, storage, or generation independently of any frontend.

## Endpoint reference

All request and response bodies below use JSON and snake_case fields. Successful
endpoint calls return HTTP 200, including run creation.

| Method and path | Input | Result |
| --- | --- | --- |
| `GET /api/health` | None | `status: "ready"` and current `mode`; readiness does not verify live provider credentials |
| `GET /api/settings` | None | `values`, public JSON `schema`, and installed `adapters` grouped by factory kind, including `analyzers` |
| `PUT /api/settings` | Public workspace configuration | Same shape as GET after validation, index rebuild, and persistence |
| `GET /api/corpus` | None | Indexed `files` with `path` and `revision`, `chunks`, `snapshot`, `retrieval`, `mode`, workspace labels, and `suggestions` |
| `POST /api/runs` | `question` and optional `intent` | A `RunView` after completion, abstention, or a pending human review |
| `GET /api/runs/{run_id}` | UUID in the path | The checkpointed `RunView` |
| `POST /api/runs/{run_id}/decision` | `{"approved": true}` or `{"approved": false}` | The resumed `RunView`; requires a pending review |

For settings, fetch `values`, edit what you need, and PUT the complete object back.
This endpoint is a replacement, not a partial update: omitted fields receive
defaults. Unknown fields are rejected. Preparation or save failures preserve the
active configuration. Applying settings affects all clients of this backend and
can block run operations while rebuilding the index.

```powershell
$apiBase = 'http://127.0.0.1:8018/api'
$settingsDocument = Invoke-RestMethod "$apiBase/settings"
$settingsDocument.values.retrieval_limit = 6
Invoke-RestMethod "$apiBase/settings" -Method Put -ContentType 'application/json' -Body ($settingsDocument.values | ConvertTo-Json -Depth 20)
```

Server-only settings such as data storage paths and allowed browser origins are
configured at startup, not through this endpoint. Reapply public settings to
refresh indexed source files; there is no automatic file watcher.

## Ask a question and inspect its evidence

```powershell
$apiBase = 'http://127.0.0.1:8018/api'
$body = @{
    question = 'How does repository ingestion preserve source references?'
    intent = 'question'
} | ConvertTo-Json
$run = Invoke-RestMethod "$apiBase/runs" -Method Post -ContentType 'application/json' -Body $body
$run.answer
$run.citations | Format-Table id, path, start_line, end_line, revision
Invoke-RestMethod "$apiBase/runs/$($run.id)"
```

`question` must have 3–2000 characters, with at least three after trimming.
`intent` is `question` (the default) or `review`. Each POST creates a new run;
there is no conversational memory shared across separate runs.

`POST /api/runs` waits for the graph to finish or pause. It does not return a job
ticket for background execution. Show a loading state while the request is pending.
There are no streaming tokens, live progress events, cancellation, or run-list
endpoints yet. Save the returned run ID in your client if you want to reload it.
Do not automatically retry POST requests after a network timeout: there is no
idempotency key, and the original operation may still have completed.

### Run response

| Field | Meaning |
| --- | --- |
| `id` | UUID used to read or resume this run |
| `question`, `intent` | The submitted question and workflow choice |
| `status` | Workflow state described below |
| `answer` | Explanation or abstention message; may include references such as `[S1]` |
| `answerability` | `complete`, `partial`, `insufficient_evidence`, or `not_assessed`; separate from workflow status |
| `limitations` | Missing information reported for a partial or insufficient answer |
| `citations` | Source excerpts referenced by this answer, not every retrieved candidate |
| `steps` | Recorded graph node names; these are not a live progress stream |
| `mode` | `demo` or `live`, recorded for this run |
| `retrieval` | Label identifying the retrieval setup |
| `snapshot` | Fingerprint of the indexed file list and revisions used for this run |
| `context_expansion` | Optional expansion trace, or `null` when expansion did not run |
| `evidence_map` | Saved containment map of cited passages, or `null` when no map was saved |

Each citation contains `id`, `path`, `start_line`, `end_line`, `excerpt`, `score`,
and `revision`. Line numbers are one-based and inclusive. Paths are relative to
the configured corpus. With the built-in local source, `revision` is a shortened
content hash, not a Git commit. Treat these identifiers as opaque provenance
values. Scores are similarity values, not confidence probabilities.

The additive `source_analysis` citation field is `null` when analysis is disabled
or absent from an older checkpoint. When enabled, it records the analyzer `method`,
`status`, `parser_version`, intersecting `symbols`, and `omitted_symbols` count.
Symbols include snapshot-bound IDs, qualified names, kinds, definition line ranges,
and full/partial definition-span coverage. This is separate from answerability.
Clients can render it or ignore it; unsupported languages must not be treated as
successfully analyzed. See [the source-analysis contract](SOURCE_ANALYSIS.md) for
all fields, status meanings, and the `analyzers` plugin group.

Optional `source_analysis.relationships` records explicit `contains` edges using
definition IDs. A null parent denotes module scope; a null list means containment
is unavailable. Clients must not infer missing edges from names or line ranges.

The run's optional `evidence_map` supplies `nodes`, `edges`, `issues`, `node_limit`,
and `omitted_nodes`, with `scope=cited_passages`. It is built after citation checks
from the passages cited in the accepted response and saved in the checkpoint.
Node source references retain each passage's full/partial definition coverage.
Edges include their analyzer method and supporting source IDs. Invalid citations
produce no map; older saved runs return `null`. Read the
[map contract and rendering guide](EVIDENCE_MAP.md) before treating the view as
complete: limits and unavailable analysis are explicit, and runtime calls and
cross-file relationships remain outside its current scope.

With context expansion enabled, citations contain the enlarged excerpt and line
range; their scores still describe the original retrieved chunk. The optional
`context_expansion` object records `method`, `reason`, `stop_reason`, `window_lines`,
`max_added_chars`, `added_chars`, and per-source `changes`. Each change contains
`source_id`, `path`, `original_start_line`, `original_end_line`, `start_line`,
`end_line`, `status`, and `added_chars`. It covers all retrieved seeds, including
ones the generator did not cite. Older clients may ignore this additive field;
older saved runs return `null`. See [the context guide](CONTEXT.md) for status
meanings and budget semantics. An expansion trace does not establish answerability.

Use the returned excerpt when presenting saved evidence: the source file may
have changed since the run. There is no raw-file download endpoint. Render
repository content as text or sanitized Markdown, never executable HTML.

### Run lifecycle and human review

| Status | Client behavior |
| --- | --- |
| `completed` | Display the question answer and citations |
| `insufficient_evidence` | Display the abstention; do not offer an approval action |
| `invalid_citations` | Display the rejection message; do not offer approval or present the rejected draft as an answer |
| `awaiting_review` | Display the brief and evidence, then offer an explicit approve/reject choice |
| `approved`, `rejected` | Display the recorded final decision; no further decision is accepted |

A complete or partial question response ends at `completed`. A corresponding review
with valid citations pauses at `awaiting_review`; the backend retains its state in
SQLite. No retrieved sources, or a model assessment of `insufficient_evidence`, stop
without a review gate. Invalid references instead produce `invalid_citations`.
Neither citation structure nor the model's assessment establishes factual support.
The service also has a defensive
`running` fallback for an incomplete saved state; clients should not show review
controls for it or treat it as a promise of background execution.

### Answer coverage is separate from approval

| Answerability | Meaning |
| --- | --- |
| `complete` | The model reports that the supplied context answers the full question; `limitations` is empty. |
| `partial` | The model can explain part of the question and identifies missing information in `limitations`. |
| `insufficient_evidence` | The requested information cannot be determined from the supplied context, or retrieval returned no passages. Missing information is preserved. |
| `not_assessed` | Extractive demo output, a legacy generator/checkpoint without assessment fields, or a rejected draft. |

Render the assessment and limitations alongside the answer. For live generated
responses the assessment is model-reported, not an independent factuality score.
The `abstain` step identifies the separate no-context path, which makes no model call.

Complete and partial responses require citations. An insufficient response may
have an empty citation list; when it includes references, they must still be valid.
Validation covers references in both `answer` and `limitations`. A failed check
withholds the draft, clears its citations and limitations, and reports
`answerability=not_assessed`. Invalid structured classifications fail generation
instead of silently becoming complete answers.

A partial brief can be approved or rejected. Its `answerability`, limitations,
answer, and source snapshot remain unchanged by that decision. Older runs are not
reclassified or regenerated: absent fields return `not_assessed` and an empty list.
This additive checkpoint compatibility does not provide general graph migrations.
Older stored statuses are retained; newly rejected citations now use
`invalid_citations` rather than the previous `insufficient_evidence` status.

Create a review and display it before deciding:

```powershell
$body = @{
    question = 'Review the human review checkpoint policy'
    intent = 'review'
} | ConvertTo-Json
$review = Invoke-RestMethod "$apiBase/runs" -Method Post -ContentType 'application/json' -Body $body
$review.status
$review.answer
$review.citations
```

After the user has inspected the brief and chosen to approve it, send:

```powershell
Invoke-RestMethod "$apiBase/runs/$($review.id)/decision" -Method Post -ContentType 'application/json' -Body '{"approved":true}'
```

Send `false` for rejection. Only enable this action when the current state is
`awaiting_review`. Approval records acceptance of a brief; it does not modify
the repository or certify a code change. A repeated decision returns HTTP 409.
Saved runs and pending reviews survive a restart using the same data directory
and graph version. Graph-schema migrations are not implemented.

## Connect a custom frontend

Choose one of these connection arrangements. React is not required.

**Same-origin proxy.** Have the frontend server forward `/api/*` to the backend,
preserving the path. Browser requests use `/api` on the frontend's origin, so
backend CORS configuration is unnecessary. The bundled Vite configuration already
does this; `REPO_EXPLORER_API_URL` selects its proxy target. Vite's development
proxy is not included in a static build, which needs an equivalent serving proxy
or a separately configured API base URL.

**Direct requests from another browser origin.** Allow the frontend origin in the
backend environment before starting it:

```powershell
$env:REPO_EXPLORER_CORS_ORIGINS = '["http://127.0.0.1:3000"]'
.\.venv\Scripts\python.exe -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --workers 1
```

Then use `http://127.0.0.1:8018/api` as the client's API base URL. Origins must
match scheme, hostname, and port, with no path or trailing slash. `localhost`
and `127.0.0.1` differ. This uses [FastAPI's CORS middleware](https://fastapi.tiangolo.com/tutorial/cors/)
to handle browser preflight and response headers. The default list is empty;
only explicitly configured origins are allowed, without credentialed requests.
Restart to change it. Command-line and server-to-server clients do not need CORS.

### Minimal JavaScript client

This example takes its base URL from the caller. It can be used by a custom React,
Vue, or plain JavaScript UI. The bundled [TypeScript client](../frontend/src/api.ts)
also shows the current response interfaces; it is an example, not a separately
versioned SDK.

```javascript
function createRepoExplorerClient(apiBase) {
  const base = apiBase.replace(/\/$/, '');

  async function request(path, method = 'GET', body) {
    const response = await fetch(`${base}${path}`, {
      method,
      ...(body === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === 'string'
        ? data.detail
        : JSON.stringify(data.detail ?? data);
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    return data;
  }

  return {
    settings: () => request('/settings'),
    saveSettings: (values) => request('/settings', 'PUT', values),
    corpus: () => request('/corpus'),
    ask: (question, intent = 'question') => request('/runs', 'POST', { question, intent }),
    run: (id) => request(`/runs/${encodeURIComponent(id)}`),
    decide: (id, approved) => request(`/runs/${encodeURIComponent(id)}/decision`, 'POST', { approved }),
  };
}

const api = createRepoExplorerClient('/api'); // Same-origin proxy.
// For direct requests, pass your configured absolute API base URL instead.
const run = await api.ask('How do checkpoints make human review durable?');
console.log(run.status, run.answer, run.citations);
```

## Errors and operating limits

FastAPI errors have a `detail` field: a message string for service errors or an
array of validation issues for malformed input. Clients should handle both.

| HTTP status | Meaning and action |
| --- | --- |
| `404` | A well-formed run UUID has no saved state; check the ID and backend data directory |
| `409` | The run has no pending review; reload it before offering another action |
| `422` | Invalid request, invalid UUID, or settings that could not be prepared/saved; correct the input |
| `502` on run creation | Generation or pipeline execution failed; inspect backend configuration and logs |

The API is currently unversioned; custom clients should target the same project
revision as the server. See [live observations](LIVE_OBSERVATIONS.md) for the tested
provider and fixtures; other provider combinations need their own verification.
Browser CORS grants are not authentication: the application
has no user or document-level authorization. Keep it on loopback. Serving a remote
or multi-user frontend requires a separate authentication and deployment design.

For the next backend work, the [evaluation guide](EVALUATION.md) describes how to
measure retrieval failures before changing RAG or LangGraph behavior. A replacement
frontend should be able to consume those improvements through this same boundary.
