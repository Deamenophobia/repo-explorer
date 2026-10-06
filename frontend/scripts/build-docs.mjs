import { readFileSync, writeFileSync, mkdirSync, cpSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { marked } from 'marked'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const articles = resolve(root, 'docs/articles')
const output = resolve(root, 'docs/site')
const series = JSON.parse(readFileSync(resolve(articles, 'series.json'), 'utf8'))
mkdirSync(output, { recursive: true })
cpSync(resolve(articles, 'assets'), resolve(output, 'assets'), { recursive: true })
const escape = (value) =>
  value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;')
const css = `*{box-sizing:border-box}body{margin:0;background:#f7f8f2;color:#334631;font:16px/1.85 'Segoe UI',sans-serif}header{background:#15392d;color:#e4edda;padding:30px max(24px,calc((100% - 1100px)/2));font-size:14px;letter-spacing:2px}header a{color:inherit;text-decoration:none}header small{display:block;letter-spacing:0;color:#a8be99;font-size:12px}.layout{display:grid;grid-template-columns:240px minmax(0,820px);gap:45px;max-width:1160px;margin:45px auto;padding:0 24px}nav{font-size:13px}nav a{display:block;padding:12px 0;border-bottom:1px solid #dfe7d5;text-decoration:none;color:#69805a}nav span{font-size:10px;letter-spacing:1px;color:#9aa98c}article{min-width:0}h1,h2{font-family:Georgia,serif;line-height:1.2;font-weight:400;letter-spacing:-.6px;color:#23452e}h1{font-size:43px;margin:0 0 28px}h2{font-size:29px;margin-top:42px}p{margin:19px 0}a{color:#517e37;text-underline-offset:3px}img{max-width:100%;height:auto;border:1px solid #dce5d1;border-radius:9px;display:block;margin:28px auto}p:has(>em:only-child){font-size:13px;color:#80916f;line-height:1.7}pre{background:#eaf0e1;padding:23px;overflow:auto;border-radius:8px;line-height:1.6;font-size:13px}code{font-size:.86em;overflow-wrap:anywhere}table{border-collapse:collapse;font-size:13px;width:100%}td,th{padding:12px;border-bottom:1px solid #d6dfcb;text-align:left}blockquote{border-left:3px solid #9ab17b;padding-left:20px;color:#6c805b}.draft{font-size:11px;letter-spacing:1.5px;color:#8d9e78;margin-bottom:14px}.next{border-top:1px solid #dae3cc;padding-top:24px;margin-top:45px;font-size:14px}.cards{display:grid;gap:17px}.card{display:block;padding:24px;border:1px solid #dae3cc;border-radius:10px;background:#fdfef8;text-decoration:none}.card strong{font:24px Georgia,serif;display:block;color:#325135}.card p{font-size:14px;margin:12px 0 0;color:#829372}@media(max-width:800px){.layout{display:block;margin:25px auto}nav{margin-bottom:35px}nav a{padding:7px 0}h1{font-size:35px}body{font-size:15px}header{padding:24px}}`
const nav = `<nav><span>THE ENGINEERING SERIES</span>${series.articles.map((a, i) => `<a href="${a.slug}.html">0${i + 1} / ${escape(a.title)}</a>`).join('')}</nav>`
function page(title, body) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} · Repo Explorer</title><style>${css}</style></head><body><header><a href="index.html">REPO EXPLORER / ENGINEERING NOTES</a><small>A repository assistant, explained from evidence to interface.</small></header><div class="layout">${nav}<article><div class="draft">EDITORIAL DRAFT · VERSION 0.1.0</div>${body}</article></div></body></html>`
}
for (const [i, article] of series.articles.entries()) {
  const source = readFileSync(resolve(articles, article.file), 'utf8')
  for (const match of source.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)) {
    if (!existsSync(resolve(articles, match[1])))
      throw new Error(`Missing article asset: ${match[1]}`)
  }
  const next = series.articles[i + 1]
  const html =
    marked.parse(source) +
    (next
      ? `<div class="next">Continue reading → <a href="${next.slug}.html">${escape(next.title)}</a></div>`
      : '')
  writeFileSync(resolve(output, `${article.slug}.html`), page(article.title, html))
}
const introduction =
  `<h1>${escape(series.title)}</h1><p>${escape(series.description)}</p><img src="assets/01-workbench.png" alt="Repo Explorer repository workbench"><p>${escape(series.evidence_note)}</p>`
const cards = `<div class="cards">${series.articles.map((a, i) => `<a class="card" href="${a.slug}.html"><div class="draft">CHAPTER 0${i + 1}</div><strong>${escape(a.title)}</strong><p>${escape(a.description)}</p></a>`).join('')}</div>`
writeFileSync(resolve(output, 'index.html'), page(series.title, introduction + cards))
console.log(`Article preview built at ${output}`)
