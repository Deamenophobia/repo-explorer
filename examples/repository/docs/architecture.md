# Application architecture

Repo Explorer separates transport, application workflow, retrieval, and generation.
FastAPI validates HTTP requests. RunService creates and resumes runs. LangGraph
owns the state machine and SQLite checkpoints. KnowledgeIndex supplies evidence
through LangChain documents, splitters, and the in-memory vector store.

AnswerGenerator is a Python protocol. ExtractiveGenerator supplies transparent
offline evidence excerpts. ChatAnswerGenerator composes a LangChain prompt with a
configured chat model and a structured answer schema. The React frontend uses the
same API in both modes and shows the current mode beside each answer.

The application is a local single-user workbench, bound to loopback. It has no
authentication, hosted deployment, autonomous coding worker, or background indexer.
