# Codex as an optional local generation provider

Select `chat_provider=codex` to connect Repo Explorer's LangChain prompt to the
installed Codex CLI. The CLI owns sign-in; the application does not read, copy, or
convert its authentication tokens. LangGraph retains retrieval, citation validation,
and human-review transitions. The frontend uses the same backend APIs.

Codex documents [saved authentication and structured non-interactive output](https://learn.chatgpt.com/docs/non-interactive-mode).
This adapter uses those interfaces for a trusted local development workspace. It
does not expose your personal Codex account as a public model service.

## Configure it

Install/sign in to Codex separately and confirm `codex login status` in the server's
user account. In **Settings → Generation**, choose:

| Setting | Value |
| --- | --- |
| Mode | `live` |
| Chat Provider | `codex` |
| Chat model | A model accessible through your Codex sign-in |
| Codex reasoning effort | A level supported by that model |
| Chat endpoint | Empty |
| Chat credential environment variable | Empty |
| Request Timeout | Overall CLI process deadline, including startup; configurable up to 300 seconds |

The defaults remain the offline demo and TF-IDF. Codex supplies generation only;
choose an embedding provider separately if you want learned semantic retrieval.
No particular model name is hardcoded in the adapter. `max_retries` does not retry
the CLI invocation; Codex may retry transport requests internally before the process
deadline. Your Codex account's usage limits still apply.

The server resolves a native `codex.exe` on Windows or `codex` on other platforms.
To specify another installed binary, set the server startup variable
`REPO_EXPLORER_CODEX_EXECUTABLE` to its absolute path. Use the native binary so timeout
handling targets the actual CLI process. Script wrappers are rejected.
For an npm installation on Windows, the native executable is inside its platform
package's `vendor` directory. This executable setting is server-only and cannot be
changed through the browser or saved public workspace JSON. Set it in the process
environment for evaluation; the API server also reads its startup `.env`.

### Networks that require a proxy

The CLI inherits the backend process's `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY`
environment. An enabled Windows user proxy does not guarantee that the CLI will use
it. If this server needs a different route, set `REPO_EXPLORER_CODEX_PROXY_URL` to
your HTTP or HTTPS proxy URL. The API reads it from the server environment or its
uncommitted `.env`; the evaluation runner requires it in the process environment.
Restart the API after changing startup settings.

This optional server-only setting overrides HTTP(S) proxy variables for the Codex
child only, preserves `NO_PROXY`, and does not change Windows settings or other
providers. Leave it unset to inherit the usual environment. The URL is redacted in
settings serialization and excluded from public workspace settings, model metadata,
and evaluation reports. Proxy credentials, if needed, belong only in this private
startup setting. Keep local API addresses in your bypass rules.

The integration targets CLI **0.160.0**, including `--ignore-user-config`, JSONL
events, ephemeral requests, and structured-output flags. Older or changed CLIs may
fail explicitly. Applying settings checks the executable/version but does not
verify model access or run an inference request.

## Keep the experiment tied to supplied evidence

Every request starts a fresh CLI turn in a temporary directory containing only
the response schema and the application's system instructions. The question and
retrieved passages enter through stdin, not shell arguments. The adapter does not
resume this development chat or mount the source repository for the model to search.

It ignores user CLI configuration and supplies its own generation settings, disables
project instructions and memory injection, and disables shell, browser, app, plugin,
hook, and multi-agent capabilities. Web search is disabled. It selects the read-only
sandbox and rejects observed tool activity in the event stream. CLI authentication
still uses the server account's normal Codex credential storage.

These controls are part of the generation contract. User model and retrieval choices
remain configurable; enabling autonomous file access would require a separate adapter
and a different evaluation claim. Managed CLI policies or runtime behavior can still
affect invocation, so this is not a claim that the CLI is an independently audited
sandbox. A completed public-fixture request returned a structured answer without
observed tool events. This demonstrates the integration on that request, not a
guarantee of isolation or groundedness for every future answer.

## Run the evaluation

Copy `evaluations/codex.example.json` into an ignored local file, replace its model
placeholder, and select the cases to run. For example:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config .repo-explorer/codex-eval.json --output .repo-explorer/evaluations/codex-preflight
```

Add `--execute` and use a new output directory for a real run. Preflight checks local
configuration and executable availability; it does not contact Codex or establish
that saved sign-in grants working model access. See [live evaluation](LIVE_EVALUATION.md)
for reports and the source-support rubric.

The report records the CLI version and usage from a completed CLI turn when supplied.
The requested model name identifies that usage; it is not a server-reported model
revision. Missing usage and costs remain unknown. Provider stderr and credentials
are omitted. CLI initialization errors remain preparation failures. Nonfatal startup
diagnostic items do not override a successful final turn.

### Interpret a failed generation

The adapter distinguishes the CLI process, its
[JSONL events](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable),
and the final structured answer. Evaluation reports preserve these local diagnostic
codes and an `exit_code` when a process result is available:

| Code | What was observed |
| --- | --- |
| `timeout` | The process exceeded the configured deadline |
| `unavailable` | The native executable could not start |
| `cli_failed` | The process exited unsuccessfully without an earlier, more specific stream failure |
| `turn_failed` | The CLI emitted `turn.failed` |
| `stream_error` | The CLI emitted a top-level `error` event |
| `invalid_event_stream` | JSONL or an event/item shape was invalid |
| `invalid_usage` | A completion event supplied an invalid usage object |
| `missing_completion` | No completion event arrived |
| `missing_answer` | Completion arrived without a final text answer |
| `tool_activity` | The stream contained an item outside the permitted text/reasoning/diagnostic types |
| `invalid_structured_output` | The completed text failed the existing Pydantic answer contract |

An explicit stream failure is retained even when the process exits nonzero.
A nonzero process exit can never produce an accepted answer. The first rejected
event determines the stream classification. These codes identify an observed
boundary; `turn_failed` alone does not establish a network, authentication, or model
service cause. Timeout and launch failures have no returned process exit status;
schema validation occurs after event parsing and does not retain that status.

Raw CLI messages, stderr, and invalid model text are excluded from exceptions and
evaluation diagnostics. Schema failures still use LangChain's Pydantic parser,
with a wrapper that replaces its raw-output exception with a fixed message.
Existing reports using `invalid_response` keep that historical value; their cause
cannot be recovered from that code alone. Any deliberate rerun belongs in a new
output directory. No automatic generation retry was added.

## Current observation

On this development machine, CLI 0.160.0 reported a ChatGPT sign-in while generation
timed out. Windows had a local user proxy enabled, but the backend process had no
HTTP(S) proxy environment. A direct HTTPS probe timed out; routing through the
existing proxy reached the service. Repeating the same public cache question through
that proxy completed retrieval, generation, citation validation, and the final answer.

The answer identified the Python dictionary lookup and the TypeScript HTTP lookup
with separate citations. Both descriptions match the supplied passages; it did not
claim a demonstrated connection between those independent examples. This is a
single teaching-fixture observation, not a general answer-quality benchmark. The
default browser demonstration remains offline unless its mode is explicitly changed.
An additional [opt-in live browser journey](../README.md#verify-the-live-browser-workflow)
has exercised partial answers, complete function context, and model-reported
insufficient evidence. See the [observations](LIVE_OBSERVATIONS.md) and
[article screenshots](articles/05-live-model.md) for the specific behavior and limits.
