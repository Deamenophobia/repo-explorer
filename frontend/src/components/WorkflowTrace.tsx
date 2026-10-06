import { Check, Circle, Pause } from 'lucide-react'
import type { Run } from '../api'

export function WorkflowTrace({ run }: { run: Run | null }) {
  const stages = ['retrieve', 'compose', 'validate', run?.intent === 'review' ? 'review' : 'finish']
  if (run?.steps.includes('abstain')) stages.splice(1, 3, 'abstain')
  else if (run && ['insufficient_evidence', 'invalid_citations'].includes(run.status)) {
    stages.pop()
  }
  if (run?.steps.includes('expand_context')) stages.splice(1, 0, 'expand_context')
  const expansion = run?.context_expansion
  return (
    <section className="trace-card" aria-label="Workflow trace">
      <div className="section-label">
        EXECUTION PATH <span>LangGraph</span>
      </div>
      <ol className="trace">
        {stages.map((stage, i) => {
          const done = run?.steps.includes(stage)
          const paused = stage === 'review' && run?.status === 'awaiting_review'
          return (
            <li key={stage} className={done ? 'done' : paused ? 'paused' : ''}>
              <span className="trace-icon">
                {done ? <Check size={15} /> : paused ? <Pause size={14} /> : <Circle size={12} />}
              </span>
              <span>
                <small>0{i + 1}</small>
                {stage === 'compose'
                  ? 'Compose draft'
                  : stage === 'validate'
                    ? 'Check citations'
                    : stage === 'retrieve'
                      ? 'Retrieve evidence'
                      : stage === 'expand_context'
                        ? 'Expand context'
                      : stage === 'review'
                        ? 'Human review'
                        : stage === 'abstain'
                          ? 'Abstain'
                          : 'Complete'}
              </span>
            </li>
          )
        })}
      </ol>
      <p>
        {run?.status === 'awaiting_review'
          ? 'Checkpoint saved. This review can resume after a restart.'
          : run?.status === 'invalid_citations'
            ? 'Stopped at citation validation. The draft cannot proceed to review.'
            : run?.answerability === 'insufficient_evidence'
              ? 'Stopped with insufficient evidence. No review decision is requested.'
              : 'A small, explicit graph. Every transition has a purpose.'}
      </p>
      {expansion && (
        <details className="context-trace">
          <summary>Context expansion details</summary>
          <p>
            {expansion.added_chars.toLocaleString()} characters added within a{' '}
            {expansion.max_added_chars.toLocaleString()}-character allowance.{' '}
            {expansion.stop_reason === 'budget_limited'
              ? 'Some windows did not fit; their original passages were kept.'
              : 'One expansion pass completed.'}
          </p>
          <ul>
            {expansion.changes.map((change) => (
              <li key={change.source_id}>
                {change.source_id} · {change.path}: {change.original_start_line}–
                {change.original_end_line} → {change.start_line}–{change.end_line} ·{' '}
                {change.status.replaceAll('_', ' ')}
              </li>
            ))}
          </ul>
          <p>Additional context does not establish that the answer is supported.</p>
        </details>
      )}
    </section>
  )
}
