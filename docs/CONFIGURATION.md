# Workspace configuration and plugins

The Settings screen reads its field constraints and adapter choices from the backend.
Users can configure the workspace without changing Python or React code. Settings
belong to the local server workspace, not to individual browser users.

## Persistence and precedence

Configuration resolves in this order, with later sources winning:

1. Application defaults.
2. `.env` in the server working directory.
3. Process environment variables prefixed with `REPO_EXPLORER_`.
4. Public settings in `repo-explorer.json` (or the path specified by `REPO_EXPLORER_CONFIG_FILE`).

The JSON file may contain a subset of settings. Applying through the UI saves the
complete public configuration. `repo-explorer.json` is ignored by Git. Run the API from
the project root so relative corpus, data, and configuration paths stay consistent.
`REPO_EXPLORER_DATA_DIR`, `REPO_EXPLORER_CONFIG_FILE`, `REPO_EXPLORER_CORS_ORIGINS`,
`REPO_EXPLORER_CODEX_EXECUTABLE`, `REPO_EXPLORER_CODEX_PROXY_URL`, and the
`REPO_EXPLORER_FASTEMBED_*` settings described below
are server-only startup settings. They cannot be changed through `PUT /api/settings`
or the public JSON configuration file.

Apply constructs a new index and graph under the run-service lock, writes the JSON
through an atomic file replacement, then swaps the active runtime. Preparation or
write failure leaves the old runtime active. Existing checkpointed review briefs
retain their original answer and citations. New questions use the new configuration.
Reapply settings after changing source files; there is no automatic file watcher.
Large indexes can make Apply take time and block new runs while rebuilding.

## User-controlled choices

| Area | Fields |
| --- | --- |
| Workspace | `workspace_name`, `repository_name`, `corpus_description`, `suggestions` |
| Generation | `mode`, `generator`, `chat_provider`, `model`, `base_url`, `chat_api_key_env`, `request_timeout`, `max_retries`, `codex_reasoning_effort`, `demo_excerpt_limit` |
| Source | `source_provider`, `corpus_dir`, `policy_file`, `extensions`, `excluded_dirs`, `max_file_bytes`, `max_chunks` |
| Chunking | `chunk_size`, `chunk_overlap` |
| Embeddings | `embedding_provider`, `embedding_model`, `embedding_base_url`, `embedding_api_key_env` |
| Retrieval | `vector_store`, `retrieval_limit`, `minimum_score`, `lexical_tokenization`, `lexical_stop_words`, `lexical_ngram_max` |
| Evidence context | `context_expander`, `context_window_lines`, `context_max_added_chars` |
| Source identity and map | `source_analyzer`, `source_symbol_limit`, `evidence_map_node_limit` |
| Extensions | `plugin_options`, an object keyed by plugin name containing non-secret JSON options |

`GET /api/settings` exposes current public values, the JSON schema, and adapter names.
`PUT /api/settings` replaces public settings; fetch and edit the current values first.
Array environment variables use JSON strings. The schema lists ranges and enums.
Chunk overlap must be smaller than chunk size. Scores use higher-is-better similarity
in the range -1 to 1; recalibrate the threshold when changing embeddings.

Demo mode always uses the local extractive generator and TF-IDF embeddings. Live
mode selects the registered generator and embedding adapter. Choosing a live mode
and model is explicit; failures do not silently fall back to demo output.

### TF-IDF tokenization

`lexical_tokenization` selects `standard` (the existing default) or `code_identifiers`.
The latter splits snake_case, camelCase, PascalCase, and ASCII acronym boundaries
before lowercasing. It indexes word components and a compact spelling: `cache_lookup`
and `cacheLookup` both contribute `cache`, `lookup`, and `cachelookup`. Individual
one-character components are omitted. It changes neither source excerpts nor line
ranges. Stop-word and n-gram settings still apply.

Choose it in the UI, set `REPO_EXPLORER_LEXICAL_TOKENIZATION=code_identifiers`, or
update the public settings through the API. Apply rebuilds the index. This setting
affects only the built-in `tfidf` embedding adapter in demo or live mode; learned
embedding adapters ignore it. New runs record the selected retrieval label, while
existing runs retain their original evidence and label.

