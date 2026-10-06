import { useEffect, useState } from 'react'
import {
  ArrowUpRight,
  ArrowUp,
  BookOpen,
  Compass,
  GitBranch,
  Layers,
  Plus,
  ShieldCheck,
} from 'lucide-react'
import { api, type Corpus, type Run } from './api'
import { EvidencePanel } from './components/EvidencePanel'
import { WorkflowTrace } from './components/WorkflowTrace'
import { SettingsPanel } from './components/SettingsPanel'
import { AnswerAssessment } from './components/AnswerAssessment'
import { EvidenceMap } from './components/EvidenceMap'

export function App() {
  const [corpus, setCorpus] = useState<Corpus | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [question, setQuestion] = useState('')
  const [intent, setIntent] = useState('question')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [focusRequest, setFocusRequest] = useState<{ sourceId: string } | null>(null)

  useEffect(() => {
    api
      .corpus()
      .then(setCorpus)
      .catch((error) => setError(error.message))
    const id = new URLSearchParams(location.search).get('run')
    if (id)
      api
        .run(id)
        .then((result) => {
          setRun(result)
          setIntent(result.intent)
        })
        .catch((error) => setError(error.message))
  }, [])

  function showRun(result: Run) {
    setFocusRequest(null)
    setRun(result)
    history.replaceState(null, '', `?run=${result.id}`)
  }

  async function ask(text: string) {
    if (busy || text.trim().length < 3) return
    setBusy(true)
    setError('')
    setQuestion(text)
    try {
      showRun(await api.ask(text, intent))
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function decide(approved: boolean) {
    if (!run) return
    setBusy(true)
    setError('')
    try {
      showRun(await api.decide(run.id, approved))
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <nav className="sidebar" aria-label="Main navigation">
        <a className="brand" href="/">
          <Compass size={29} />
          <span>
            Repo<span className="brand-sub">EXPLORER</span>
          </span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <div className="nav-item selected">
          <Layers size={18} />
          Knowledge workbench
        </div>
        <a className="nav-item" href="/docs" target="_blank" rel="noreferrer">
          <BookOpen size={18} />
          API reference
          <ArrowUpRight size={13} />
        </a>
        <div className="sidebar-bottom">
          <span className="little-orbit">R</span>
          <div>
            {corpus?.workspace_name ?? 'Workspace'}
            <small>Build with evidence.</small>
          </div>
        </div>
      </nav>
      <div className="workspace">
        <header className="topbar">
          <span>
            Workspace <span className="breadcrumb">/</span> Repository intelligence
          </span>
          <span className="local-status">
            <button
              className="settings-trigger"
              disabled={busy}
              onClick={() => setSettingsOpen(true)}
            >
              Settings
            </button>
            <i />
            Local workbench
          </span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">UNDERSTAND BEFORE YOU BUILD</div>
              <h1>
                A map of your code.
                <br />
                <em>Evidence for every step.</em>
              </h1>
              <p>Explore repository knowledge and review decisions in one place.</p>
            </div>
            <div className="edition">
              REPO EXPLORER / 01<small>KNOWLEDGE & REVIEW</small>
            </div>
          </div>
          <div className="repository-bar">
            <div className="repo-icon">
              <GitBranch size={21} />
            </div>
            <div>
              <strong>{corpus?.repository_name ?? 'Loading repository…'}</strong>
              <span>
                {corpus?.corpus_description} · {corpus?.files.length ?? '…'} source files
              </span>
            </div>
            <div className="mode-badge">
              {corpus?.mode === 'live' ? 'LIVE MODEL' : 'OFFLINE DEMO'}
            </div>
          </div>
          <div className="workbench-grid">
            <div className="conversation">
              <div className="conversation-header">
                <div className="tabs" aria-label="Workflow mode">
                  <button
                    disabled={busy}
                    className={intent === 'question' ? 'active' : ''}
                    onClick={() => setIntent('question')}
                  >
                    Ask the repository
                  </button>
                  <button
                    disabled={busy}
                    className={intent === 'review' ? 'active' : ''}
                    onClick={() => setIntent('review')}
                  >
                    Review a brief
                  </button>
                </div>
                <button
                  className="icon-button"
                  aria-label="New question"
                  disabled={busy}
                  onClick={() => {
                    setRun(null)
                    setQuestion('')
                    setError('')
                    history.replaceState(null, '', location.pathname)
                  }}
                >
                  <Plus size={19} />
                </button>
              </div>
              {!run ? (
                <div className="welcome">
                  <div className="welcome-icon">
                    <Compass size={30} />
                  </div>
                  <h2>Start with a good question.</h2>
                  <p>
                    Discover how a system works, where a decision lives,
                    <br />
                    and which rules apply.
                  </p>
                  <div className="suggestions">
                    {(corpus?.suggestions ?? []).map((text) => (
                      <button disabled={busy || !corpus} key={text} onClick={() => ask(text)}>
                        {text}
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <section className="answer-section" aria-label="Repository answer">
                  <div className="question-bubble">{run.question}</div>
                  <div className="answer-heading">
                    <Compass size={20} />
                    <strong>Repo Explorer</strong>
                    <span>{run.mode === 'demo' ? 'EXTRACTIVE DEMO' : 'MODEL RESPONSE'}</span>
                  </div>
                  <p className="answer-text">{run.answer}</p>
                  <AnswerAssessment run={run} />
                  <div className={`run-status ${run.status}`} role="status">
                    {run.status.replaceAll('_', ' ')}
                  </div>
                  {run.status === 'awaiting_review' && (
                    <div className="review-actions">
                      <p>Accept this brief for review records. No code will be changed.</p>
                      <button disabled={busy} onClick={() => decide(true)}>
                        Approve brief
                      </button>
                      <button className="secondary" disabled={busy} onClick={() => decide(false)}>
                        Reject brief
                      </button>
                    </div>
                  )}
                </section>
              )}
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault()
                  void ask(question)
                }}
              >
                <label className="sr-only" htmlFor="question">
                  Your repository question
                </label>
                <textarea
                  id="question"
                  value={question}
                  maxLength={2000}
                  disabled={busy}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder={
                    intent === 'review'
                      ? 'Describe the review brief you need…'
                      : 'Ask about architecture, policies, or implementation…'
                  }
                />
                <div>
                  <span>
                    {busy ? 'Running workflow…' : 'Answers stay connected to their sources.'}
                  </span>
                  <button
                    aria-label="Send question"
                    disabled={busy || !corpus || question.trim().length < 3}
                  >
                    <ArrowUp size={19} />
                  </button>
                </div>
              </form>
              {error && (
                <div className="error" role="alert">
                  {error}
                </div>
              )}
              <WorkflowTrace run={run} />
              {run && <EvidenceMap key={run.id} map={run.evidence_map}
                onInspect={sourceId => setFocusRequest({ sourceId })} />}
            </div>
              <EvidencePanel
                citations={run?.citations ?? []}
                corpus={corpus}
                expansion={run?.context_expansion}
                hasRun={Boolean(run)}
                focusRequest={focusRequest}
              />
          </div>
          <footer>
            <span>
              <ShieldCheck size={14} />
              {corpus?.retrieval ?? 'Connecting to API'} ·{' '}
              {corpus?.mode === 'live'
                ? 'Configured model generation'
                : 'No model calls in demo mode'}
            </span>
            <span>REPO EXPLORER</span>
          </footer>
        </main>
      </div>
      {settingsOpen && (
        <SettingsPanel
          onClose={() => setSettingsOpen(false)}
          onApplied={async () => {
            setCorpus(await api.corpus())
          }}
        />
      )}
    </div>
  )
}
