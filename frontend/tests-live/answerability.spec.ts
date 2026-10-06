import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Run } from '../src/api'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const assets = resolve(root, 'docs/articles/assets')

test('live answers preserve coverage, evidence, and review decisions', async ({ page, request }, info) => {
  mkdirSync(assets, { recursive: true })
  const generated: Run[] = []
  page.on('response', async response => {
    if (response.url().endsWith('/api/runs') && response.request().method() === 'POST' && response.ok()) {
      generated.push(await response.json())
    }
  })
  async function savedRun(): Promise<Run> {
    const id = new URL(page.url()).searchParams.get('run')
    expect(id).toBeTruthy()
    const response = await request.get(`/api/runs/${id}`)
    expect(response.ok()).toBe(true)
    return response.json()
  }
  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
    const question = 'Explain the full publish_record implementation, including how it writes the destination.'
    await page.getByLabel('Your repository question').fill(question)
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('awaiting review')
    await expect(page.getByRole('region', { name: 'Answer assessment' })).toContainText('Partial answer')
    const partial = await savedRun()
    expect(partial.mode).toBe('live')
    expect(partial.limitations?.length).toBeGreaterThan(0)
    expect(partial.citations[0].excerpt).not.toContain('pending.replace(destination)')
    await page.reload()
    await expect(page.getByRole('region', { name: 'Answer assessment' })).toContainText(partial.limitations![0])
    await page.locator('.source-card summary').first().click()
    await page.screenshot({ path: resolve(assets, '08-live-partial.png'), fullPage: true })
    await page.getByRole('button', { name: 'Approve brief', exact: true }).click()
    await expect(page.getByRole('status')).toHaveText('approved')
    expect((await savedRun()).answerability).toBe('partial')
    expect((await savedRun()).answer).toBe(partial.answer)

    await page.goto('/')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText('Evidence context', { exact: true }).click()
    await dialog.getByLabel('Context expansion', { exact: false }).selectOption('line_window')
    await dialog.getByRole('button', { name: 'Apply settings' }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByLabel('Your repository question').fill(question)
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('completed')
    await expect(page.getByRole('region', { name: 'Answer assessment' })).toContainText('Complete answer')
    const complete = await savedRun()
    expect(complete.limitations).toEqual([])
    expect(complete.citations[0].excerpt).toContain('pending.replace(destination)')
    expect(complete.steps).toContain('expand_context')
    await page.reload()
    await page.locator('.source-card summary').first().click()
    await page.getByText('Context expansion details', { exact: true }).click()
    await page.screenshot({ path: resolve(assets, '09-live-complete.png'), fullPage: true })

    await page.goto('/')
    await page.getByRole('button', { name: 'Review a brief', exact: true }).click()
    await page.getByLabel('Your repository question').fill('Which production region runs publish_record?')
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(page.getByRole('status')).toHaveText('insufficient evidence')
    await expect(page.getByRole('region', { name: 'Answer assessment' })).toContainText('Insufficient evidence')
    await expect(page.getByRole('button', { name: 'Approve brief' })).toHaveCount(0)
    const insufficient = await savedRun()
    expect(insufficient.limitations?.length).toBeGreaterThan(0)
    expect(insufficient.steps).not.toContain('finish')
    expect((await request.post(`/api/runs/${insufficient.id}/decision`, { data: { approved: true } })).status()).toBe(409)
    await page.reload()
    await expect(page.getByRole('region', { name: 'Answer assessment' })).toContainText(insufficient.limitations![0])
    if (insufficient.citations.length) await page.locator('.source-card summary').first().click()
    await page.screenshot({ path: resolve(assets, '10-live-insufficient.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('live-mobile.png'), fullPage: true })
    expect(generated).toHaveLength(3)
  } finally {
    const path = info.outputPath('live-responses.json')
    writeFileSync(path, JSON.stringify(generated, null, 2))
    await info.attach('live-responses', { path, contentType: 'application/json' })
  }
})
