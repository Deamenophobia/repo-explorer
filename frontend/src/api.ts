export interface SourceAnalysis {
  method: string
  status: 'analyzed' | 'unsupported_language' | 'parse_error' | 'source_unavailable' | 'source_mismatch'
  parser_version: string | null
  omitted_symbols: number
  relationships?: { kind: 'contains'; parent_id: string | null; child_id: string }[] | null
  symbols: {
    id: string
    qualified_name: string
    kind: 'class' | 'function' | 'method'
    is_async: boolean
    start_line: number
    end_line: number
    coverage: 'full' | 'partial'
  }[]
}
export interface Citation {
  id: string
  path: string
  start_line: number
  end_line: number
  excerpt: string
  score: number
  revision: string
  source_analysis?: SourceAnalysis | null
}
export interface Run {
  id: string
  question: string
  intent: string
  status: string
  answer: string
  answerability?: 'complete' | 'partial' | 'insufficient_evidence' | 'not_assessed'
  limitations?: string[]
  citations: Citation[]
  steps: string[]
  mode: string
  retrieval: string
  snapshot: string
  context_expansion?: ContextExpansion | null
  evidence_map?: EvidenceMap | null
}
export interface MapNode {
  id: string
  kind: 'file' | 'class' | 'function' | 'method'
  label: string
  path: string
  revision: string
  start_line: number | null
  end_line: number | null
  sources: { source_id: string; coverage: 'full' | 'partial' | null }[]
}
export interface EvidenceMap {
  scope: 'cited_passages'
  nodes: MapNode[]
  edges: { kind: 'contains'; parent_id: string; child_id: string; method: string; source_ids: string[] }[]
  issues: { source_id: string; reason: string; detail: string }[]
  node_limit: number
  omitted_nodes: number
}
export interface ContextExpansion {
  method: string
  reason: string
  stop_reason: string
  added_chars: number
  max_added_chars: number
  window_lines: number | null
  changes: {
    source_id: string
    path: string
    original_start_line: number
    original_end_line: number
    start_line: number
    end_line: number
    status: string
    added_chars: number
  }[]
}
export interface Corpus {
  workspace_name: string
  repository_name: string
  corpus_description: string
  suggestions: string[]
  files: { path: string; revision: string }[]
  chunks: number
  snapshot: string
  retrieval: string
  mode: string
}

export interface SettingsDocument {
  values: Record<string, unknown>
  adapters: Record<string, string[]>
  schema: {
    properties: Record<
      string,
      {
        title: string
        type?: string
        enum?: string[]
        anyOf?: unknown[]
        minimum?: number
        maximum?: number
        minLength?: number
        maxLength?: number
      }
    >
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((item: { msg: string }) => item.msg).join(' ')
          : 'The request could not be completed.',
    )
  }
  return response.json()
}

export const api = {
  settings: () => request<SettingsDocument>('/settings'),
  saveSettings: (values: Record<string, unknown>) =>
    request<SettingsDocument>('/settings', {
      method: 'PUT',
      body: JSON.stringify(values),
    }),
  corpus: () => request<Corpus>('/corpus'),
  run: (id: string) => request<Run>(`/runs/${encodeURIComponent(id)}`),
  ask: (question: string, intent: string) =>
    request<Run>('/runs', {
      method: 'POST',
      body: JSON.stringify({ question, intent }),
    }),
  decide: (id: string, approved: boolean) =>
    request<Run>(`/runs/${id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    }),
}
