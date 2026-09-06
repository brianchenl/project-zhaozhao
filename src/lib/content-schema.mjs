import { z } from 'zod';

const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value => {
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}, '日期必须真实存在，格式为 YYYY-MM-DD');
const source = z.object({
  title: z.string().min(1),
  url: z.url({ protocol: /^https$/ }),
  publisher: z.string().min(1),
  independenceKey: z.string().min(1),
  locator: z.string().min(1),
  accessed: day
});
const common = {
  summary: z.string().min(10).max(300),
  published: day, updated: day,
  status: z.enum(['draft', 'reviewed', 'published']).default('draft'),
  sources: z.array(source).default([]),
  languages: z.array(z.enum(['zh-CN', 'zh-Hant', 'en', 'ja'])).length(1).default(['zh-CN']),
  translationOf: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).optional(),
  sourceUpdated: day.optional()
};

function validatePublic(data, ctx) {
  const today = new Date().toISOString().slice(0, 10);
  const issue = (path, message) => ctx.addIssue({ code: 'custom', path, message });
  if (data.languages[0] !== 'zh-CN' && (!data.translationOf || !data.sourceUpdated)) issue(['translationOf'], '译文须标记原文 ID 和所依据的更新日期');
  if (data.languages[0] === 'zh-CN' && (data.translationOf || data.sourceUpdated)) issue(['translationOf'], '原文不能指向自身译文');
  if (data.updated < data.published) issue(['updated'], '更新时间不能早于初次记录日期');
  if (data.updated > today || data.published > today) issue(['updated'], '内容日期不能在未来');
  if (data.status !== 'published') return;
  if (new Set(data.sources.map(s => s.independenceKey)).size < 2) {
    issue(['sources'], '公开条目须有至少两个独立证据来源；镜像和译文不能重复计数');
  }
  if (new Set(data.sources.map(s => s.url)).size !== data.sources.length) issue(['sources'], '来源 URL 不得重复');
  for (const s of data.sources) {
    if (s.accessed > today) issue(['sources'], '来源查阅日期不能在未来');
  }
  if (/待补|待填写|待核档|TODO|示例条目/.test(JSON.stringify(data))) issue(['summary'], '公开条目不能包含占位内容');
}

export const schemas = {
  facts: z.object({
    ...common, title: z.string().min(1),
    category: z.enum(['event', 'statistics', 'dossier', 'trial']).default('event'),
    regions: z.array(z.string()).default([]),
    dateStart: day.optional(), dateEnd: day.optional(),
    wikidata: z.string().regex(/^Q[1-9]\d*$/).optional()
  }).superRefine((data, ctx) => {
    validatePublic(data, ctx);
    if (data.dateEnd && (!data.dateStart || data.dateEnd < data.dateStart)) {
      ctx.addIssue({ code: 'custom', path: ['dateEnd'], message: '事件结束日期须不早于起始日期' });
    }
  }),
  claims: z.object({
    ...common, claim: z.string().min(1), claimContext: z.string().min(1),
    verdict: z.enum(['false', 'misleading', 'unsupported', 'partly-true', 'true'])
  }).superRefine(validatePublic),
  ledger: z.object({
    ...common, title: z.string().min(1), date: day, actor: z.string().min(1),
    kind: z.enum(['statement', 'apology', 'action', 'education', 'visit']).default('statement')
  }).superRefine(validatePublic)
};

export const isPublic = ({ data }) => data.status === 'published';
export const serializeJsonLd = value => JSON.stringify(value).replace(/</g, '\\u003c');
export const csvCell = value => {
  let text = String(value ?? '');
  if (/^[\s]*[=+@-]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
};
