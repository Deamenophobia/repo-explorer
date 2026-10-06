# Definition identity in retrieved evidence

The learned-retrieval comparison found `TTLCache.expire`, but its passage omitted
the owning class header. A nearby implementation had the same method name. Naming
the source file and line range was useful, but readers still had to inspect the
full file to establish which definition they were seeing.

Optional source analysis adds that syntax context to the existing passage. It does
not change its text, embedding, rank, or similarity score. The backend supplies the
metadata to LangChain generation and any API client; React displays it in the source
card. The [evidence map](EVIDENCE_MAP.md) uses saved containment relationships to
group the definitions represented in an answer's cited passages.

## Configure it

Choose **Settings → Evidence context → Source analysis → python_ast** and Apply.
`source_analyzer` defaults to `none`. `source_symbol_limit` defaults to 8, with a
range of 1–100 definitions per passage. Both settings are public workspace choices
and can be saved through the API or `repo-explorer.json`.

Equivalent environment defaults:

```dotenv
REPO_EXPLORER_SOURCE_ANALYZER=python_ast
REPO_EXPLORER_SOURCE_SYMBOL_LIMIT=8
```

The built-in analyzer handles `.py` and `.pyi` files using the running Python
interpreter's [AST parser](https://docs.python.org/3.12/library/ast.html).
To index `.pyi`, also include it in the source `extensions` setting. There is no new
dependency, model call, module import, or execution of the indexed repository.
Language syntax unsupported by the current interpreter is reported as a parse
failure. The parser version is saved with the result.

## What a passage can say

Each citation has an optional `source_analysis` object:

| Field | Meaning |
| --- | --- |
| `method` | Selected analyzer, such as `python_ast` |
| `status` | Whether analysis succeeded, was unsupported, or lacked matching source |
| `parser_version` | Python version used by the built-in parser |
| `symbols` | Definitions whose source spans intersect the excerpt |
| `omitted_symbols` | Additional intersecting definitions excluded by the configured limit |
| `relationships` | Optional explicit containment relationships; null means unavailable |

Each symbol supplies an `id`, lexical `qualified_name`, `kind` (`class`, `method`,
or `function`), `is_async`, definition `start_line` and `end_line`, and `coverage`
(`full` or `partial`). A passage inside a method can intersect both its class and
method. One crossing several definitions lists them separately; there is no claim
that a single symbol owns the entire excerpt.

Names include nested lexical scopes, for example `Outer.method.inner`. Methods
with the same spelling remain distinguishable through their scope and source span.
Repeated declarations of the same qualified name have distinct IDs. IDs incorporate
path, content revision, qualified name, and byte span; they remain stable across
queries and context expansion within that snapshot, not across source revisions.

`coverage=full` means the excerpt includes the complete AST definition span,
including its decorators. It does not mean the answer is complete, a call target is
resolved, or all related code has been retrieved. Comments outside the parser's
definition span are not part of this measure. Partial coverage names the definition
without pretending its omitted implementation is visible.

Definitions are returned in source traversal order, with enclosing definitions
before their children. A small limit may omit a nested method after its class;
`omitted_symbols` makes that limitation explicit. Clients must not treat a truncated
list as the complete set of relationships.

For analyzed Python passages, `relationships` records each returned definition's
`child_id` and its enclosing definition's `parent_id`, with `kind=contains`.
A null parent means module scope. The parser records IDs during traversal, so
repeated declarations with identical names remain distinct. Old analysis results
without this field remain readable and supply no inferred containment edges.

## Keep analysis tied to the snapshot

The analyzer parses the full text captured during indexing. It verifies the passage's
path, revision, declared lines, and exact excerpt before assigning definitions.
Positions use UTF-8 bytes because that is how Python's AST reports columns. A short
fragment on a line is not mistaken for the whole definition on that line.

If an excerpt occurs more than once within its declared range, the built-in adapter
declines to assign names rather than choosing an occurrence. Missing full text from
a custom source adapter similarly produces no guessed identity.

| Status | Behavior |
| --- | --- |
| `analyzed` | Includes intersecting definitions; an empty list means no class/function span overlaps |
| `unsupported_language` | The built-in parser does not handle this extension |
| `parse_error` | The indexed Python text could not be parsed |
| `source_unavailable` | Matching full text for the path/revision was not supplied |
| `source_mismatch` | Excerpt and declared range could not be matched uniquely |

Failures leave the original text available to retrieval and inspection. With analysis
disabled, the field is `null`. Older checkpoints also return `null`; the service
does not retroactively analyze old answers using today's checkout.

Context expansion can cross definition boundaries. `KnowledgeIndex.expand_context`
therefore recalculates metadata for the final excerpt using the same captured text.
Review checkpoints save those results along with the source passages. Reloading,
reconfiguring the workspace, or approving a brief does not replace its evidence.

## Adapter boundary

The registry's `analyzers` group accepts factories with `(settings, corpus)` inputs.
They return a `SourceAnalyzer` implementing `analyze(source) -> SourceAnalysis | None`.
The existing `repo_explorer.plugins` entry point can register another language parser.
The built-ins are `none` and `python_ast`; adapter discovery feeds the frontend's
settings choices without provider-specific UI code.

An analyzer annotates a source record; it does not rewrite its text or retrieve more
files. Keep new language support separate from chunking and ranking experiments so
changes can be assessed independently. The implementation is in
[`analysis.py`](../backend/src/repo_explorer/analysis.py), with orchestration in
[`knowledge.py`](../backend/src/repo_explorer/knowledge.py).

## Demonstrate the boundary

The authored `examples/symbol-repository` has two different `expire` methods. With
200-character chunks, 30-character overlap, identifier tokenization, and one returned
passage, “deadline has arrived” retrieves part of `DeadlineCache.expire` without its
class header. The source card names the class and method while marking both spans
partial. The [retrieval article](articles/02-retrieval.md) shows the actual browser
capture, including the unchanged excerpt.

The pinned Cachetools `ttl-expire` case was also run with FastEmbed retrieval and
actual Codex generation. Its original two excerpts, ranks, and scores were preserved.
The metadata distinguished full `TTLCache.expire` coverage from a partial
`TLRUCache.expire` definition in the neighboring result. The response described the
expiration cutoff and returned pairs correctly. The earlier response without this
metadata was already correct, so this verifies integration and provenance, not a
measured quality gain. The local report is
`.repo-explorer/evaluations/cachetools-symbol-context-v1`; assistant source inspection
is separate from its pending independent review.

This metadata does not resolve imports, inheritance, aliases, decorators' runtime
effects, conditional definitions, dynamic dispatch, cross-file calls, or frontend/
backend API relationships. Unsupported files are visibly unsupported. These limits
must remain explicit in any later visualization.
