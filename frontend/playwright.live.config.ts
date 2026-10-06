import { defineConfig } from '@playwright/test'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = dirname(fileURLToPath(import.meta.url))
const root = resolve(frontend, '..')
const configPath = process.env.REPO_EXPLORER_LIVE_CONFIG
if (!configPath) throw new Error('Set REPO_EXPLORER_LIVE_CONFIG to your local model configuration.')
const document = JSON.parse(readFileSync(resolve(configPath), 'utf8'))
const selected = document.workspace ?? document
if (typeof selected.model !== 'string' || !selected.model.trim() || !selected.chat_provider) {
  throw new Error('The live configuration must choose a chat_provider and accessible model.')
}

function port(name: string, fallback: number) {
  const value = Number(process.env[name] ?? fallback)
  if (!Number.isInteger(value) || value < 1 || value > 65535) throw new Error(`Invalid ${name}.`)
  return value
}
const apiPort = port('REPO_EXPLORER_LIVE_API_PORT', 8020)
const webPort = port('REPO_EXPLORER_LIVE_WEB_PORT', 5180)
if (apiPort === webPort) throw new Error('The live API and web ports must differ.')
const parent = resolve(root, '.repo-explorer/live-e2e')
mkdirSync(parent, { recursive: true })
const runDir = process.env.REPO_EXPLORER_LIVE_RUN_DIR ?? mkdtempSync(resolve(parent, 'run-'))
process.env.REPO_EXPLORER_LIVE_RUN_DIR = runDir
const settingsPath = resolve(runDir, 'settings.json')
const workspace = {
  mode: 'live', generator: 'chat',
  chat_provider: selected.chat_provider, model: selected.model,
  base_url: selected.base_url ?? null, chat_api_key_env: selected.chat_api_key_env ?? '',
  request_timeout: selected.request_timeout ?? 120, max_retries: selected.max_retries ?? 0,
  codex_reasoning_effort: selected.codex_reasoning_effort ?? 'medium',
  workspace_name: 'Live repository investigation',
  repository_name: 'examples / context-repository',
  corpus_description: 'Authored public source fixture',
  suggestions: ['Explain how publish_record writes its destination.'],
  source_provider: 'local', corpus_dir: resolve(root, 'examples/context-repository'),
  embedding_provider: 'tfidf', vector_store: 'memory', lexical_tokenization: 'code_identifiers',
  chunk_size: 200, chunk_overlap: 30, retrieval_limit: 1,
  context_expander: 'none', context_window_lines: 8, context_max_added_chars: 4000,
}
// Workers reuse the same runtime directory; only the runner writes initial settings.
if (!process.env.TEST_WORKER_INDEX) writeFileSync(settingsPath, JSON.stringify(workspace, null, 2))
const apiURL = `http://127.0.0.1:${apiPort}`
const python = process.platform === 'win32' ? '..\\.venv\\Scripts\\python.exe' : '../.venv/bin/python'
const requestDeadline = (Number(workspace.request_timeout) + 30) * 1000

export default defineConfig({
  testDir: './tests-live', workers: 1, fullyParallel: false, retries: 0,
  timeout: 3 * requestDeadline + 120_000, expect: { timeout: requestDeadline },
  outputDir: resolve(runDir, 'browser-results'),
  use: { baseURL: `http://127.0.0.1:${webPort}`, viewport: { width: 1440, height: 1120 }, trace: 'retain-on-failure' },
  webServer: [
    {
      command: `${python} -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port ${apiPort} --app-dir ../backend/src`,
      env: { REPO_EXPLORER_CONFIG_FILE: settingsPath, REPO_EXPLORER_DATA_DIR: runDir },
      url: `${apiURL}/api/health`, reuseExistingServer: false, timeout: 120_000,
    },
    {
      command: 'npm run dev',
      env: { REPO_EXPLORER_API_URL: apiURL, REPO_EXPLORER_WEB_PORT: String(webPort) },
      url: `http://127.0.0.1:${webPort}`, reuseExistingServer: false,
    },
  ],
})
