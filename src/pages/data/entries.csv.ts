import type { APIRoute } from 'astro';
import { exportData } from '../../lib/exports';
export const GET: APIRoute = ({ site }) => exportData('csv', site);
