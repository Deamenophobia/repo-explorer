# Review workflow and checkpoints

LangGraph runs the repository assistant as explicit state transitions:
retrieve evidence, compose a draft, validate source references, then finish or
pause for human review. If retrieval finds no qualifying evidence, the workflow
abstains without invoking the generator.

## Durable review
A SQLite checkpointer persists the workflow under a unique thread identifier.
The review node calls interrupt with the draft. The browser displays a pending
decision and can be closed without losing that checkpoint. Resuming with the same
thread identifier and Command(resume=...) supplies the human decision.

Approval and rejection are separate terminal outcomes. A second decision is
rejected because the run no longer has a pending interrupt. Code before an
interrupt can run again on resume, so the review node performs no external writes.
