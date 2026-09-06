import messages from '../i18n/ui.json';
export type Locale = keyof typeof messages;
export const t = (locale: string = 'zh-CN') => messages[locale as Locale];
export const countText = (text: string, count: number) => text.replace('{count}', String(count));
