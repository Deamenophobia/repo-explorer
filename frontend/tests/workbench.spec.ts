import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'

const assets = '../docs/articles/assets'
test.beforeAll(() => mkdirSync(assets, { recursive: true }))

test('source analysis identifies a method outside its class header and survives review', async ({ page, request }) => {
  const original = (await (await request.get('/api/settings')).json()).values
  try {
    expect((await request.put('/api/settings', { data: {
      ...original, corpus_dir: '../examples/symbol-repository', source_analyzer: 'none',
      workspace_name: 'Source identity example', repository_name: 'examples / symbol-repository',
      corpus_description: 'Authored Python definitions', chunk_size: 200, chunk_overlap: 30,
      retrieval_limit: 1, lexical_tokenization: 'code_identifiers', context_expander: 'none',
    } })).ok()).toBe(true)
    await page.goto('/')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText('Evidence context', { exact: true }).click()
    await dialog.getByLabel('Source analysis', { exact: false }).selectOption('python_ast')
    await dialog.getByLabel('Definitions per passage').fill('8')
    await dialog.getByLabel('Maximum map blocks').fill('40')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
    await page.getByLabel('Your repository question').fill('deadline has arrived')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('awaiting review')
    await page.reload()
    const map = page.getByRole('region', { name: 'Evidence map', exact: true })
    await expect(map.getByRole('button', { name: 'Inspect class DeadlineCache', exact: true })).toBeVisible()
    const method = map.getByRole('button', { name: 'Inspect method DeadlineCache.expire', exact: true })
    await method.focus()
    await page.keyboard.press('Enter')
    const selection = map.getByRole('region', { name: 'Selected map block' })
    await expect(selection).toContainText('Contained by DeadlineCache')
    const openSource = selection.getByRole('button', { name: 'Open S1 · partial span', exact: true })
    await openSource.focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('.source-card summary')).toBeFocused()
    await expect(page.locator('.source-card')).toHaveAttribute('open', '')
    await page.locator('.evidence-map').screenshot({ path: `${assets}/12-evidence-map.png` })
    const context = page.getByRole('region', { name: 'Code context' })
    await expect(context).toContainText('DeadlineCache.expire')
    await expect(context).toContainText('Partial definition span')
    await expect(context).not.toContainText('ManualCache')
    await expect(page.locator('.source-card pre')).not.toContainText('class DeadlineCache')
    await page.screenshot({ path: `${assets}/11-source-identity.png`, fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(method).toBeVisible()
    await page.locator('.evidence-map').screenshot({ path: '../.repo-explorer/evidence-map-mobile.png' })
    await page.screenshot({ path: '../.repo-explorer/source-identity-mobile.png', fullPage: true })
    const values = (await (await request.get('/api/settings')).json()).values
    expect((await request.put('/api/settings', { data: {
      ...values, source_analyzer: 'none', evidence_map_node_limit: 2,
    } })).ok()).toBe(true)
    await page.reload()
    await expect(method).toBeVisible()
    await page.locator('.source-card summary').click()
    await expect(context).toContainText('DeadlineCache.expire')
    await expect(method).toBeVisible()
    await page.getByRole('button', { name: 'Approve brief' }).click()
    await expect(page.getByRole('status')).toHaveText('approved')
    await expect(context).toContainText('DeadlineCache.expire')
    await page.goto('/')
    await page.getByLabel('Your repository question').fill('deadline has arrived')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    await page.locator('.source-card summary').click()
    await expect(context).toHaveCount(0)
    await page.locator('.evidence-map > summary').click()
    await expect(map).toContainText('This passage has no saved source analysis')
    expect((await request.put('/api/settings', { data: {
      ...values, source_analyzer: 'python_ast', evidence_map_node_limit: 2,
    } })).ok()).toBe(true)
    await page.goto('/')
    await page.getByLabel('Your repository question').fill('deadline has arrived')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    await expect(map).toContainText('1 block omitted by the saved map limit of 2')
    await expect(method).toHaveCount(0)
  } finally {
    expect((await request.put('/api/settings', { data: original })).ok()).toBe(true)
  }
})

test('the evidence map switches files and exposes unsupported language coverage', async ({ page, request }) => {
  const original = (await (await request.get('/api/settings')).json()).values
  const corpus = '../.repo-explorer/e2e-map-corpus'
  mkdirSync(corpus, { recursive: true })
  writeFileSync(`${corpus}/cache.py`, 'class Cache:\n    def expire(self):\n        """Cache expiry records."""\n        return []\n')
  writeFileSync(`${corpus}/client.ts`, '// Cache expiry records.\nexport const expiry = "unknown"\n')
  try {
    expect((await request.put('/api/settings', { data: {
      ...original, corpus_dir: corpus, source_analyzer: 'python_ast',
      chunk_size: 1500, chunk_overlap: 0, retrieval_limit: 2, minimum_score: 0,
      context_expander: 'none', demo_excerpt_limit: 2, evidence_map_node_limit: 40,
    } })).ok()).toBe(true)
    await page.goto('/')
    await page.getByLabel('Your repository question').fill('cache expiry records')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    const map = page.getByRole('region', { name: 'Evidence map', exact: true })
    const picker = map.getByLabel('Map file')
    const options = await picker.locator('option').allTextContents()
    expect(options).toHaveLength(2)
    await picker.selectOption({ label: options.find(label => label.startsWith('cache.py'))! })
    await map.getByRole('button', { name: 'Inspect method Cache.expire', exact: true }).click()
    await expect(map.getByRole('region', { name: 'Selected map block' })).toContainText('Contained by Cache')
    await picker.selectOption({ label: options.find(label => label.startsWith('client.ts'))! })
    const selection = map.getByRole('region', { name: 'Selected map block' })
    await expect(selection).toContainText('client.ts')
    await expect(map).toContainText('unsupported language')
    await expect(map.getByRole('button', { name: /Inspect (class|method|function)/ })).toHaveCount(0)
    await selection.getByRole('button', { name: /Open S/ }).click()
    await expect(page.locator('.source-card').filter({ hasText: 'client.ts' })).toHaveAttribute('open', '')
  } finally {
    expect((await request.put('/api/settings', { data: original })).ok()).toBe(true)
  }
})

test('saved response assessments remain distinct from workflow status', async ({ page }) => {
  // Browser contract fixtures only; the opt-in live suite uses real generation.
  const saved = {
    id: '00000000-0000-0000-0000-000000000001', question: 'Explain a saved review brief.',
    intent: 'review', status: 'awaiting_review', answer: 'Saved explanation.', citations: [],
    steps: ['retrieve', 'compose', 'validate'], mode: 'live', retrieval: 'TF-IDF', snapshot: 'fixture',
  }
  let response: Record<string, unknown> = { ...saved }
  await page.route(`**/api/runs/${saved.id}`, route => route.fulfill({ json: response }))
  await page.goto(`/?run=${saved.id}`)
  const assessment = page.getByRole('region', { name: 'Answer assessment' })
  await expect(page.locator('.evidence-map')).toHaveCount(0)
  await expect(assessment).toContainText('Not assessed')
  await expect(page.getByRole('button', { name: 'Approve brief' })).toBeVisible()
  response = { ...saved, status: 'approved', answerability: 'partial', limitations: ['Error handling was not supplied.'] }
  await page.reload()
  await expect(page.getByRole('status')).toHaveText('approved')
  await expect(assessment).toContainText('Partial answer')
  await expect(assessment).toContainText('Error handling was not supplied.')
  await expect(page.getByRole('button', { name: 'Approve brief' })).toHaveCount(0)
  response = { ...saved, status: 'invalid_citations', answerability: 'not_assessed', limitations: [] }
  await page.reload()
  await expect(assessment).toContainText('source references were invalid')
  await expect(page.getByRole('region', { name: 'Workflow trace' })).not.toContainText('Human review')
  await expect(page.getByRole('button', { name: 'Approve brief' })).toHaveCount(0)
})

test('Codex settings persist while demo mode keeps generation offline', async ({ page, request }) => {
  const original = (await (await request.get('/api/settings')).json()).values
  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText('Generation', { exact: true }).click()
    await expect(dialog.getByLabel('Codex reasoning effort')).toHaveCount(0)
    await dialog.getByLabel('Chat Provider').selectOption('codex')
    await expect(dialog).toContainText("Uses the server's signed-in Codex CLI")
    await dialog.getByLabel('Codex reasoning effort').selectOption('low')
    await dialog.getByLabel('Chat model', { exact: true }).fill('fixture-model')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog).toHaveCount(0)
    await page.reload()
    await expect(page.getByText('OFFLINE DEMO', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    await dialog.getByText('Generation', { exact: true }).click()
    await expect(dialog.getByLabel('Chat Provider')).toHaveValue('codex')
    await expect(dialog.getByLabel('Codex reasoning effort')).toHaveValue('low')
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await dialog.getByLabel('Chat Provider').selectOption('openai')
    await expect(dialog.getByLabel('Codex reasoning effort')).toHaveCount(0)
  } finally {
    expect((await request.put('/api/settings', { data: original })).ok()).toBe(true)
  }
})

test('settings persist, affect retrieval, and reject invalid changes', async ({
  page,
  request,
}) => {
  const original = (await (await request.get('/api/settings')).json()).values
  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel('Workspace Name')).toBeVisible()
    await page.screenshot({ path: `${assets}/06-settings.png`, fullPage: true })
    await dialog.getByLabel('Workspace Name').fill('My engineering workspace')
    await dialog.getByText('Retrieval', { exact: true }).click()
    await dialog.getByLabel('Retrieval Limit').fill('1')
    await dialog.getByLabel('TF-IDF tokenization').selectOption('code_identifiers')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog).toHaveCount(0)
    await page.reload()
    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toContainText(
      'My engineering workspace',
    )
    await page.getByLabel('Your repository question').fill('repository ingestion')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    await expect(page.locator('.source-card')).toHaveCount(1)
    await expect(page.locator('footer')).toContainText(
      'TF-IDF / code identifiers',
    )
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    await expect(dialog.getByLabel('TF-IDF tokenization')).toHaveValue('code_identifiers')
    await dialog.getByText('Source and chunking', { exact: true }).click()
    await dialog.getByLabel('Chunk Size').fill('100')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog.getByRole('alert')).toContainText('overlap')
    await expect(dialog.getByRole('button', { name: 'Apply settings' })).toBeEnabled()
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
      true,
    )
    await page.screenshot({ path: '../.repo-explorer/settings-mobile.png', fullPage: true })
  } finally {
    const restored = await request.put('/api/settings', { data: original })
    expect(restored.ok()).toBe(true)
  }
})

