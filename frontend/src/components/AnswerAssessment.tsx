import type { Run } from '../api'

const labels = {
  complete: 'Complete answer',
  partial: 'Partial answer',
  insufficient_evidence: 'Insufficient evidence',
  not_assessed: 'Not assessed',
}

export function AnswerAssessment({ run }: { run: Run }) {
  const assessment = run.answerability ?? 'not_assessed'
  const noContext = run.steps.includes('abstain')
  const explanation =
    run.status === 'invalid_citations'
      ? 'The response was rejected because its source references were invalid.'
      : noContext
        ? 'Retrieval found no matching passages. The model was not called.'
        : assessment === 'not_assessed'
          ? run.mode === 'demo'
            ? 'The extractive demo does not assess answer completeness.'
            : 'This response has no recorded answerability assessment.'
          : 'Model assessment of the supplied evidence. Verify claims against the sources.'

  return (
    <section className={`answer-assessment ${assessment}`} aria-label="Answer assessment">
      <strong>{labels[assessment]}</strong>
      <p>{explanation}</p>
      {!!run.limitations?.length && (
        <>
          <span>Missing information</span>
          <ul>
            {run.limitations.map((limitation, index) => (
              <li key={`${index}-${limitation}`}>{limitation}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
