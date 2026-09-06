import { getCollection } from 'astro:content';
import { isPublic } from './content-schema.mjs';
import { entryPath, baseId, locales, localizedPath } from './locales.mjs';

export async function getPublicCatalog(locale?: string) {
  const groups = await Promise.all([
    getCollection('facts', isPublic), getCollection('claims', isPublic), getCollection('ledger', isPublic)
  ]);
  return groups.flat().filter(entry => !locale || entry.data.languages[0] === locale).map(entry => ({
    id: entry.id, collection: entry.collection,
    title: 'title' in entry.data ? entry.data.title : entry.data.claim,
    path: entryPath(entry), translationKey: `${entry.collection}/${baseId(entry)}`, ...entry.data, body: entry.body ?? ''
  })).sort((a, b) => b.updated.localeCompare(a.updated) || a.path.localeCompare(b.path));
}

export const infoPages = ['about', 'methodology', 'corrections', 'data'] as const;
export const staticPages = locales.flatMap(locale => ['/', ...infoPages.map(p => `/${p}/`)].map(path => localizedPath(locale, path)));
export const repository = 'https://github.com/brianchenl/project-zhaozhao';
