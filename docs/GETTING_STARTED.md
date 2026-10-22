# Getting started

[Project overview](../README.md) · [Documentation index](README.md)

Run all commands from the repository root. Start with the offline fixture, then configure your own source directory and providers.

## Start locally

The backend requires Python 3.12+. The bundled frontend additionally requires
Node.js 22+. Run commands from this repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

**Backend only:** no frontend installation or build is needed.

```powershell
.\.venv\Scripts\python.exe -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --workers 1
```

The API is at `http://127.0.0.1:8018/api`, with interactive documentation at
[`/docs`](http://127.0.0.1:8018/docs) and schemas at
[`/openapi.json`](http://127.0.0.1:8018/openapi.json). Use one backend worker for
the current local runtime. See [the API guide](../docs/API.md) to make your first request.

**Backend plus bundled frontend:** instead of the backend-only command, install
the frontend dependencies and start both services:

```powershell
cd frontend
npm ci
cd ..
.\scripts\start.ps1
```

The launcher opens no external windows. Visit [the workbench](http://127.0.0.1:5178).
Stop the launched services with
`./scripts/stop.ps1`. On macOS/Linux, activate the virtual environment and run
`python -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --workers 1`
in one terminal; optionally run `npm run dev` from `frontend` in another.

The bundled frontend sends relative `/api` requests through Vite's development
proxy. For a custom frontend, choose a proxy or configure allowed browser origins
with `REPO_EXPLORER_CORS_ORIGINS`; see [client connection options](../docs/API.md#connect-a-custom-frontend).

The default corpus is a public-safe teaching fixture. Demo mode runs real
LangChain retrieval and a real LangGraph state machine, using local TF-IDF vectors
and an extractive response generator. It makes no model calls. **It is not a
demonstration of learned semantic retrieval or live LLM answer quality.**


## Configure your workspace

Open **Settings** in the workbench to change workspace labels, suggested questions,
repository directory, file selection, chunking, retrieval limits, chat and embedding
providers, models, endpoints, and installed adapters. Apply validates the configuration,
rebuilds retrieval, and saves `repo-explorer.json` before switching the active workspace.
Existing review evidence remains available. Invalid changes leave the active setup intact.

Defaults can also be supplied through `.env` or `REPO_EXPLORER_` environment variables;
saved JSON settings take precedence. Credentials remain in server environment variables.
See [configuration and plugin contracts](../docs/CONFIGURATION.md) for every setting,
optional providers, custom adapters, and non-secret plugin options.
Local ports are configurable: `./scripts/start.ps1 -ApiPort 8020 -WebPort 5180`.

Machine-specific values belong in the ignored `.env`, including the optional
`REPO_EXPLORER_CODEX_PROXY_URL`. Commit only placeholders in `.env.example`.
An enabled Windows proxy does not automatically configure the CLI's network route;
see [Codex proxy setup](../docs/CODEX.md#networks-that-require-a-proxy). Users without
that requirement can leave the proxy setting unset.

With TF-IDF, **Settings → Retrieval → TF-IDF tokenization → code_identifiers**
enables matching across words inside `snake_case`, `camelCase`, and `PascalCase`
names. The default remains `standard`. This is a lexical option, not symbol
resolution or learned semantic retrieval. The [evaluation guide](../docs/EVALUATION.md)
includes a reproducible example and shows where the option still fails.

**Settings → Evidence context → line_window** enables an optional LangGraph step
that adds neighboring lines to retrieved passages. Users control the line window
and shared extra-character budget. The trace records original/expanded ranges and
skipped windows, and reads from the indexed snapshot. It cannot discover a missing
file or establish that the question is answerable. See [bounded context expansion](../docs/CONTEXT.md).

Live responses report **complete**, **partial**, or **insufficient evidence**, with
missing information shown beside the answer. These are model assessments of the
supplied context, not factuality guarantees. Workflow status is separate: approving
a partial brief preserves its limitations. Insufficient responses stop before review;
invalid citations receive a distinct rejection. Demo and older saved responses show
**not assessed**. Custom clients can use the same [answerability fields](../docs/API.md#answer-coverage-is-separate-from-approval).

Optional **Source analysis → python_ast** identifies the class and function names
behind Python passages, including excerpts that omit the class header. It preserves
retrieval ranking, records partial definition coverage, and reports unsupported or
unparseable files explicitly. The analyzer and per-passage limit are configurable;
the API exposes the same metadata to custom frontends. See
[source identity and its limits](../docs/SOURCE_ANALYSIS.md). This is syntax provenance,
not a runtime call graph.

The **Evidence map** below the workflow trace groups the answer's cited files and
definitions using those containment relationships. Select a block to see its
supporting passages, then open one in the source explorer. **Maximum map blocks**
controls the saved view's size; missing analysis and omissions remain visible.
The backend saves the same nodes and edges for any API client. See
[the evidence map guide](../docs/EVIDENCE_MAP.md) for scope, configuration, and the
actual browser example.


## Live generation

Copy `.env.example` to `.env`, set `REPO_EXPLORER_MODE=live`, `REPO_EXPLORER_MODEL` to a supported
model, and `OPENAI_API_KEY` in the server environment. The adapter uses
`langchain-openai`; the endpoint must support its structured-output contract.
An optional `REPO_EXPLORER_BASE_URL` supports compatible endpoints, but compatibility is
provider-specific. No API key belongs in browser code or article assets.

Set `REPO_EXPLORER_EMBEDDING_PROVIDER=openai` and `REPO_EXPLORER_EMBEDDING_MODEL` to enable learned
semantic embeddings. With the default `tfidf` provider, live generation still
uses the lexical retrieval baseline. Configuring remote
embeddings sends indexed text to that provider; configuring live generation sends
retrieved passages and policy to the model. Use a curated corpus you intend to send.
Use Apply settings to rebuild after corpus changes. File/environment edits require
a restart. Recalibrate `REPO_EXPLORER_MINIMUM_SCORE`
when changing embedding models; cosine scores are not confidence probabilities.

For local learned embeddings, install `.[fastembed]`, select `fastembed` as the
embedding provider, and choose a supported embedding model in Settings. The first
use downloads model files; embedding runs locally afterward. Leave the embedding
endpoint and credential fields empty. Cache location, CPU threads, and cached-only
operation are [server settings](../docs/CONFIGURATION.md#local-learned-embeddings-with-fastembed).
This works independently of the chat provider, including Codex CLI generation.

The hosted API adapters still need their own credentials and live verification.
An optional **Codex CLI adapter** can
reuse the server user's CLI sign-in: select `codex` as the chat provider and choose
an accessible model. See [Codex setup and evaluation](../docs/CODEX.md). A local Codex
run completed the pipeline and returned cited explanations of both public cache
examples after configuring the backend's proxy. This confirms that integration on
that teaching question; it is not a general answer-quality result. The subsequent
[live comparisons](../docs/LIVE_OBSERVATIONS.md) show how incomplete context, missing
facts, and paraphrases affect the pipeline. Provider failures remain explicit.
