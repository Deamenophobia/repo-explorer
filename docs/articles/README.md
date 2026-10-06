# AI engineering with Repo Explorer

A five-part technical series explaining the work of an AI engineer through a
repository assistant. It follows the decisions about source data, retrieval,
model integration, orchestration, API design, and evaluation in Repo Explorer
0.1.0. All five chapters are written and available in the local preview. They
remain unpublished editorial drafts for the author's blog.

1. [Building Repo Explorer: the work of an AI engineer](01-architecture.md)
2. [From source files to useful evidence](02-retrieval.md)
3. [A review that survives closing the browser](03-langgraph.md)
4. [An interface for inspecting an answer](04-interface.md)
5. [Evaluating live answers against their sources](05-live-model.md)

The opening assumes general software-development experience and explains RAG,
LangChain, and LangGraph through their actual responsibilities. Later chapters
follow the same examples into retrieval, saved review state, the interface, and
live responses. Readers can trace the explanations to code, diagrams, and actual
screenshots.

The series covers the current local prototype, including its containment map.
Cross-file relationship analysis, broader evaluation, independent review, and publication are
still open. Future additions should document demonstrated behavior when that work
is complete.

The first four articles use offline demo screenshots. The fifth adds actual
Codex-backed browser captures showing partial answers, context expansion, and
insufficient evidence. The retrieval chapter records a separate local learned-embedding
comparison, including pinned public package code. Remote embeddings and other chat
providers remain unverified paths. All screenshot sources were authored for this
project and contain no private repository data.

The interface and evaluation chapters also follow a separate HTTPX source
inspection. They explain what the containment map adds to existing source cards
and preserve a failed cross-file question. The
[experiment record](../MAP_EVALUATION.md) supplies fixed questions and reproduction
steps. This developer inspection includes no independent human timing comparison.

`series.json` contains the preview introduction, slugs, descriptions, and image captions. `assets/` contains
captured PNGs and editable SVG diagrams. `PUBLISHING.md` maps the bundle to the
existing Payload blog. To read as a small documentation site, run
`node frontend/scripts/build-docs.mjs` from the repository root and open
`docs/site/index.html`.
