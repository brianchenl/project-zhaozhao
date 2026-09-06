# 内容字段与引用说明

每篇条目由 YAML 字段和 Markdown 正文组成。模板保存在 `templates/`，不会被当作历史事实生成网页。

## 共同字段

| 字段 | 内容 |
| --- | --- |
| summary | 10—300字，完整表达结论与关键限定 |
| published / updated | 条目创建、实质修订日期，使用带引号的 YYYY-MM-DD |
| status | draft：资料草稿；reviewed：整理待确认；published：公开条目。仅 published 进入网页与导出 |
| languages | 单元素数组：zh-CN、zh-Hant、en、ja；外文原始来源不代表条目已有外文译本 |
| translationOf | 译文必填，同一集合内简体中文原文的文件名（不含 .md） |
| sourceUpdated | 译文必填，所依据原文的 updated 日期；原文实质修订后需同步译文 |
| sources | 结构化出处数组，公开条目至少有两个独立来源链 |

事实另有 title、category、regions、dateStart、dateEnd、wikidata；核查另有 claim、claimContext、verdict；台账另有 title、date、actor、kind。日期不是文献发现日期，也不要用条目更新时间替代历史事件时间。

## 来源结构

每项包含 title、url、publisher、independenceKey、locator 和 accessed。locator 写档案号、页码、文献段落或馆藏具体字段；accessed 写实际查阅日期。

independenceKey 表示证据形成来源。同一文书的译本、镜像和重印沿用相同标识；不要用任意不同字符串凑足来源数。机器只能核对字段和标识数量，独立性及内容准确性仍依赖资料判断。

正文用 `[出处1](#source-1)` 就近关联 sources 的第一项，以此类推；不要将一个只支持日期的来源用于支持伤亡数字。说明读取的是原文、馆藏著录还是其他层次。

## 正文结构

- 事实条目：事实与证据、范围与限制。
- 说法核查：判定依据、核查边界，明确命题来自原话还是编辑拟题。
- 台账：表态内容、独立回应、范围与限制。
- 统计条目：还需统计口径、数字适用范围和分歧说明；正文不能只列孤立数字。

## 校验与可见性

译文分别放在对应集合的 `zh-hant/`、`en/`、`ja/` 子目录中，文件名与原文一致。简体中文原文不填写 translationOf 和 sourceUpdated。翻译标题、摘要、正文、区域及人物说明，保留历史日期、判定、文献分类和实体标识。sources 的顺序、URL、independenceKey、accessed 必须与原文一致；出处题名可保留原文，定位说明可翻译。不能将同一文书的译本计作新增独立来源。

各语言必须使用 `src/lib/locales.mjs` 中的正文标题。公开译文必须有公开原文；来源不一致、事实字段变化或 sourceUpdated 落后会阻止校验通过。新增译文后，路由、语言切换、JSON-LD 和导出索引自动生成。涉及证据理解的翻译应由具备相关语言和主题能力的人审校；只在实际完成后记录审校状态。

`npm run verify` 检查字段、日期、占位文字、引用定位、译文同步、站内链接、语言标记、互相对应的 hreflang、结构化数据以及网页、sitemap、文本索引、JSON、CSV的一致性。

草稿过滤只控制生成站点，不隐藏 GitHub 源码或 Git 历史。内部计划放在被忽略的本地目录，不应写入内容条目。首批内容没有独立专家或双人审核记录，后续如有审核应按实际情况记录。
