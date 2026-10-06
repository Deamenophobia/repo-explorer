import { chromium } from '@playwright/test'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/articles/assets')
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1000, height: 500 }, deviceScaleFactor: 2 })
for (const name of ['architecture', 'retrieval', 'workflow', 'context-expansion']) {
  await page.goto(pathToFileURL(resolve(root, `${name}.svg`)).href)
  await page.locator('svg').screenshot({ path: resolve(root, `${name}.png`) })
}
await browser.close()
