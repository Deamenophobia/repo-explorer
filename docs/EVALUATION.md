# Reproducible retrieval evaluation

The evaluation runner establishes a baseline before adding investigation complexity.
It evaluates retrieved evidence without calling a model. It does not grade generated
answers, reproduce an IDE search session, or compare against a coding assistant yet.
The separate [live-pipeline runner](LIVE_EVALUATION.md) adds explicit provider execution,
draft/final answer capture, and human source-support records while reusing these
snapshot and annotation formats. Its results are separate from this offline report.

## Run the public example

From the repository root, using the environment installed in the README:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation --suite evaluations/reference.json --repository examples/repository --output .repo-explorer/evaluations/reference
```

The output directory must be new. Reusing an existing directory fails rather than
overwriting a previous experiment. Reports and copied source files stay under the
ignored `.repo-explorer` directory in this example. Keep private suites and reports
there too; do not commit them into the public fixture or article assets.

The public suite uses independently authored documentation. Its small, curated
corpus demonstrates the mechanics; it does not establish performance on real code
or large repositories. It includes a no-vocabulary control and a deployment question
that shares relevant-looking words with the corpus but has no supplied answer.

## What is compared

- **TF-IDF (`tfidf`):** `KnowledgeIndex.search` with standard word tokenization,
  using the configured similarity threshold and retrieval limit.
- **Identifier-aware TF-IDF (`tfidf_identifiers`):** the same application search
  path with `lexical_tokenization=code_identifiers`. Chunks, context limit,
  stop words, n-grams, and cosine threshold remain the same as standard TF-IDF.
- **Identifier TF-IDF plus context (`tfidf_identifiers_context`):** the same seed
  retrieval followed by the built-in one-pass line-window expander. Its additional
  context allowance is recorded, so compare coverage gains with `context_chars`,
  not as an equal-context-budget experiment. Scores remain those of the seeds.
- **Keyword overlap:** passages ranked by the fraction of distinct query tokens
  that occur in each passage. It uses the same chunks, stop-word setting, and
  retrieval limit, with stable path/line tie-breaking. It keeps positive matches;
  the TF-IDF cosine threshold has no equivalent meaning for this score.

All methods receive only the question and snapshot text. Gold evidence ranges and
reference notes are used afterward to evaluate the results. The evaluator explicitly
selects local adapters and defaults, ignoring the application's provider environment,
saved workspace configuration, and installed plugin entry points. It makes no model
or embedding-provider requests.

## Try the identifier example

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation --suite evaluations/identifiers.json --repository examples/identifier-repository --output .repo-explorer/evaluations/identifier-example
```

This suite supplies three small, independently authored code files. A Python
`cache_lookup` method and a TypeScript `cacheLookup` function share word components.
An `HTTPTransport` class exercises acronym splitting and acts as a distractor for
cache questions. These are independent examples; the fixture supplies no route
connecting its TypeScript client to the Python store.

With the default settings, standard TF-IDF returns no passages for “Find the cache
lookup implementations.” Identifier tokenization retrieves both implementations
without changing their source text. Both TF-IDF modes still return no passages for
the paraphrase “How are remembered objects recovered?” Identifier tokenization also
returns cache passages for a cloud-region question whose answer is absent. More
retrieval is therefore not sufficient evidence of a better answer.

This fixture was designed after the implementation experiment to explain the
behavior and guard against regressions. It is not a held-out benchmark. The existing
documentation suite remains a separate check on ordinary prose. On the original
private investigation, identifier tokenization retrieves a previously missed
state-changing function, but still misses the paraphrase and complete command-write
evidence. Keep private sources and reports in ignored local artifacts.

The application exposes this option in **Settings → Retrieval → TF-IDF tokenization**.
It remains opt-in: the default `standard` behavior is unchanged. The evaluator always
compares both modes, independently of that application setting. Matching names does
not resolve symbols or establish a relationship between two functions.

## Pin sources and annotate evidence

