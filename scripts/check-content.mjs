import { readEntries, validateBody, validateTranslations } from './content-files.mjs';
const entries = await readEntries();
entries.forEach(validateBody);
validateTranslations(entries);
console.log(`内容校验通过：${entries.filter(e => e.data.status === 'published').length} 条公开，${entries.filter(e => e.data.status !== 'published').length} 条非公开。`);
