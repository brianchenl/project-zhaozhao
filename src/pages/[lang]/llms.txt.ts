import type { APIRoute } from 'astro';
import { exportData } from '../../lib/exports';
import { translatedLocales, prefixes, localeFromPrefix } from '../../lib/locales.mjs';
export function getStaticPaths() {
  return translatedLocales.map(locale => ({ params: { lang: prefixes[locale] } }));
}
export const GET: APIRoute = ({ site, params }) => exportData('llms', site, localeFromPrefix(params.lang));