The [bounded context guide](CONTEXT.md#reproduce-the-boundary-failure) supplies
another authored case: a matched function is cut off before its write/replace
sequence. `evaluations/context.json` and `evaluations/context-config.json` reproduce
the seed-versus-expanded comparison, including unanswerable and no-seed controls.
The expansion strategy never receives the gold evidence ranges.

`evaluations/reference.json` is a complete suite example. Each suite contains:

| Field | Meaning |
| --- | --- |
| `version`, `name`, `scope` | Schema version and the limits of the experiment |
| `snapshot.kind` | `files` for a supplied directory, or `git` for committed objects |
| `snapshot.revision` | Full commit hash for a Git snapshot; omitted/null for files |
| `snapshot.files` | Explicit relative paths and SHA-256 identities |
| `cases[].question` | The only case text supplied to retrieval |
| `cases[].evidence` | Required source paths, inclusive line ranges, IDs, and quote anchors |
| `cases[].unanswerable` | Whether the selected corpus lacks the required answer evidence |
| `cases[].reference_notes` | Source-anchored explanation and qualifications, withheld from retrieval |

Hashes identify UTF-8 text after normalizing CRLF and CR to LF. This makes Windows
and Unix checkouts comparable. Preserve all other characters when computing hashes.
The runner verifies every file and quote anchor before creating an output directory.
Stale annotations or modified sources fail explicitly.

For `git`, source text is read directly from regular file blobs at the pinned commit.
The working tree and branch are not changed, and uncommitted edits are not included.
The runner does not execute repository code or Git checkout filters. It rejects
symlinks, submodules, hidden/traversing paths, binary text, and oversized files.
The initial resource bounds are 500 selected files, 200 KB per file, and the
application's default 2,000-chunk limit. This is a bounded experiment runner.

Curating files using knowledge of the answer makes a task easier. Record that
selection in `scope`; do not describe results on a hand-selected subset as a
whole-repository benchmark. Broader distractor sets and held-out questions are
needed before making general retrieval-quality claims.

## Inspect and reproduce the result

Each experiment contains:

- `corpus/`: the exact normalized source snapshot used for indexing.
- `suite.json`: the original annotations, file identities, and optional Git revision.
- `replay-suite.json`: equivalent annotations configured to read the copied files.
- `config.json`: the common retrieval settings used by the comparison.
- `report.json`: retrieved excerpts, rankings, evidence coverage, timings, snapshot
  identity, effective settings per method, an implementation fingerprint, and
  relevant runtime/package versions.
- `report.md`: a readable account of retrieved passages and missing evidence.

Report format version 3 includes `tfidf_identifiers_context`, `context_chars`, and
the optional per-method `context_expansion` trace in addition to `method_configs`
and `index_seconds` by TF-IDF method. Suite format version 1 is unchanged.
Each TF-IDF index is prepared independently from the same saved corpus; the
keyword baseline shares its chunks and does not build a separate vector index.

Replay without access to the original Git checkout:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation --suite .repo-explorer/evaluations/reference/replay-suite.json --repository .repo-explorer/evaluations/reference/corpus --config .repo-explorer/evaluations/reference/config.json --output .repo-explorer/evaluations/reference-replay
```

The replay has the same source identity. Its source mode is now `files`; the original
commit remains recorded in the original `suite.json`. Retrieval determinism assumes
the same configuration and dependency versions; timings vary across runs.

For a sensitivity experiment, supply a JSON file with `--config`. Supported settings
are `chunk_size`, `chunk_overlap`, `retrieval_limit`, `minimum_score`,
`lexical_stop_words`, `lexical_ngram_max`, `context_window_lines`, and
`context_max_added_chars`. The last two affect only the expanded-context method.
For example:

```json
{"retrieval_limit": 12}
```

This changes the context budget, not the retrieval algorithm. Keep the original run
and identify the changed setting when comparing results. Avoid tuning on the same
questions later used to claim general improvements.

## Interpret results carefully

An evidence unit is covered only when the retrieved excerpts collectively include
the non-whitespace source text across its annotated line range. Overlapping line
numbers alone are insufficient: a chunk can stop in the middle of a line. Coverage
is averaged over annotated units, not weighted by file size. The report lists missing
units and lines so a reviewer can inspect the actual failure.

This is text coverage, not a judgment that a model understood the code. An incomplete
or overly broad gold annotation can mislead the metric; review annotations as well as
retrieval. A one-pass budget smaller than the number of required files cannot cover
the complete reference path, even with perfect ranking.

The initial annotations were prepared with source inspection during development;
they have not received independent human review. Treat them as a starting reference
set, not an authoritative benchmark. Review the required spans and qualifications
before using them to compare systems.

For unanswerable cases, the report flags returned context. Related passages can still
be useful to a model that correctly abstains, so this flag is not an answer-quality
failure by itself. It does expose why a nonempty retrieval result cannot establish
that the question is answerable. The current demo workflow does not perform that
semantic sufficiency check.

The separate [live observations](LIVE_OBSERVATIONS.md) record actual model behavior
and assistant source inspections. An independent human review and an assistant
baseline remain outstanding. No generation-quality result should be inferred from
this offline retrieval report. Article prose should
explain observed behavior and limitations rather than list automated test totals.