test('ask, inspect original evidence, and preserve the run on reload', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('OFFLINE DEMO', { exact: true })).toBeVisible()
  await expect(page.getByText('docs/ingestion.md', { exact: true })).toBeVisible()
  await page.screenshot({ path: `${assets}/01-workbench.png`, fullPage: true })
  await page
    .getByRole('button', { name: 'How does repository ingestion preserve source references?' })
    .click()
  await expect(page.getByRole('status')).toHaveText('completed')
  const source = page.locator('.source-card').filter({ hasText: 'docs/ingestion.md' }).first()
  await source.locator('summary').click()
  await expect(source.locator('pre')).toContainText('TF-IDF')
  await page.screenshot({ path: `${assets}/02-evidence.png`, fullPage: true })
  await page.reload()
  await expect(page.getByRole('status')).toHaveText('completed')
  await expect(page.getByRole('region', { name: 'Repository answer' })).toContainText(
    'source references',
  )
})

test('review pauses, reloads, and accepts an explicit decision', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
  await page
    .getByLabel('Your repository question')
    .fill('Review the checkpoint and human review policy')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('status')).toHaveText('awaiting review')
  await page.screenshot({ path: `${assets}/03-review.png`, fullPage: true })
  await page.reload()
  await expect(page.getByRole('button', { name: 'Approve brief' })).toBeVisible()
  await page.getByRole('button', { name: 'Approve brief' }).click()
  await expect(page.getByRole('status')).toHaveText('approved')
  await expect(page.getByRole('button', { name: 'Approve brief' })).toHaveCount(0)
})

