# Development conventions

Coding agents should also follow `AGENTS.md`. Install the optional Git checks using
the [README setup](README.md#agent-guidance-and-git-hooks). Hook definitions are shared
in `.pre-commit-config.yaml`; installation is local to each clone. They check staged
changes without running the application, browser tests, or live-model evaluations.

Keep changes focused on observable user behavior. A new retrieval technique must
have a concrete query it improves and a failure mode it does not solve.

Python modules and functions use `snake_case`; classes and protocols use
`PascalCase`; constants use `UPPER_SNAKE_CASE`. Python uses Ruff formatting and
type annotations on public boundaries. React components and their files use
`PascalCase`; hooks and helpers use `camelCase`. API JSON uses `snake_case` on both
sides so transport fields remain recognizable. CSS classes use `kebab-case` and
describe a component or state rather than a visual location.

The API validates transport data. RunService coordinates application operations.
LangGraph owns state transitions. KnowledgeIndex owns ingestion and retrieval.
AnswerGenerator defines a replaceable generation contract. Do not put retrieval
logic in HTTP routes, model calls in React components, or external side effects
before a resumable interrupt. Prefer functions for stateless behavior; use classes
for dependencies and state with an actual lifecycle.

Do not copy private repository material into the public teaching fixture or blog
screenshots. The fixture is intentionally authored for publication. Keep article
claims tied to the shipped version, and distinguish demo, implemented-but-unverified,
and future functionality. Do not put test totals or pass-rate marketing in articles.

Use the checks in README for changes to behavior. Add regression coverage for a
new failure mode; avoid tests that merely repeat implementation details.
`.gitlab-ci.yml` runs backend, browser, build, and article checks. CI uses the
offline fixtures and makes no model calls. Deployment is a separate release step.
