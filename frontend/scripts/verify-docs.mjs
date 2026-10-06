import { chromium } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const series = JSON.parse(readFileSync(resolve(root, 'docs/articles/series.json'), 'utf8'))
const output = resolve(root, '.repo-explorer/document-preview')
mkdirSync(output, { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
for (const file of ['index', ...series.articles.map(article => article.slug)]) {
  await page.goto(pathToFileURL(resolve(root, `docs/site/${file}.html`)).href)
  const invalid = await page.locator('img').evaluateAll(images =>
    images.filter(image => !image.complete || image.naturalWidth === 0).map(image => image.src),
  )
  if (invalid.length) throw new Error(`Missing images in ${file}: ${invalid.join(', ')}`)
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
    throw new Error(`Horizontal overflow in ${file}`)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
    throw new Error(`Mobile horizontal overflow in ${file}`)
  }
  await page.setViewportSize({ width: 1440, height: 1100 })
}
await page.goto(pathToFileURL(resolve(root, 'docs/site/index.html')).href)
await page.screenshot({ path: resolve(output, 'index.png'), fullPage: true })
await page.goto(pathToFileURL(resolve(root, 'docs/site/repo-explorer-langgraph-review.html')).href)
await page.screenshot({ path: resolve(output, 'article.png'), fullPage: true })
await page.setViewportSize({ width: 390, height: 844 })
await page.screenshot({ path: resolve(output, 'article-mobile.png'), fullPage: true })
if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
  throw new Error('Mobile article overflows horizontally')
}
await browser.close()
console.log('Article pages render with loaded figures and responsive layout.')
