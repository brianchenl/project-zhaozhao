import { spawnSync } from 'node:child_process';
import { readEntries } from './content-files.mjs';
const urls = new Set((await readEntries()).filter(e => e.data.status === 'published').flatMap(e => e.data.sources.map(s => s.url)));
let failed = 0;
for (const url of urls) {
  const result = spawnSync('curl', ['--location', '--silent', '--show-error', '--fail', '--max-time', '25', '--output', '/dev/null', '--write-out', '%{http_code}', url], { encoding: 'utf8' });
  console.log(`${result.status === 0 ? 'OK' : 'FAIL'} ${result.stdout} ${url}`);
  if (result.status !== 0) failed++;
}
console.log(`来源可达性检查：${urls.size - failed}/${urls.size}；HTTP 成功不代表内容准确或未变更。`);
process.exitCode = failed ? 1 : 0;
