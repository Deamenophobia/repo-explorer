import type { SourceAnalysis } from '../api'

const unavailable = {
  unsupported_language: 'This analyzer does not support the file’s language.',
  parse_error: 'The indexed file could not be parsed. Definition names are unavailable.',
  source_unavailable: 'The full indexed source was unavailable for analysis.',
  source_mismatch: 'The excerpt could not be matched uniquely to its indexed source.',
}

export function SourceContext({ analysis }: { analysis?: SourceAnalysis | null }) {
  if (!analysis) return null
  return (
    <section className="source-analysis" aria-label="Code context">
      <strong>Code context</strong>
      {analysis.status !== 'analyzed' ? (
        <p>{unavailable[analysis.status]}</p>
      ) : analysis.symbols.length ? (
        <>
          <p>Definitions overlapping this excerpt. Ranges refer to the indexed file.</p>
          <ul>
            {analysis.symbols.map(symbol => (
              <li key={symbol.id}>
                <code>{symbol.qualified_name}</code>
                <span>
                  {symbol.is_async ? 'Async ' : ''}{symbol.kind} · Lines {symbol.start_line}–{symbol.end_line}
                </span>
                <span>{symbol.coverage === 'full' ? 'Full definition span' : 'Partial definition span'}</span>
              </li>
            ))}
          </ul>
          {analysis.omitted_symbols > 0 && (
            <p>{analysis.omitted_symbols} more definitions omitted by the configured limit.</p>
          )}
        </>
      ) : (
        <p>No class or function definition overlaps this excerpt.</p>
      )}
      <small>Syntax from the indexed snapshot · {analysis.method}. This does not resolve runtime calls.</small>
    </section>
  )
}