Identifier matching can retrieve useful code that standard words miss, but also
more related passages for questions the source cannot answer. It is not a parser,
call graph, synonym model, or evidence-sufficiency check. Cosine scores change with
tokenization, so compare modes on your own corpus before choosing a threshold.
See [the evaluation guide](EVALUATION.md#try-the-identifier-example).

### Bounded evidence context

`context_expander` is `none` by default; choose `line_window` to run one context
expansion step before generation. `context_window_lines` (default 8, range 1–100)
sets how many lines to request above and below each match. `context_max_added_chars`
(default 4000, range 0–50000) is a shared allowance for added excerpt characters
across all matches in the run. It is additional to the retrieved seed text and
counts characters rather than model tokens.

Windows are considered in retrieval order. A window that does not fit is skipped
whole and its seed is preserved; later smaller windows may still fit. A zero budget
keeps all seeds unchanged. Existing runs retain their expansion trace and evidence.
See [the context guide](CONTEXT.md) for provenance, adapter behavior, and limitations.

### Source definition identity

`source_analyzer` defaults to `none`. Select `python_ast` to identify intersecting
Python class, method, and function definitions from the indexed snapshot. The
`source_symbol_limit` bounds metadata per passage; omitted definitions are counted.
Analysis preserves ranking and excerpt text and is recalculated after expansion.
It does not resolve runtime calls. See [source analysis](SOURCE_ANALYSIS.md) for the
API fields, failure states, and pluggable analyzer contract.

`evidence_map_node_limit` controls the combined map of an answer's cited passages
(default 40, range 2–200 blocks, including files). Omitted blocks and unavailable
analysis remain explicit. This setting applies to new runs; saved maps retain
their original evidence and limit. See [the evidence map contract](EVIDENCE_MAP.md).

## Independent model providers

Built-in chat adapters are `openai`, `anthropic`, `ollama`, and `codex`. Embedding adapters
are `tfidf`, `openai`, `ollama`, and `fastembed`. The built-in source is `local` and store is `memory`.
Install optional dependencies before choosing the associated adapter:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[anthropic]'
.\.venv\Scripts\python.exe -m pip install -e '.[ollama]'
.\.venv\Scripts\python.exe -m pip install -e '.[fastembed]'
```

For the optional-provider versions checked with this repository, install
`-r requirements-providers.lock`. Constructor checks exercise adapter setup and
structured-response composition without making live model requests.

For example, chat can use Anthropic while retrieval uses local TF-IDF, or chat can
use an OpenAI-compatible endpoint while embeddings use Ollama. Select each endpoint
and model independently. Ollama requires its server and chosen models to be available.
OpenAI-compatible endpoints must support the selected model's structured-output API.
Provider/model capabilities vary; selecting an adapter does not guarantee compatibility.

The [Codex adapter](CODEX.md) uses an installed native CLI and its saved sign-in.
Select a model and `codex_reasoning_effort`; leave chat endpoint and credential fields
empty. `request_timeout` bounds the whole CLI process. Codex does not use the
workspace retry setting and supplies no embedding adapter. The executable path is
server-only, as is the optional HTTP(S) proxy URL. Without an explicit proxy URL, the
CLI inherits the server's proxy environment. The proxy override applies only to the
Codex child process; generation settings and provider selection remain user-configurable.

OpenAI defaults to `OPENAI_API_KEY`; Anthropic defaults to `ANTHROPIC_API_KEY`.
Credential fields contain environment variable **names**, never keys. Store the
actual values in the server environment or uncommitted `.env`. Plugin options also
must not contain secrets: they are intentionally returned to the browser and saved.
Do not place credentials in endpoint URLs. The bundled Ollama adapter uses its local
server without an API key. Timeout applies to built-in network adapters; retry count
applies to the OpenAI and Anthropic adapters.

Applying remote embeddings sends corpus text to that provider to build the index.
Chat sends retrieved passages and policy when a question is asked. Applying settings
does not make a test chat request. See [the recorded live observations](LIVE_OBSERVATIONS.md)
for the providers and behaviors actually exercised. The default demonstration
remains offline; selecting another provider does not establish its answer quality.

### Local learned embeddings with FastEmbed

The optional `fastembed` adapter implements LangChain's `Embeddings` interface using
[FastEmbed](https://qdrant.github.io/fastembed/). It uses the selected model's
`passage_embed` and `query_embed` methods, preserving any query/document transforms
supplied by the library. It reuses the existing vector store and workflow.

In live mode, select `embedding_provider=fastembed` and a model from
[FastEmbed's supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/).
For example, the comparison uses `BAAI/bge-small-en-v1.5`; it is an explicit example,
not a hardcoded application model. Leave embedding endpoint and credential fields
empty. Chat generation remains independently configured.

The first initialization downloads the selected model. Embedding documents and
questions then runs on this machine without sending their text to an embedding API.
Use ordinary process `HTTP_PROXY` / `HTTPS_PROXY` settings if the download requires
a proxy. The Codex-specific proxy setting applies only to the Codex subprocess.

| Server-only setting | Default | Meaning |
| --- | --- | --- |
| `REPO_EXPLORER_FASTEMBED_CACHE_DIR` | `.repo-explorer/models` | Downloaded model cache; resolved relative to the backend working directory |
| `REPO_EXPLORER_FASTEMBED_THREADS` | `2` | CPU inference threads, configurable from 1 to 64 |
| `REPO_EXPLORER_FASTEMBED_LOCAL_FILES_ONLY` | `false` | Require previously cached model files instead of downloading missing artifacts |

After preparing the chosen model, set local-files-only to `true` for repeat runs
without download attempts. Selecting a missing model then fails explicitly. A failed
settings update preserves the active workspace; it never substitutes TF-IDF.
Changing embedding models requires rebuilding the index. Model token limits can
truncate long passages independently of the character-based chunk settings.

## Add an installed adapter

Repo Explorer discovers trusted Python packages through `importlib.metadata` entry points
at server startup. A plugin adds named factories to `PluginRegistry`; names then
appear in Settings automatically. Install the package and restart the server.
Configuration cannot import arbitrary module paths. Duplicate adapter names fail.

```toml
[project.entry-points."repo_explorer.plugins"]
company = "company_repo_explorer:register"
```

```python
from repo_explorer.sources import local_source

def register(registry):
    registry.register("sources", "company", company_source)

def company_source(settings):
    options = settings.plugin_options.get("company", {})
    # Validate the plugin's own options before any external side effects.
    extensions = options.get("extensions", [".md", ".txt"])
    return local_source(settings.model_copy(update={"extensions": extensions}))
```

| Factory kind | Arguments | Return contract |
| --- | --- | --- |
| `sources` | `settings` | `CorpusSnapshot(documents, files, policy)` |
| `embeddings` | `settings, texts` | LangChain `Embeddings` implementation |
| `stores` | `settings, embeddings` | `add_documents` and `similarity_search_with_score_by_vector` |
| `chat` | `settings` | LangChain chat model supporting `with_structured_output(DraftAnswer)` |
| `generators` | `settings, registry` | Object implementing `generate(question, intent, sources, policy)` |
| `expanders` | `settings, corpus` | `ContextExpander` implementing `expand(sources) -> ExpansionResult` |
| `analyzers` | `settings, corpus` | `SourceAnalyzer` implementing `analyze(source) -> SourceAnalysis \| None` |

Source documents carry `path`, `revision`, `start_line`, and `end_line` metadata;
file entries contain `path` and `revision`. Generators return `answer` and
`citation_ids`. To report coverage, also return `answerability` (`complete`, `partial`,
or `insufficient_evidence`) and `limitations` together, following `DraftAnswer`.
Complete answers require empty limitations; the other assessments require a nonempty
description of missing information. The built-in chat adapter requires these fields.
Legacy generators returning only answer/citations remain usable as `not_assessed`,
which is also how the extractive demo is presented. See [answer coverage](API.md#answer-coverage-is-separate-from-approval).
Vector-store adapters must normalize scores to higher-is-better
similarity and preserve source metadata; many databases return distances instead.
Custom adapters own validation, external resource cleanup, and isolation of any
remote index they create. Build into a new namespace before activation: the runtime
can preserve its old references after failure, but cannot undo external plugin writes.

Custom generators can supply different prompt templates without editing the graph.
Citation validation and explicit human review remain workflow guarantees. Hidden-file
exclusion and source-boundary checks in the built-in loader are deliberate invariants.

`CorpusSnapshot` also accepts an optional `texts` dictionary mapping source paths
to the full indexed text. The built-in local loader supplies it. The `line_window`
expander uses that text only when the file revision and seed excerpt agree with
the snapshot; it never reopens the source path. Source plugins omitting `texts`
remain usable and receive `source_unavailable` trace entries when expansion is
requested. They must not supply live text from a different revision.

Register context adapters in the `expanders` factory group. The protocol and result
type are in `context.py`, and public trace models are in `schemas.py`. Adapters own
their expansion strategy and must honor the configured growth budget, retain source
provenance, and explain changes through `ContextExpansion`. Installed plugin code
is trusted; the built-in line-window guarantees are not a sandbox for arbitrary plugins.

## Local service ports

Use `scripts/start.ps1 -ApiPort 8020 -WebPort 5180`. For manual startup, set
`REPO_EXPLORER_API_URL` for Vite's API proxy and `REPO_EXPLORER_WEB_PORT` for its listening port.
The API port is a uvicorn `--port` argument. Ports and checkpoint storage are startup
settings because changing them requires restarting the relevant service.

## Custom frontend connections

The bundled React interface is optional. Any client can use the backend's HTTP
API; see [the API guide](API.md) for requests, responses, and lifecycle semantics.
The bundled Vite development server proxies relative `/api` requests to the API.
`REPO_EXPLORER_API_URL` configures that proxy, not backend CORS or a compiled
frontend's runtime URL. A static build needs its own proxy or API base URL setup.

For a separate browser frontend calling the API directly, configure exact allowed
origins in the backend environment, then restart the backend:

```dotenv
REPO_EXPLORER_CORS_ORIGINS=["http://127.0.0.1:3000"]
```

The default is `[]`. Each origin includes scheme, hostname, and optional port,
without a trailing slash or path. Wildcards are not accepted. Use the frontend's
origin, not the backend's address; `localhost` and `127.0.0.1` are different origins.
The middleware allows GET, POST, PUT, and JSON content headers for listed origins,
and handles browser preflight requests. It does not enable credentialed browser
requests or provide authentication. Keep the current service on loopback.
