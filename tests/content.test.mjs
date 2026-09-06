import test from 'node:test';
import assert from 'node:assert/strict';
import { schemas, isPublic, serializeJsonLd, csvCell } from '../src/lib/content-schema.mjs';
import { validateBody, validateTranslations, readEntries } from '../scripts/content-files.mjs';
import { entryPath, locales } from '../src/lib/locales.mjs';

const source = (id) => ({ title: '档案', url: `https://example.org/${id}`, publisher: '馆藏机构',
  independenceKey: id, locator: '档案号123，第1页', accessed: '2026-09-06' });
const valid = () => ({ title: '历史事件', summary: '这是包含足够信息的完整事实摘要。', published: '2026-09-06', updated: '2026-09-06',
  status: 'published', sources: [source('a'), source('b')] });

test('only published entries are exposed; draft and reviewed remain private to the build', () => {
  assert.equal(isPublic({ data: { status: 'published' } }), true);
  for (const status of ['draft', 'reviewed', undefined]) assert.equal(isPublic({ data: { status } }), false);
});
test('reject missing or duplicate independent evidence even when URLs differ', () => {
  assert.equal(schemas.facts.safeParse(valid()).success, true);
  for (const sources of [[], [source('a')], [source('a'), { ...source('b'), independenceKey: 'a' }], [source('a'), { ...source('b'), url: source('a').url }]]) {
    assert.equal(schemas.facts.safeParse({ ...valid(), sources }).success, false);
  }
  assert.equal(schemas.facts.safeParse({ ...valid(), status: 'draft', sources: [] }).success, true);
});
test('reject invalid, future and reversed dates', () => {
  for (const updated of ['2026-02-30', '2099-01-01', '2026-09-05']) assert.equal(schemas.facts.safeParse({ ...valid(), updated }).success, false);
  assert.equal(schemas.facts.safeParse({ ...valid(), dateStart: '1945-09-02', dateEnd: '1945-08-15' }).success, false);
});
test('placeholders and unlinked evidence block public content', () => {
  assert.equal(schemas.facts.safeParse({ ...valid(), summary: '待填写所有历史事件的具体资料。' }).success, false);
  assert.throws(() => validateBody({ collection: 'facts', file: 'test.md', data: valid(), body: '## 事实与证据\n' + '证据说明。'.repeat(30) + '\n## 范围与限制\n[出处1](#source-1)' }), /出处2/);
});
test('JSON-LD cannot escape the script element', () => {
  const value = { text: '</script><script>alert(1)</script>中文' };
  const serialized = serializeJsonLd(value);
  assert.ok(!serialized.includes('<'));
  assert.deepEqual(JSON.parse(serialized), value);
});
test('CSV escapes multiline quoted cells and neutralizes formulas', () => {
  assert.equal(csvCell('一行,"引文"\n二行'), '"一行,""引文""\n二行"');
  assert.equal(csvCell('=1+1'), '"\'=1+1"');
  assert.equal(csvCell(' @SUM(1)'), '"\' @SUM(1)"');
});

test('translations require a supported single language and original revision', () => {
  for (const fields of [{ languages: ['fr'] }, { languages: ['en'] }, { languages: ['en', 'ja'] }, { translationOf: 'sample' }]) {
    assert.equal(schemas.facts.safeParse({ ...valid(), ...fields }).success, false);
  }
  assert.equal(schemas.facts.safeParse({ ...valid(), languages: ['en'], translationOf: 'sample', sourceUpdated: '2026-09-06' }).success, true);
});

test('translated sources, dates, original availability and source revision stay aligned', async () => {
  const entries = await readEntries();
  assert.doesNotThrow(() => validateTranslations(entries));
  for (const mutate of [
    e => { e.data.sourceUpdated = '2026-09-05'; },
    e => { e.data.sources[0].url = 'https://example.org/changed'; },
    e => { e.data.dateStart = '1940-01-01'; },
    e => { e.data.translationOf = 'missing-original'; },
    e => { e.id = 'ja/wrong-file'; }
  ]) {
    const changed = structuredClone(entries);
    mutate(changed.find(e => e.collection === 'facts' && e.data.languages[0] === 'en'));
    assert.throws(() => validateTranslations(changed));
  }
  const changed = structuredClone(entries);
  changed.find(e => e.id === 'japan-surrender-1945').data.status = 'draft';
  assert.throws(() => validateTranslations(changed), /原文未公开/);
  for (const e of entries) assert.equal(entryPath(e), e.path);
});

test('every locale has the same UI keys and complete informational pages', async () => {
  const { readFile } = await import('node:fs/promises');
  const ui = JSON.parse(await readFile('src/i18n/ui.json', 'utf8'));
  const pages = JSON.parse(await readFile('src/i18n/pages.json', 'utf8'));
  function keys(obj, prefix = '') {
    return Object.entries(obj).flatMap(([k, v]) => typeof v === 'object' ? keys(v, prefix + k + '.') : [prefix + k]).sort();
  }
  for (const locale of locales) {
    assert.deepEqual(keys(ui[locale]), keys(ui['zh-CN']));
    assert.deepEqual(Object.keys(pages[locale]).sort(), ['about', 'corrections', 'data', 'methodology']);
    assert.ok(Object.values(ui[locale]).every(v => typeof v !== 'string' || v.trim()));
  }
});
