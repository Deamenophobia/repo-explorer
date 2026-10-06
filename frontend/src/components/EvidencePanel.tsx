import { FileText, ArrowUpRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Citation, ContextExpansion, Corpus } from '../api'
import { SourceContext } from './SourceContext'

export function EvidencePanel({
  citations,
  corpus,
  expansion,
  hasRun = false,
  focusRequest,
}: {
  citations: Citation[]
  corpus: Corpus | null
  expansion?: ContextExpansion | null
  hasRun?: boolean
  focusRequest?: { sourceId: string } | null
}) {
  const cards = useRef(new Map<string, HTMLDetailsElement>())
  useEffect(() => {
    if (!focusRequest) return
    const card = cards.current.get(focusRequest.sourceId)
    if (card) {
      card.open = true
      card.querySelector('summary')?.focus()
      card.scrollIntoView({ block: 'nearest' })
    }
  }, [focusRequest])
  return (
    <aside className="evidence-panel">
      <div className="section-label">
        SOURCE EXPLORER <FileText size={16} />
      </div>
      <h2>Follow the evidence.</h2>
      <p className="muted">Inspect the passages behind the answer.</p>
      {citations.length ? (
        citations.map((citation) => (
          <details className="source-card" key={citation.id} ref={element => {
            if (element) cards.current.set(citation.id, element)
            else cards.current.delete(citation.id)
          }}>
            <summary>
              <span className="source-id">{citation.id}</span>
              <span>
                {citation.path}
                <small>
                  Lines {citation.start_line}–{citation.end_line}
                </small>
              </span>
              <ArrowUpRight size={16} />
            </summary>
            <SourceContext analysis={citation.source_analysis} />
            <pre>{citation.excerpt}</pre>
            <div className="source-meta">
              Revision {citation.revision} · Similarity {citation.score.toFixed(2)}
              {expansion?.changes.some(
                (change) => change.source_id === citation.id && change.status === 'expanded',
              ) && <span> · Expanded context; similarity is for the original match.</span>}
            </div>
          </details>
        ))
      ) : (
        <div className="source-empty">
          <FileText size={30} />
          <p>
            {hasRun ? 'This response has no cited passages.' : 'Ask a question to see the original source passages.'}
          </p>
        </div>
      )}
      <div className="corpus-list">
        <div className="section-label">INDEXED SNAPSHOT</div>
        {corpus?.files.map((file) => (
          <div key={file.path}>
            <FileText size={14} />
            {file.path}
          </div>
        ))}
        <p className="mono">{corpus?.snapshot ?? 'Connecting…'}</p>
      </div>
      <div className="note">
        A source reference is traceability, not a guarantee of factual correctness.
      </div>
    </aside>
  )
}
