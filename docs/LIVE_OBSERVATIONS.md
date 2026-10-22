# What the first live comparisons establish

These observations come from actual Codex-backed runs on the public teaching
fixtures on 6 October 2026 (Singapore time). Codex CLI 0.160.0 used the requested
model `gpt-6-astra`, medium reasoning, and identifier-aware TF-IDF retrieval.
This records the experimental configuration, not a required model or a claim about
the exact model revision served. The source manifests pin every input file by hash.

The Codex assistant inspected each material claim against the supplied passages and
withheld reference notes. These are assistant assessments, not independent human
review. The original human-review records remain pending. The examples were authored
during development; they do not establish general quality on unfamiliar repositories.

## Name matching and missing information

The [identifier suite](../evaluations/identifiers.json) contains independent Python
and TypeScript examples and an HTTP transport class.

| Question | Observed behavior | Implication |
| --- | --- | --- |
| `Find cache_lookup and cacheLookup.` | Identified both functions and described their supplied implementations with separate citations. | Exact identifiers work in this fixture. No connection between the implementations was claimed. |
| `Where is HTTP transport defined?` | Located `HTTPTransport` and named its two methods. | Splitting identifier components recovered the relevant class. |
| `How are remembered objects recovered?` | Retrieved no passages and abstained without calling the model. | The lexical retriever missed the annotated mapping lookup. Generation cannot recover evidence it never receives. |
| `Which cloud region hosts the cache lookup service?` | Retrieved related code but explicitly said the region could not be determined. | A relevant passage does not necessarily contain an answer. |

The region response cited the local mapping and relative-URL client to explain the
evidence boundary. It did not invent a deployment region or assert that the whole
repository lacked deployment configuration. However, the then-current graph returned
`completed` and the evaluator recorded `answered`: those labels identify a finished
response with valid citations, not a substantive answer to the question.

## Same question, more complete function context

The [context suite](../evaluations/context.json) asks about `publish_record`. Both
runs used the same snapshot, question, model, prompt, and retrieval settings:
`chunk_size=200`, `chunk_overlap=30`, and `retrieval_limit=1`. The comparison changed
only `context_expander`, from `none` to `line_window`, with an eight-line window
and a 4,000-character allowance.

The seed contained lines 5–7: a signature, docstring, and JSON serialization. The
model described those operations and explicitly said the excerpt did not show how
the destination was written or errors handled. This was a qualified partial
explanation, not a fabricated implementation.

Expansion supplied lines 1–10, including the missing operations. The resulting
answer described serializing with sorted keys, writing UTF-8 to a `.pending` path,
and replacing the destination. It also identified the absence of explicit error
handling or cleanup. These claims match the supplied function. The answer did not
claim crash durability or guarantees across every filesystem.

The context grew from 184 to 359 characters. This is an example of spending more
context to explain missing logic, not a comparison at equal prompt size. With one
response per configuration, model variation is not controlled. A larger initial
chunk might also retrieve the complete function; this comparison does not establish
that expansion is universally preferable.

As a control, the expanded function was also supplied for a production-region
question. The model still said that the source could not determine the region.
More source text improved the function explanation but supplied no deployment facts.

## The contract change prompted by these observations

The runs above used the earlier response contract. The current implementation adds
explicit `answerability` and `limitations` fields, with separate complete, partial,
and insufficient-evidence outcomes. It preserves citation validation and the model's
qualifications. The classification remains a claim to inspect, not proof of truth.
Old saved runs are left unassessed rather than silently reclassified. See the
[API contract](API.md#answer-coverage-is-separate-from-approval) for the current rules.

The later opt-in browser walkthrough used the same Codex provider and public
`publish_record` source. It asked for the full implementation, including the
destination write. With only lines 5–7, the response reported `partial` and named
the missing write and error-handling information. Approving the brief preserved
that assessment. Enabling context expansion supplied lines 1–10; the next answer
reported `complete` and explained serialization, the UTF-8 staging-file write, and
replacement of the destination. Its substantive claims match the supplied source.

For the production-region question, the response reported `insufficient_evidence`
and identified the missing deployment configuration. It stopped before review,
exposed no approval control, and rejected a direct decision request. Reloading
preserved each response and its qualifications. These source-support judgments
are assistant inspections; the UI's approval exercised workflow behavior and was
not an independent human quality assessment.

The walkthrough's setup is in [the development guide](DEVELOPMENT.md#verify-the-live-browser-workflow),
and its actual screenshots appear in [the live-model article](articles/05-live-model.md).
These later checks do not rewrite the earlier experiment reports.

The paraphrase miss prompted a subsequent [local learned-retrieval comparison](SEMANTIC_RETRIEVAL.md).
It keeps the source snapshot, generation model, and questions fixed, then inspects
retrieved evidence before judging the explanation. Those results are separate from
the earlier generation/context experiments recorded above.

## Reproduce and inspect

Follow [live evaluation setup](LIVE_EVALUATION.md) and copy
[`codex.example.json`](../evaluations/codex.example.json) to an ignored local config.
Choose your available model. The identifier example uses the existing workspace
defaults; select `exact-identifiers`, `acronym-components`, `paraphrase`, and
`missing-deployment` through `case_ids`. For the context comparison, apply the settings
above and select `function-tail`; include `missing-deployment` with expansion as the
negative control. Use a new output directory for every execution.

The original local artifacts are named `identifiers-live-v1`,
`context-seed-live-v1`, and `context-expanded-live-v1` under
`.repo-explorer/evaluations/`. Each contains the exact input configuration, copied
sources, pre-validation draft, final workflow state, and provider metadata.
`assistant-review.json` records the assistant's claim assessments bound to the report
hash; `review.json` remains available for human review. Runtime artifacts and the
machine's proxy configuration remain ignored by Git.
