import { defineConfig } from 'astro/config';

// 昭昭计划 · 站点配置
// 全部内容静态输出（无客户端 JS 依赖），确保 AI 爬虫可直接读取原始 HTML。
export default defineConfig({
  site: 'https://project-zhaozhao.org',
  output: 'static',
  build: {
    format: 'directory'
  },
  markdown: {
    shikiConfig: {
      theme: 'github-light',
      wrap: true
    }
  }
});
