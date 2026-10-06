# ADR 001: a modular local application with one workflow owner

Status: accepted for the first local version. Date: 2026-10-06.

## Context

Repo Explorer begins with repository knowledge and review, which needs retrieval
provenance and durable human decisions. A separate code-writing orchestration
engine would introduce a second scheduler and obscure the RAG concepts we want to teach.

## Alternatives examined

| Candidate | Useful fit | Decision |
| --- | --- | --- |
| FastAPI full-stack template | Maintained FastAPI/React/Vite reference, API and UI boundaries | Adopt the stack and modular pattern; do not copy account/deployment scope |
| LangChain retrieval building blocks | Documents, splitters, model adapters, vector stores | Use directly |
| LangGraph StateGraph | Branching, interrupts, persisted run state | Sole workflow owner |
| A simple sequential function | Smallest answer-only implementation | Inadequate for the intended persisted human-review teaching example |

This is a small ports-and-adapters design inside one backend process, not a claim
that one architecture is an industry standard for every AI application. We reuse
established libraries where their capabilities match a requirement.

## Consequences

The generation protocol permits offline extraction and live generation without
changing graph nodes. The vector store uses a reproducible lexical adapter by
default and optional remote learned embeddings. SQLite is sufficient for the
local workflow demonstration; multi-user scaling and authorization need separate
design work. The current service serializes mutations and intentionally uses one
backend process. The React trace displays actual completed node names, not a
simulated animation or streaming promise.

The backend starts independently of React and Node.js. The bundled frontend is
one HTTP client; custom interfaces and command-line integrations use the same
[API contract](../API.md). HTTP clients submit inputs and decisions and render
backend results. They do not own workflow transitions or provider credentials.
Separate browser frontends may use a proxy or configured CORS origins; this does
not change the local, single-user deployment boundary.

## Sources consulted

- [FastAPI full-stack template](https://github.com/fastapi/full-stack-fastapi-template)
- [FastAPI application structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangChain retrieval](https://docs.langchain.com/oss/python/deepagents/retrieval)
