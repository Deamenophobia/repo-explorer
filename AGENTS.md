# Working on Repo Explorer

Read `CONTRIBUTING.md` for naming conventions and architectural boundaries. Use
`README.md` for the overview, `docs/GETTING_STARTED.md` for setup,
`docs/SCOPE.md` for scope, and `docs/DEVELOPMENT.md` for verification commands.

## Decide what is worth building

- Before a substantial feature, identify the user problem, the observed gap, and
  a concrete example that would demonstrate improvement. Check existing framework
  capabilities before creating custom infrastructure.
- Keep the core focus on repository RAG, LangChain integration, and LangGraph
  orchestration. Add visualizations only when they clarify evidence and relationships.
- Deliver a working, bounded change. Distinguish what is demonstrated, what remains
  uncertain, and what is planned; do not equate valid citations with factual support.

## Preserve the architecture

- The backend owns ingestion, model calls, workflow state, validation, and persistence.
  The bundled React frontend is an optional API client; custom clients must remain viable.
- Keep providers, models, retrieval settings, and source selection configurable.
  Use the existing adapter registries rather than provider-specific branches in the UI.
- Keep credentials, executable paths, and machine-specific proxies in server startup
  settings. Public workspace configuration must not expose them.
- Keep the Codex generation adapter's development hooks and tools disabled. Its input
  is the supplied repository evidence, not this development conversation or its tools.

## Verify relevant behavior

- Use the repository's pinned tools and focused checks first. Add regression coverage
  for a demonstrated failure, especially API contracts and checkpoint behavior.
- Python changes: run Ruff and the relevant backend tests. Frontend changes: type-check
  and build; run browser journeys when user behavior or API integration changes.
- Changes to hooks: verify allowed and rejected commits in a temporary repository,
  including partially staged files. Preserve the user's real index and working files.
- For article changes, verify local links and rebuild/render `docs/site` when article
  content or assets change. Avoid unrelated formatting of hash-pinned source fixtures.
- E2E runs own their configured ports. Stop and restore the tracked local preview when
  necessary. Live-model evaluations are explicit experiments, never commit-hook work.

## Keep publication honest

- Private source material, credentials, local configuration, and runtime reports stay
  outside public fixtures, articles, and screenshots. Use the authored teaching corpus.
- Explain mechanisms and observed behavior in the articles, with focused diagrams and
  real screenshots. Do not publish test totals as evidence of product usefulness.
- Explain AI engineering concepts through specific project decisions. Use plain prose;
  avoid promotional filler and rhetorical "X, not Y" / "not just X, but Y" constructions.
  Preserve technical limits and uncertainty while stating them directly. See the
  editorial guidance in `docs/articles/PUBLISHING.md`.
- Label demo, live, and planned behavior accurately. Identify assistant assessments
  separately from independent human review. Update conflicting README claims when
  new evidence changes the project's status.
- Keep changes local until publication is requested for a specified destination.
  Hooks must not publish, deploy, or make model calls.
