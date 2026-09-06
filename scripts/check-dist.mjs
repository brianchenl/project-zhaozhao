import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { relative } from 'node:path';
import { load } from 'cheerio';
import { readEntries, walk } from './content-files.mjs';
import { locales, prefixes, localizedPath } from '../src/lib/locales.mjs';

const source = await readEntries();
const publicEntries = source.filter(e => e.data.status === 'published');
const files = await walk('dist');
const paths = new Set(files.map(file => '/' + relative('dist', file).replaceAll('\\', '/')));
const data = JSON.parse(await readFile('dist/data/entries.json', 'utf8'));
assert.equal(data.schemaVersion, 2);
assert.equal(data.language, 'all');
assert.deepEqual(data.entries.map(e => e.path).sort(), publicEntries.map(e => e.path).sort());
const pages = new Map();
for (const file of files.filter(f => f.endsWith('.html'))) {
  const raw = await readFile(file, 'utf8');
  const $ = load(raw);
  const path = '/' + relative('dist', file).replaceAll('\\', '/');
  pages.set(path, $);
  const lang = locales.find(l => prefixes[l] && path.startsWith('/' + prefixes[l] + '/')) ?? 'zh-CN';
  assert.equal($('html').attr('lang'), lang, file);
  assert.equal($('h1').length, 1, file);
  assert.ok($('title').text().trim(), file);
  assert.ok($('meta[name="description"]').attr('content'), file);
  assert.equal($('link[rel="canonical"]').length, 1, file);
  assert.equal($('script').not('[type="application/ld+json"]').length, 0, `意外客户端脚本：${file}`);
  for (const script of $('script[type="application/ld+json"]').toArray()) JSON.parse($(script).html());
  assert.doesNotMatch(raw, /docs\/internal|待填写|待补：|核查示例|引用率约为|三个月未更新/);
}
const origin = new URL(pages.get('/index.html')('link[rel="canonical"]').attr('href')).origin;
function targetPath(url) {
  const pathname = decodeURIComponent(url.pathname);
  return pathname.endsWith('/') ? `${pathname}index.html` : pathname;
}
function assertLink(href, base) {
  const url = new URL(href, base);
  if (url.origin !== origin) return;
  const target = targetPath(url);
  assert.ok(paths.has(target), `站内链接缺失：${href} (from ${base})`);
  if (url.hash && pages.has(target)) {
    const ids = pages.get(target)('[id]').toArray().map(el => pages.get(target)(el).attr('id'));
    assert.ok(ids.includes(decodeURIComponent(url.hash.slice(1))), `锚点缺失：${href}`);
  }
}
for (const [path, $] of pages) {
  const canonical = $('link[rel="canonical"]').attr('href');
  assert.equal(new URL(canonical).origin, origin);
  const expected = path.replace(/index\.html$/, '');
  assert.equal(new URL(canonical).pathname, expected, `canonical 路径不匹配：${path}`);
  if (path !== '/404.html') {
    const variants = $('link[rel="alternate"]').toArray();
    assert.equal(variants.length, 5, path);
    assert.deepEqual(variants.map(el => $(el).attr('hreflang')).sort(), [...locales, 'x-default'].sort());
    assert.equal($('nav.languages a[aria-current="page"]').length, 1);
    for (const el of variants) {
      const href = $(el).attr('href');
      const target = pages.get(targetPath(new URL(href)));
      assert.ok(target, href);
      const locale = $(el).attr('hreflang');
      assert.equal(target('html').attr('lang'), locale === 'x-default' ? 'zh-CN' : locale);
      const reciprocal = target('link[rel="alternate"]').toArray().some(a => target(a).attr('href') === canonical);
      assert.ok(reciprocal, `hreflang not reciprocal: ${canonical} -> ${href}`);
    }
  }
  for (const link of $('a[href], link[href], img[src]').toArray()) {
    assertLink($(link).attr('href') ?? $(link).attr('src'), canonical);
  }
}
for (const entry of data.entries) {
  const $ = pages.get(entry.path + 'index.html');
  assert.ok($, entry.path);
  assert.equal($('h1').text(), entry.title);
  const ld = JSON.parse($('script[type="application/ld+json"]').html());
  assert.equal(ld['@type'], entry.collection === 'claims' ? 'ClaimReview' : 'Article');
  assert.equal(ld.url, entry.url);
  assert.deepEqual(ld.citation.map(s => s.url), entry.sources.map(s => s.url));
  assert.equal(ld.dateModified, entry.updated);
  assert.equal(ld.inLanguage, entry.languages[0]);
  assert.equal($('.translation-note').length, entry.translationOf ? 1 : 0);
  if (entry.translationOf) assert.equal(ld.translationOfWork['@id'], new URL('/' + entry.translationKey + '/', origin).href);
  const siblings = data.entries.filter(e => e.translationKey === entry.translationKey);
  assert.deepEqual($('link[rel="alternate"]').toArray().filter(el => $(el).attr('hreflang') !== 'x-default').map(el => $(el).attr('href')).sort(), siblings.map(e => e.url).sort());
  const original = publicEntries.find(e => e.path === entry.path);
  assert.equal(entry.body.trim(), original.body.trim());
}
const llms = await readFile('dist/llms.txt', 'utf8');
for (const match of llms.matchAll(/\]\((https:\/\/[^)]+)\)/g)) assertLink(match[1], origin);
for (const entry of data.entries) assert.ok(llms.includes(entry.url));
const sitemap = load(await readFile('dist/sitemap.xml', 'utf8'), { xml: true });
const locs = sitemap('loc').toArray().map(el => sitemap(el).text());
const expectedUrls = [...pages.keys()].filter(p => p !== '/404.html').map(p => new URL(p.replace(/index\.html$/, ''), origin).href);
assert.deepEqual(locs.sort(), expectedUrls.sort());
assert.ok((await readFile('dist/robots.txt', 'utf8')).includes(`Sitemap: ${origin}/sitemap.xml`));
for (const entry of source.filter(e => e.data.status !== 'published')) {
  assert.ok(!paths.has(entry.path + 'index.html'));
  assert.ok(!llms.includes(entry.path));
  assert.ok(!locs.includes(new URL(entry.path, origin).href));
}
// Parse RFC 4180 quoted fields, including multiline bodies, to compare the CSV export.
function parseCsv(text) {
const csv = text.replace(/^\uFEFF/, '');
const rows = []; let row = []; let cell = ''; let quoted = false;
for (let i = 0; i < csv.length; i++) {
  const c = csv[i];
  if (c === '"') {
    if (quoted && csv[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted;
  } else if (c === ',' && !quoted) { row.push(cell); cell = ''; }
  else if (c === '\r' && csv[i + 1] === '\n' && !quoted) { row.push(cell); rows.push(row); row = []; cell = ''; i++; }
  else cell += c;
}
assert.equal(quoted, false);
return rows;
}
const rows = parseCsv(await readFile('dist/data/entries.csv', 'utf8'));
assert.equal(rows.length, data.entries.length + 1);
for (const fields of rows.slice(1)) {
  assert.equal(fields.length, 13);
  const entry = data.entries.find(e => e.url === fields[6]);
  assert.ok(entry);
  assert.equal(fields[2], entry.title);
  assert.deepEqual(JSON.parse(fields[7]), entry.sources);
  assert.equal(fields[8].trim(), entry.body.trim());
  assert.equal(fields[9], entry.languages[0]);
  assert.equal(fields[10], entry.translationKey);
  assert.equal(fields[11], entry.translationOf ?? '');
  assert.equal(fields[12], entry.sourceUpdated ?? '');
}
console.log(`产物校验通过：${pages.size} 个 HTML，${data.entries.length} 个条目；站内链接、JSON-LD、草稿隔离、sitemap、llms、JSON/CSV 一致。`);

for (const locale of locales) {
  const matching = data.entries.filter(e => e.languages[0] === locale);
  const home = pages.get(localizedPath(locale) + 'index.html');
  assert.deepEqual(home('.item-list a').toArray().map(a => home(a).attr('href')).sort(), matching.map(e => e.path).sort());
  // This edition deliberately includes the same five topics in all four languages.
  assert.equal(matching.length, 5);
  if (locale === 'zh-CN') continue;
  const root = 'dist' + localizedPath(locale);
  const localData = JSON.parse(await readFile(root + 'data/entries.json', 'utf8'));
  assert.equal(localData.schemaVersion, 2);
  assert.equal(localData.language, locale);
  assert.deepEqual(localData.entries, matching);
  const localRows = parseCsv(await readFile(root + 'data/entries.csv', 'utf8'));
  assert.deepEqual(localRows, [rows[0], ...rows.slice(1).filter(row => row[9] === locale)]);
  const localIndex = await readFile(root + 'llms.txt', 'utf8');
  for (const match of localIndex.matchAll(/\]\((https:\/\/[^)]+)\)/g)) assertLink(match[1], origin);
  for (const e of data.entries) assert.equal(localIndex.includes(e.url + ')'), e.languages[0] === locale, e.url);
}
assert.equal(pages.size, 41);
console.log('多语言校验通过：4 种语言，每种 5 篇；原文关联、语言切换、双向 hreflang 和分语言导出一致。');
