# Development and evaluation

[Project overview](../README.md) · [Documentation index](README.md)

Commands for contributors, optional Git hooks, and reproducible evaluations.

## Layout

```text
backend/src/repo_explorer/    configuration, retrieval, generation, graph, service, API
backend/tests/       API, behavior and restart checks
evaluations/         public, source-backed retrieval evaluation suite
frontend/src/        typed API client, workbench, evidence and trace components
frontend/tests/      browser journeys and reproducible article captures
examples/repository/ public-safe repository knowledge fixture
examples/identifier-repository/ small authored code fixture for tokenization comparisons
examples/context-repository/ authored function split across retrieval chunks
docs/API.md          backend contract, custom clients and connection options
docs/articles/       five-part technical series, captions and image assets
docs/decisions/      framework choice and boundaries
scripts/             local startup, shutdown and documentation tooling
```

Start reading at [the series index](../docs/articles/README.md). Build the self-contained
HTML article preview with `node frontend/scripts/build-docs.mjs`; open
`docs/site/index.html`. Article content and captions describe behavior, not test totals.


## Agent guidance and Git hooks

[`AGENTS.md`](../AGENTS.md) gives coding agents the project's working rules:
justify substantial features with a concrete need, preserve the backend/API boundary,
keep integrations configurable, verify relevant behavior, and distinguish observed
results from planned capabilities. [`CONTRIBUTING.md`](../CONTRIBUTING.md) defines the
shared naming and architectural conventions. Instructions guide judgment; executable
checks catch specific mechanical mistakes.

