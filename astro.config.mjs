import { defineConfig } from 'astro/config';

// 昭昭计划 · 站点配置
// 全部内容静态输出（无客户端 JS 依赖），确保 AI 爬虫可直接读取原始 HTML。
//
// site 必须是最终对外访问的规范域名：canonical、sitemap、llms.txt、hreflang
// 全部由此推导。改域名时只改这一行，不要在各处硬编码。
export default defineConfig({
  site: 'https://settledrecord.com',
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
