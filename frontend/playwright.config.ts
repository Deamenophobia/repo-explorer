import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5178',
    viewport: { width: 1440, height: 1120 },
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        process.platform === 'win32'
          ? '..\\.venv\\Scripts\\python.exe -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --app-dir ../backend/src'
          : '../.venv/bin/python -m uvicorn repo_explorer.api:app --host 127.0.0.1 --port 8018 --app-dir ../backend/src',
      env: {
        REPO_EXPLORER_MODE: 'demo',
        REPO_EXPLORER_EMBEDDING_MODEL: '',
        REPO_EXPLORER_CORPUS_DIR: '../examples/repository',
        REPO_EXPLORER_DATA_DIR: '../.repo-explorer/e2e',
        REPO_EXPLORER_CONFIG_FILE: '../.repo-explorer/e2e-settings.json',
      },
      url: 'http://127.0.0.1:8018/api/health',
      reuseExistingServer: false,
      timeout: 120000,
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5178', reuseExistingServer: false },
  ],
})