The repository uses [pre-commit](https://pre-commit.com/) with the official
[Ruff hooks](https://github.com/astral-sh/ruff-pre-commit). Install the optional hook
tools and enable them once per clone, from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-hooks.lock
.\.venv\Scripts\python.exe -m pre_commit install
```

On macOS/Linux, use `.venv/bin/python` in the same commands. Hook definitions and
tool versions are in [`.pre-commit-config.yaml`](../.pre-commit-config.yaml); the installed
Git hook and its interpreter path are local. Reinstall after moving or recreating
the virtual environment. The first Ruff run downloads its pinned environment;
subsequent checks reuse the cache. Network proxy settings for installing tools remain
local environment settings, separate from the application's Codex proxy option.

| Commit check | Scope and behavior |
| --- | --- |
| Local-file guard | Rejects staged `.env` and `.env.*` except `.env.example`, `repo-explorer.json`, and files under `.repo-explorer/`, including forced additions. |
| Whitespace and conflict markers | Checks the staged Git diff. It does not rewrite files. |
| Python lint and formatting | Runs Ruff on staged Python files under `backend/`, in check-only mode. Teaching fixtures and article code blocks are excluded. |

Normal commits check staged content, including partially staged files. Fix failures,
inspect the diff, and stage the intended correction before retrying. The local-file
guard checks paths, not arbitrary secrets or copied private source inside other files;
review the staged diff before sharing. Hooks run locally and are not a server-enforced
policy or proof of answer quality.

Run the checks explicitly when useful:

```powershell
.\.venv\Scripts\python.exe -m pre_commit run
.\.venv\Scripts\python.exe -m pre_commit run --all-files
```

The first command checks staged changes. The second checks all tracked files for
the file-based hooks; the whitespace check still examines only the staged diff.
New untracked files are checked after staging or by passing `--files` explicitly.
To remove this clone's installed hook, run `python -m pre_commit uninstall` using
the same virtual-environment interpreter.

There are no Codex lifecycle hooks enabled by this setup. The optional Codex generation
adapter also keeps hooks disabled so development automation cannot alter its evidence
input. Git hooks do not run E2E tests, contact models, publish, or deploy. They work
independently of the AI assistant used to edit the repository.


## Developer checks

Choose checks based on the change. Backend behavior needs relevant pytest coverage;
frontend changes need type checking and a build, with browser journeys for affected
user flows. Pipeline changes may need an explicit source-backed evaluation. Article
changes need link checks and a rebuilt, rendered preview. Hook checks complement
these steps; they do not replace them.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
cd frontend
npm run build
npx playwright install chromium
npm run test:e2e
```

Stop the local preview first: browser checks own ports 8018 and 5178 and use their
own checkpoint directory. Screenshots are generated into `docs/articles/assets`.

### Verify the live browser workflow

Live browser verification is a separate, opt-in command. It makes real model calls
and can consume provider usage. Copy `evaluations/codex.example.json` to an ignored
local file and choose your accessible model, or supply another configured chat
adapter using the same workspace fields. Then, from the repository root:

```powershell
$env:REPO_EXPLORER_LIVE_CONFIG = (Resolve-Path .repo-explorer/codex-eval.json).Path
cd frontend
npm run test:e2e:live
```

Provide credentials, an optional native Codex executable, and any required proxy
in the test process environment. This command launches its backend from `frontend`,
so it does not load the repository-root `.env`. Only shareable generation choices
belong in the JSON; the proxy value stays private.

The suite owns separate ports (API 8020 and web 5180 by default), configurable with
`REPO_EXPLORER_LIVE_API_PORT` and `REPO_EXPLORER_LIVE_WEB_PORT`. It creates a separate
ignored runtime under `.repo-explorer/live-e2e/` and does not use the preview's index,
settings, or checkpoints. It fixes retrieval to TF-IDF and the authored public context
fixture, taking chat-provider settings from the selected config. No private repository
is used. Ordinary E2E runs and commit hooks do not invoke this suite.

The browser asks for a function explanation with truncated evidence, approves a
partial brief, expands the source context for a complete explanation, and asks an
unanswerable deployment question. It checks source inspection, saved-run reload,
missing-information display, and the absence of approval for insufficient evidence.
It saves actual live screenshots and attaches the returned JSON for source review.
Assertions check the requested classifications; provider disagreement is a result
to inspect, not something the suite rewrites or automatically retries. The browser
checks do not independently grade every generated claim.


## Evaluate retrieval locally

The offline runner compares standard TF-IDF, identifier-aware TF-IDF, and a
keyword-overlap baseline on the same verified source snapshot. A fourth method
adds bounded context to identifier matches and records the additional context size.
The runner records retrieved passages,
missing reference evidence, context returned for unanswerable questions, and
timings. It makes no model calls and does not grade generated answers.

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation --suite evaluations/reference.json --repository examples/repository --output .repo-explorer/evaluations/reference
```

Choose a new output directory for each experiment. The output includes source
files, annotations, effective settings, and JSON/Markdown reports for replay.
See [the evaluation guide](../docs/EVALUATION.md) for Git snapshots, scoring rules,
configuration, and limitations. The public teaching suite is deliberately small;
private repository cases and their source copies stay in local ignored artifacts.


## Evaluate live explanations

The live runner reuses the backend's retrieval, LangChain generator, and LangGraph
workflow. It records the model's parsed draft before citation validation, the final
answer, exact context, coverage gaps, and elapsed timings. Human source-support
judgments remain pending until reviewed; valid citation IDs are not a quality score.

Start with a preflight that makes no provider calls:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config evaluations/live.example.json --output .repo-explorer/evaluations/live-preflight
```

The example reports the missing model configuration. Copy it to an ignored local
file, choose providers/models and server credentials, then use `--execute` with a
new output directory. See [live evaluation](../docs/LIVE_EVALUATION.md) for configuration,
reviewing claims, comparing learned retrieval with TF-IDF, and interpreting failures.
The [recorded live comparisons](../docs/LIVE_OBSERVATIONS.md) include assistant source
inspection. Independent human review and general answer-quality claims remain pending.
The [lexical versus learned retrieval experiment](../docs/SEMANTIC_RETRIEVAL.md) also
includes a pinned public Cachetools package snapshot, model-file identities, and
reproducible configurations. It examines evidence and explanations, not test totals.
The [HTTPX map inspection](../docs/MAP_EVALUATION.md) adds a second pinned public
package, preserves the failed cross-file question, and records follow-ups separately.
A retry completed with the same partial context. Increasing the existing passage
limit recovered API entry points but still missed the synchronous client path;
the default retrieval settings remain unchanged.
