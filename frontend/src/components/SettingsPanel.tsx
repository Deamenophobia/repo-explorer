import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api, type SettingsDocument } from '../api'
import './settings.css'

const groups: Record<string, string[]> = {
  Workspace: ['workspace_name', 'repository_name', 'corpus_description', 'suggestions'],
  Generation: [
    'mode',
    'generator',
    'chat_provider',
    'model',
    'base_url',
    'chat_api_key_env',
    'request_timeout',
    'max_retries',
    'codex_reasoning_effort',
    'demo_excerpt_limit',
  ],
  'Source and chunking': [
    'source_provider',
    'corpus_dir',
    'policy_file',
    'extensions',
    'excluded_dirs',
    'max_file_bytes',
    'max_chunks',
    'chunk_size',
    'chunk_overlap',
  ],
  Retrieval: [
    'embedding_provider',
    'embedding_model',
    'embedding_base_url',
    'embedding_api_key_env',
    'vector_store',
    'retrieval_limit',
    'minimum_score',
    'lexical_tokenization',
    'lexical_stop_words',
    'lexical_ngram_max',
  ],
  'Evidence context': [
    'context_expander', 'context_window_lines', 'context_max_added_chars',
    'source_analyzer', 'source_symbol_limit', 'evidence_map_node_limit',
  ],
}
const adapterKinds: Record<string, string> = {
  generator: 'generators',
  chat_provider: 'chat',
  embedding_provider: 'embeddings',
  source_provider: 'sources',
  vector_store: 'stores',
  context_expander: 'expanders',
  source_analyzer: 'analyzers',
}
const labels: Record<string, string> = {
  model: 'Chat model',
  base_url: 'Chat endpoint (optional)',
  corpus_dir: 'Repository directory',
  chat_api_key_env: 'Chat credential environment variable',
  embedding_api_key_env: 'Embedding credential environment variable',
  embedding_base_url: 'Embedding endpoint (optional)',
  minimum_score: 'Minimum similarity',
  lexical_tokenization: 'TF-IDF tokenization',
  context_expander: 'Context expansion',
  context_window_lines: 'Surrounding lines',
  context_max_added_chars: 'Maximum added characters',
  source_analyzer: 'Source analysis',
  source_symbol_limit: 'Definitions per passage',
  evidence_map_node_limit: 'Maximum map blocks',
  codex_reasoning_effort: 'Codex reasoning effort',
}

export function SettingsPanel({
  onClose,
  onApplied,
}: {
  onClose: () => void
  onApplied: () => Promise<void>
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [document, setDocument] = useState<SettingsDocument | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pluginJson, setPluginJson] = useState('{}')
  useEffect(() => {
    dialog.current?.showModal()
    api
      .settings()
      .then((result) => {
        setDocument(result)
        setValues(result.values)
        setPluginJson(JSON.stringify(result.values.plugin_options, null, 2))
      })
      .catch((error) => setError(error.message))
  }, [])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.saveSettings({ ...values, plugin_options: JSON.parse(pluginJson) })
      await onApplied()
      onClose()
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <dialog
      ref={dialog}
      className="settings-dialog"
      aria-labelledby="settings-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!saving) onClose()
      }}
    >
      <header>
        <div>
          <div className="eyebrow">YOUR WORKSPACE, YOUR CHOICES</div>
          <h2 id="settings-title">Workspace settings</h2>
        </div>
        <button
          className="icon-button"
          aria-label="Close settings"
          disabled={saving}
          onClick={onClose}
        >
          <X size={22} />
        </button>
      </header>
      <p className="settings-intro">
        Choose your sources, models, and retrieval behavior. Applying settings rebuilds the index
        and saves your choices for the next session. Existing review decisions and evidence remain
        available.
      </p>
      <form onSubmit={save}>
        {document ? (
          Object.entries(groups).map(([group, keys], index) => (
            <details className="settings-group" key={group} open={index === 0}>
              <summary>{group}</summary>
              <div className="settings-fields">
                {keys.map((key) => {
                  if (key === 'codex_reasoning_effort' && values.chat_provider !== 'codex') return null
                  const schema = document.schema.properties[key]
                  const options = adapterKinds[key]
                    ? document.adapters[adapterKinds[key]]
                    : schema.enum
                  const value = values[key]
                  const title = labels[key] ?? schema.title
                  const set = (value: unknown) =>
                    setValues((previous) => ({ ...previous, [key]: value }))
                  return (
                    <label key={key} className={Array.isArray(value) ? 'wide-field' : ''}>
                      <span>{title}</span>
                      {options ? (
                        <select
                          value={String(value ?? '')}
                          disabled={saving}
                          onChange={(event) => set(event.target.value)}
                        >
                          {options.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      ) : Array.isArray(value) ? (
                        <textarea
                          value={value.join('\n')}
                          disabled={saving}
                          onChange={(event) => set(event.target.value.split('\n'))}
                          onBlur={() =>
                            set(
                              (values[key] as string[]).map((item) => item.trim()).filter(Boolean),
                            )
                          }
                        />
                      ) : (
                        <input
                          value={String(value ?? '')}
                          disabled={saving}
                          type={
                            schema.type === 'integer' || schema.type === 'number'
                              ? 'number'
                              : 'text'
                          }
                          step={schema.type === 'integer' ? 1 : 'any'}
                          min={schema.minimum}
                          max={schema.maximum}
                          minLength={schema.minLength}
                          maxLength={schema.maxLength}
                          onChange={(event) =>
                            set(
                              schema.type === 'integer' || schema.type === 'number'
                                ? event.target.value === ''
                                  ? ''
                                  : Number(event.target.value)
                                : event.target.value || (schema.anyOf ? null : ''),
                            )
                          }
                        />
                      )}
                      {Array.isArray(value) && <small>One item per line</small>}
                      {key === 'chat_provider' && values.chat_provider === 'codex' && (
                        <small>
                          Uses the server's signed-in Codex CLI. Select an accessible model and
                          leave the chat endpoint and credential fields empty. Timeout includes
                          CLI startup; this adapter does not use the retry setting.
                        </small>
                      )}
                      {key === 'lexical_tokenization' && (
                        <small>
                          With TF-IDF, code_identifiers also matches words inside snake_case and
                          camelCase names. Other embedding providers ignore this setting.
                        </small>
                      )}
                      {key === 'context_expander' && (
                        <small>
                          line_window adds nearby lines from the indexed snapshot in one bounded
                          pass. It does not determine whether the evidence answers the question.
                        </small>
                      )}
                    </label>
                  )
                })}
              </div>
            </details>
          ))
        ) : (
          <p>Loading settings…</p>
        )}
        <p className="settings-note">
          Credentials stay on the server. Enter environment variable names, never API keys. Live
          generation sends retrieved text to your selected provider; remote embeddings also send the
            indexed corpus. Optional adapters require their matching packages. FastEmbed embeds locally
            after downloading its selected model. Applying
          settings checks configuration and rebuilds retrieval; it does not verify live chat
          responses.
        </p>
        <details className="settings-group">
          <summary>Plugin options</summary>
          <div className="settings-fields">
            <label className="wide-field">
              <span>Plugin options (JSON)</span>
              <textarea
                value={pluginJson}
                disabled={saving}
                onChange={(event) => setPluginJson(event.target.value)}
              />
              <small>
                Non-secret options grouped by plugin name. Use server environment variables for
                credentials.
              </small>
            </label>
          </div>
        </details>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="settings-actions">
          <button type="button" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="primary" disabled={saving || !document}>
            {saving ? 'Preparing configuration…' : 'Apply settings'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
