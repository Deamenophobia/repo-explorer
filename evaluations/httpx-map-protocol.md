# HTTPX evidence-map inspection protocol

This is a developer inspection of a second public package. HTTPX was selected
because its synchronous and asynchronous clients, response model, and transport
adapters span several modules. It has not previously been used to adjust Repo
Explorer's retrieval settings. The inspecting assistant may already know HTTPX;
this exercise cannot establish how an unfamiliar human user performs.

## Inputs fixed before pipeline execution

- Repository: `encode/httpx`, tag `0.28.1`, commit
  `26d48e0634e6ee9cdc0533996db289ce4b430177`.
- Corpus: every Python file under `httpx/`, including its transport adapters.
  Tests, documentation, applications using the package, and HTTPcore source are
  outside the corpus. Git blobs are read without executing repository code.
- Questions and source-inspected reference spans are in `httpx.json`. The spans
  are written before inspecting retrieval or model results.
- Retrieval: local `BAAI/bge-small-en-v1.5` embeddings, chunks of 1,100 characters
  with 150-character overlap, two passages, no score cutoff, no context expansion.
- Analysis: `python_ast`, eight definitions per passage, forty map blocks.
- Generation: the existing LangChain/LangGraph pipeline, one request per question,
  no retries; local configuration records the selected provider and model.

The questions cover method ownership and behavior, a request path through multiple
functions, and missing deployment context. Any later change to those questions or
settings is a new experiment and must preserve the original results.

## Compare three information views

1. **Source search and inspection.** Search the pinned source for the named
   functions, inspect their enclosing classes, and follow explicit call sites.
   Record the commands and line references used. This supplies the reference
   reading against which the pipeline's evidence can be examined.
2. **Retrieved passages.** Inspect exactly what reached generation, including
   missing class headers, split method bodies, and evidence from similar names.
   Include the existing source cards' definition metadata: they already show the
   class and method names. Attribute those facts to analysis; assess the map as an
   additional presentation and navigation surface.
3. **Saved map and answer.** Inspect the actual cited subset, explicit containment,
   per-passage coverage, source links, omissions, and generated claims.

Check whether the map makes an owner visible when its header is outside the
excerpt, whether it preserves partial coverage, and whether it leaves unsupported
call relationships unconnected. A map containing relevant-looking classes still
needs source evidence for the behavior being explained.

## Interpretation

Report concrete observations per question, including failures. Keep assistant
source inspection separate from the pending independent human review. Full-source
reading and a two-passage model context have different information budgets, so
this exercise compares the available information. A controlled tool ranking would
require matched conditions.

Do not infer a reduction in investigation time or a general advantage over an
IDE or coding assistant. A later usability study would need independent readers,
counterbalanced tasks, matched repository access, and recorded task outcomes.
Broader language support, frontend/backend contracts, and large-repository
scalability remain separate questions.

## Follow-ups fixed after the initial inspection

Preserve the original results. The diagnostic retry selects `sync-request-path`
with the same workspace configuration and prompt after improving failure codes.
Its new report must compare the exact context, policy, question, and snapshot with
the original failed case. A successful retry cannot recover the cause of the
historical failure.

A separate offline passage-limit check uses the same snapshot, question, embedding
model, chunking, score cutoff, and analyzer, with no context expansion. Before
inspecting results, fix limits at two, four, and eight. Build the index once,
retrieve the top eight, and inspect those prefixes. Score the existing withheld
reference spans and record context size plus exact passages. Make no chat calls,
change no defaults, and infer no answer-quality improvement from span coverage.
This checks whether increasing the existing limit deserves consideration before
designing a follow-up retrieval workflow. These are development cases, so any
later choice needs evaluation on additional independently annotated questions.
