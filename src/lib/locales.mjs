/** @typedef {'zh-CN' | 'zh-Hant' | 'en' | 'ja'} Locale */
/** @type {Locale[]} */
export const locales = ['zh-CN', 'zh-Hant', 'en', 'ja'];
export const translatedLocales = locales.slice(1);
export const prefixes = { 'zh-CN': '', 'zh-Hant': 'zh-hant', en: 'en', ja: 'ja' };
export const languageNames = { 'zh-CN': '简体中文', 'zh-Hant': '繁體中文', en: 'English', ja: '日本語' };
export const localeFromPrefix = prefix => locales.find(locale => prefixes[locale] === prefix);
export const localizedPath = (locale, path = '/') => `${prefixes[locale] ? '/' + prefixes[locale] : ''}${path}`;
export const baseId = entry => entry.data.translationOf ?? entry.id;
export const entryPath = entry => localizedPath(entry.data.languages[0], `/${entry.collection}/${baseId(entry)}/`);
export const contentHeadings = {
  'zh-CN': { facts: ['事实与证据', '范围与限制'], claims: ['判定依据', '核查边界'], ledger: ['表态内容', '范围与限制'], statistics: ['统计口径', '分歧说明'] },
  'zh-Hant': { facts: ['事實與證據', '範圍與限制'], claims: ['判定依據', '核查邊界'], ledger: ['談話內容', '範圍與限制'], statistics: ['統計口徑', '分歧說明'] },
  en: { facts: ['Facts and evidence', 'Scope and limitations'], claims: ['Basis for the verdict', 'Scope of this check'], ledger: ['Statement', 'Scope and limitations'], statistics: ['Statistical scope', 'Differences between estimates'] },
  ja: { facts: ['事実と根拠', '範囲と限界'], claims: ['判定の根拠', '検証の範囲'], ledger: ['談話の内容', '範囲と限界'], statistics: ['統計の対象範囲', '推計の相違'] }
};
