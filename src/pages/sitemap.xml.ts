import type { APIRoute } from 'astro';
import { getPublicCatalog, staticPages } from '../lib/catalog';
export const GET: APIRoute = async ({ site }) => {
  const entries = await getPublicCatalog();
  const escape = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const urls = [
    ...staticPages.map(path => `<url><loc>${escape(new URL(path, site).toString())}</loc></url>`),
    ...entries.map(e => `<url><loc>${escape(new URL(e.path, site).toString())}</loc><lastmod>${e.updated}</lastmod></url>`)
  ].join('');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`,
    { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
