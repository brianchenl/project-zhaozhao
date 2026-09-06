import { getPublicCatalog } from './catalog';
import { csvCell } from './content-schema.mjs';
import { localizedPath } from './locales.mjs';
import { t } from './i18n';

export async function exportData(format: 'json' | 'csv' | 'llms', site: URL | undefined, locale?: string) {
  const entries = (await getPublicCatalog(locale)).map(e => ({ ...e, url: new URL(e.path, site).toString() }));
  if (format === 'json') return new Response(JSON.stringify({
    schemaVersion: 2, language: locale ?? 'all',
    license: 'https://creativecommons.org/licenses/by/4.0/',
    rightsNote: 'License covers original project text only; third-party documents retain their own rights.',
    entries
  }, null, 2), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  if (format === 'csv') {
    const rows = [
      ['collection', 'id', 'title', 'summary', 'published', 'updated', 'url', 'sources_json', 'body', 'language', 'translationKey', 'translationOf', 'sourceUpdated'],
      ...entries.map(e => [e.collection, e.id, e.title, e.summary, e.published, e.updated, e.url,
        JSON.stringify(e.sources), e.body, e.languages[0], e.translationKey, e.translationOf ?? '', e.sourceUpdated ?? ''])
    ];
    return new Response('\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n',
      { headers: { 'Content-Type': 'text/csv; charset=utf-8' } });
  }
  const lang = locale ?? 'zh-CN';
  const u = t(lang);
  const absolute = (path: string) => new URL(localizedPath(lang, path), site).toString();
  return new Response([
    `# ${u.brand}`, '', `> ${u.homeIntro}`, `> ${u.citationNote}`, `> ${u.footerNote}`, '',
    `## ${u.allEntries}`,
    ...entries.map(e => `- [${e.title}](${e.url}) [${e.languages[0]}]: ${e.summary}`), '',
    `## ${u.dataLinks}`,
    ...(['about', 'methodology', 'corrections', 'data'] as const).map(p => `- [${u.nav[p]}](${absolute('/' + p + '/')})`),
    `- [${u.json}](${absolute('/data/entries.json')})`, ''
  ].join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
