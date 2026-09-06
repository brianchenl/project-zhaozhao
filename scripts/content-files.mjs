import { readdir, readFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { parse } from 'yaml';
import { schemas } from '../src/lib/content-schema.mjs';
import { entryPath, prefixes, contentHeadings } from '../src/lib/locales.mjs';

export async function walk(root) {
  const files = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else if (entry.isFile()) files.push(path);
  }
  return files.sort();
}

export async function readEntries() {
  const entries = [];
  for (const collection of Object.keys(schemas)) {
    const root = `src/content/${collection}`;
    for (const file of await walk(root)) {
      if (!file.endsWith('.md')) throw new Error(`内容目录仅接受 Markdown：${file}`);
      const id = relative(root, file).replace(/\.md$/, '').replaceAll('\\', '/');
      if (!/^[a-z0-9]+(?:[-/][a-z0-9]+)*$/.test(id)) throw new Error(`不稳定的路径标识：${file}`);
      const raw = await readFile(file, 'utf8');
      const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
      if (!match) throw new Error(`缺少 YAML frontmatter：${file}`);
      const parsed = schemas[collection].safeParse(parse(match[1]));
      if (!parsed.success) throw new Error(`${file}\n${parsed.error.message}`);
      const entry = { collection, id, file, data: parsed.data, body: match[2] };
      entries.push({ ...entry, path: entryPath(entry) });
    }
  }
  return entries;
}

export function validateBody(entry) {
  if (entry.data.status !== 'published') return;
  if (/待补|待填写|待核档|TODO|\[ \]/.test(entry.body)) throw new Error(`${entry.file}: 公开正文包含占位内容`);
  if (entry.body.trim().length < 100) throw new Error(`${entry.file}: 正文过短`);
  const localizedHeadings = contentHeadings[entry.data.languages?.[0] ?? 'zh-CN'];
  const headings = [...localizedHeadings[entry.collection]];
  if (entry.data.category === 'statistics') headings.push(...localizedHeadings.statistics);
  for (const heading of headings) {
    if (!entry.body.includes(`## ${heading}`)) throw new Error(`${entry.file}: 缺少 ${heading}`);
  }
  for (let i = 1; i <= entry.data.sources.length; i++) {
    if (!entry.body.includes(`](#source-${i})`)) throw new Error(`${entry.file}: 出处${i}未在正文关联`);
  }
  for (const match of entry.body.matchAll(/\]\(#source-(\d+)\)/g)) {
    if (+match[1] < 1 || +match[1] > entry.data.sources.length) throw new Error(`${entry.file}: 引用了不存在的出处`);
  }
}

export function validateTranslations(entries) {
  const seen = new Set();
  for (const entry of entries) {
    if (seen.has(entry.path)) throw new Error(`重复路由：${entry.path}`);
    seen.add(entry.path);
    const locale = entry.data.languages[0];
    if (locale === 'zh-CN') {
      if (entry.id.includes('/')) throw new Error(`原文路径不能有语言前缀：${entry.file}`);
      continue;
    }
    if (entry.id !== `${prefixes[locale]}/${entry.data.translationOf}`) throw new Error(`译文目录与语言不一致：${entry.file}`);
    const original = entries.find(e => e.collection === entry.collection && e.id === entry.data.translationOf && e.data.languages[0] === 'zh-CN');
    if (!original) throw new Error(`译文缺少原文：${entry.file}`);
    if (entry.data.status !== 'published') continue;
    if (original.data.status !== 'published') throw new Error(`原文未公开：${entry.file}`);
    if (entry.data.sourceUpdated !== original.data.updated) throw new Error(`译文落后于原文更新：${entry.file}`);
    const sources = e => JSON.stringify(e.data.sources.map(s => [s.url, s.independenceKey, s.accessed]));
    if (sources(entry) !== sources(original)) throw new Error(`译文与原文证据链不一致：${entry.file}`);
    for (const key of ['dateStart', 'dateEnd', 'date', 'verdict', 'kind', 'category', 'wikidata']) {
      if (entry.data[key] !== original.data[key]) throw new Error(`译文改变事实字段 ${key}：${entry.file}`);
    }
  }
}