test('unsupported questions abstain and rejection remains terminal', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Your repository question').fill('zyzzyva quokka nebula')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('status')).toHaveText('insufficient evidence')
  await expect(page.locator('.source-card')).toHaveCount(0)
  await page.screenshot({ path: `${assets}/04-abstention.png`, fullPage: true })
  await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
  await page.getByLabel('Your repository question').fill('Review human review policy')
  await page.getByRole('button', { name: 'Send question' }).click()
  await page.getByRole('button', { name: 'Reject brief' }).click()
  await expect(page.getByRole('status')).toHaveText('rejected')
})

test('mobile layout remains usable without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByText('docs/ingestion.md', { exact: true })).toBeVisible()
  await page
    .getByLabel('Your repository question')
    .fill('How do checkpoints make human review durable?')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('status')).toHaveText('completed')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: `${assets}/05-mobile.png`, fullPage: true })
})

test('bounded context recovers nearby lines and keeps evidence across review reload', async ({
  page,
  request,
}) => {
  const original = (await (await request.get('/api/settings')).json()).values
  try {
    const configured = await request.put('/api/settings', {
      data: {
        ...original,
        workspace_name: 'Context expansion example',
        repository_name: 'examples / context-repository',
        corpus_description: 'Authored source example',
        corpus_dir: '../examples/context-repository',
        lexical_tokenization: 'code_identifiers',
        chunk_size: 200,
        chunk_overlap: 30,
        retrieval_limit: 1,
        context_expander: 'none',
      },
    })
    expect(configured.ok()).toBe(true)
    await page.goto('/')
    await page.getByLabel('Your repository question').fill('publish_record')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    await page.locator('.source-card summary').click()
    await expect(page.locator('.source-card pre')).not.toContainText('pending.replace(destination)')

    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText('Evidence context', { exact: true }).click()
    await dialog.getByLabel('Context expansion', { exact: false }).selectOption('line_window')
    await dialog.getByLabel('Surrounding lines').fill('8')
    await dialog.getByLabel('Maximum added characters').fill('4000')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
    await page.getByLabel('Your repository question').fill('publish_record')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('awaiting review')
    await page.reload()
    await page.locator('.source-card summary').click()
    await expect(page.locator('.source-card pre')).toContainText('pending.replace(destination)')
    await expect(page.getByRole('region', { name: 'Workflow trace' })).toContainText('Expand context')
    await page.getByText('Context expansion details', { exact: true }).click()
    await expect(page.locator('.context-trace')).toContainText('One expansion pass completed.')
    await expect(page.locator('.source-meta')).toContainText('similarity is for the original match')
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: `${assets}/07-context-expansion.png`, fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: '../.repo-explorer/context-mobile.png', fullPage: true })
    await page.getByRole('button', { name: 'Approve brief' }).click()
    await expect(page.getByRole('status')).toHaveText('approved')
    await expect(page.locator('.source-card pre')).toContainText('pending.replace(destination)')
  } finally {
    expect((await request.put('/api/settings', { data: original })).ok()).toBe(true)
  }
})
