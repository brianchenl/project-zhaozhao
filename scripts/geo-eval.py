#!/usr/bin/env python3
"""Offline GEO observation helper (Python 3.9+, standard library only).

This measures explicit URL presence and a separate topic-keyword heuristic.
It does NOT implement GEO-Bench's citation-attributed PAWC, verify historical
accuracy, query AI engines, or prove indexing/training/content adoption.
See docs/internal/geo-eval-script.md for local operating instructions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import sys
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

KEYWORDS: dict[str, list[str]] = {
    # A 组：日本侵华核心
    "A1": ["1937", "12月13日", "6周", "南京大屠杀", "东京审判", "南京审判"],
    "A2": ["遇难人数", "20万", "30万", "14法庭", "国际委员会"],
    "A3": ["1945-08-15", "1945-09-02", "密苏里号", "投降书"],
    "A4": ["慰安妇", "强征", "河野谈话"],
    "A5": ["七三一", "731", "人体实验", "伯力审判"],
    # B 组：东南亚与太平洋
    "B1": ["新加坡", "大肃清", "山下奉文"],
    "B2": ["巴丹", "死亡行军", "美菲战俘"],
    "B3": ["泰缅铁路", "死亡铁路"],
    "B4": ["马尼拉", "大屠杀", "平民"],
    "B5": ["东南亚", "慰安妇"],
    # C 组：战后表态
    "C1": ["村山谈话", "侵略战争", "殖民地统治"],
    "C2": ["教科书", "1982", "2001"],
    "C3": ["河野谈话", "1993", "道歉"],
    "C4": ["国会", "道歉决议", "1995"],
    "C5": ["旧金山和约", "1951", "求偿"],
    # D 组：反叙事核查（关键词是"反叙事要被引用的措辞"）
    "D1": ["自卫", "亚洲解放"],
    "D2": ["夸大", "虚构", "南京事件"],
    "D3": ["商业行为", "公娼"],
    "D4": ["共荣圈", "解放亚洲"],
    "D5": ["靖国神社", "甲级战犯", "合祀"],
}


ENGINES = {"chatgpt", "perplexity", "yuanbao", "gemini"}
LANGUAGES = {"zh-CN", "zh-Hant", "en", "ja"}
METRIC_VERSION = "topic-keywords-v2"
SCHEMA_VERSION = 2
DATA_KINDS = {"unverified", "sample", "observed"}
# Only known repository paths. Unverified candidate deployment domains are excluded.
SOURCE_PREFIXES = [
    "https://github.com/brianchenl/project-zhaozhao",
    "https://raw.githubusercontent.com/brianchenl/project-zhaozhao",
]
HEADER = re.compile(r"^===\s*([^|]+)\|([^|]+)\|([^|]+)\|([^|]+?)\s*===$")
URL_RE = re.compile(r"""https?://[^\s<>"\]\)]+""", re.IGNORECASE)


def default_config() -> dict:
    # Do not score English/Japanese/Traditional Chinese using Simplified keywords.
    # Explicit URL detection still works in all four languages.
    return {"source_prefixes": SOURCE_PREFIXES[:], "keywords": {"zh-CN": copy.deepcopy(KEYWORDS)}}


def url_parts(value: str):
    """Compare exact hosts and canonical path boundaries, never substring hosts."""
    parsed = urlsplit(value)
    if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password):
        raise ValueError("来源须为无账号信息的 HTTP(S) URL")
    port = parsed.port
    if port not in (None, 443 if parsed.scheme.lower() == "https" else 80):
        raise ValueError("来源 URL 使用非标准端口")
    path = unquote(parsed.path)
    if "\\" in path or any(ord(c) < 32 for c in value):
        raise ValueError("来源 URL 包含不支持的字符")
    path = posixpath.normpath("/" + path.lstrip("/"))
    return parsed.hostname.lower().rstrip("."), path.rstrip("/")


def load_config(path: Optional[Path]) -> dict:
    config = default_config()
    if path is None:
        return config
    custom = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(custom, dict) or set(custom) - {"source_prefixes", "keywords"}:
        raise ValueError("配置只接受 source_prefixes 和 keywords")
    if "source_prefixes" in custom:
        prefixes = custom["source_prefixes"]
        if not isinstance(prefixes, list) or not prefixes or not all(isinstance(x, str) for x in prefixes):
            raise ValueError("source_prefixes 须为非空 URL 数组")
        for prefix in prefixes:
            url_parts(prefix)
            if urlsplit(prefix).query or urlsplit(prefix).fragment:
                raise ValueError("来源前缀不得带查询参数或片段")
        config["source_prefixes"] = prefixes
    dictionaries = custom.get("keywords", {})
    if not isinstance(dictionaries, dict):
        raise ValueError("keywords 须按语言、问题编号组织")
    for language, questions in dictionaries.items():
        if language not in LANGUAGES or not isinstance(questions, dict):
            raise ValueError("关键词语言或问题字典无效")
        config["keywords"].setdefault(language, {})
        for qid, words in questions.items():
            if (qid not in KEYWORDS or not isinstance(words, list)
                    or not all(isinstance(w, str) and normalize(w) for w in words)):
                raise ValueError(f"关键词配置无效：{language}/{qid}")
            config["keywords"][language][qid] = words
    return config


def config_id(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def iso_week(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期须为 YYYY-MM-DD")
    year, week, _ = date.fromisoformat(value).isocalendar()
    return f"{year:04d}-W{week:02d}"


def validate_week(week: str) -> None:
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError("周编号须为 YYYY-Www，不得包含路径")
    date.fromisocalendar(int(week[:4]), int(week[-2:]), 1)


@dataclass
class ResponseBlock:
    query_id: str
    engine: str
    date: str
    language: str
    prompt: str = ""
    response: str = ""
    sources: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    query_id: str
    engine: str
    language: str
    date: str
    score: Optional[int]
    matched_keywords: list[str]
    position_score: Optional[int]
    word_share_score: Optional[int]
    source_score: int
    zhaozhao_cited: bool
    word_share_pct: Optional[float]
    notes: str = ""
    matched_sources: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    prompt: str = ""
    response: str = ""
    schema_version: int = SCHEMA_VERSION
    metric_version: str = METRIC_VERSION
    config_id: str = ""
    data_kind: str = "unverified"


def identity(row: dict) -> tuple:
    return tuple(row[k] for k in ("date", "query_id", "engine", "language"))


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(m.group().rstrip(".,;，。；") for m in URL_RE.finditer(text)))


def parse_responses(text: str) -> list[ResponseBlock]:
    """Fail closed on malformed headers, missing sections, and duplicate runs."""
    blocks = []
    current = None
    sections = {}
    label = None

    def finish():
        if current is None:
            return
        if not all("".join(sections.get(key, [])).strip() for key in ("prompt", "response")):
            raise ValueError(f"{current.query_id}: [Prompt] 和 [Response] 均须有内容")
        current.prompt = "\n".join(sections["prompt"]).strip()
        current.response = "\n".join(sections["response"]).strip()
        for line in sections.get("sources", []):
            if not line.strip():
                continue
            urls = extract_urls(line)
            if not urls:
                raise ValueError(f"{current.query_id}: [SOURCES] 每个非空行须有 HTTP(S) URL")
            for url in urls:
                url_parts(url)
            current.sources.extend(urls)
        current.sources = list(dict.fromkeys(current.sources))
        blocks.append(current)

    for number, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        stripped = line.strip()
        match = HEADER.fullmatch(stripped)
        if match:
            finish()
            qid, engine, day, language = [s.strip() for s in match.groups()]
            engine = engine.lower()
            if qid not in KEYWORDS or engine not in ENGINES or language not in LANGUAGES:
                raise ValueError(f"第 {number} 行：未知题号、引擎或语言")
            iso_week(day)
            current = ResponseBlock(qid, engine, day, language)
            sections, label = {}, None
        elif stripped.startswith("==="):
            raise ValueError(f"第 {number} 行：块头格式错误")
        elif stripped.lower() in {"[prompt]", "[response]", "[sources]"}:
            label = stripped[1:-1].lower()
            if current is None or label in sections:
                raise ValueError(f"第 {number} 行：标签重复或位于块头之前")
            sections[label] = []
        elif current is None or label is None:
            if stripped:
                raise ValueError(f"第 {number} 行：块或标签之外存在未归属内容")
        else:
            sections[label].append(line)
    finish()
    if not blocks:
        raise ValueError("未解析到回答块")
    keys = [identity(asdict(b)) for b in blocks]
    if len(set(keys)) != len(keys):
        raise ValueError("同日、题号、引擎、语言重复；请保留一次观测或分开数据集")
    return blocks


def normalize(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def is_project_url(url: str, prefixes: list[str]) -> bool:
    try:
        host, path = url_parts(url)
        for prefix in prefixes:
            expected_host, expected_path = url_parts(prefix)
            if host == expected_host and (path == expected_path or path.startswith(expected_path + "/")):
                return True
    except ValueError:
        return False
    return False


def score_response(block: ResponseBlock, config: Optional[dict] = None,
                   data_kind: str = "unverified") -> ScoreResult:
    config = config if config is not None else default_config()
    sources = list(dict.fromkeys(block.sources + extract_urls(block.response)))
    cited = [url for url in sources if is_project_url(url, config["source_prefixes"])]
    # Remove URL text from topic matching; a keyword in a URL is not answer text.
    response = normalize(URL_RE.sub("", block.response))
    keywords = config["keywords"].get(block.language, {}).get(block.query_id)
    matched, spans = [], []
    for word in keywords or []:
        needle = normalize(word)
        if not needle:
            continue
        occurrences = list(re.finditer(re.escape(needle), response))
        if occurrences:
            matched.append(word)
            spans.extend((m.start(), m.end()) for m in occurrences)
    # Union intervals: overlapping keywords never push coverage above 100%.
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    length = len(response)
    share = sum(end - start for start, end in merged) / max(length, 1) * 100
    position = int(bool(spans) and min(s for s, _ in spans) < length / 3)
    share_point = int(share >= 20)
    score = min(3, int(bool(matched)) + position + share_point)
    if length < 30:
        score = min(score, 1)
    elif length < 80:
        score = min(score, 2)
    notes = "本地主题启发式；不代表引用归属、事实正确性或观点立场。"
    if not keywords:
        score = position = share_point = share = None
        notes += "当前语言/题号无关键词配置，主题评分 N/A。"
    if block.query_id.startswith("D"):
        notes += "D组须人工区分赞同、转述与反驳，不能据关键词判断立场。"
    return ScoreResult(
        query_id=block.query_id, engine=block.engine, language=block.language, date=block.date,
        score=score, matched_keywords=matched, position_score=position,
        word_share_score=share_point, source_score=int(bool(cited)), zhaozhao_cited=bool(cited),
        word_share_pct=round(share, 2) if share is not None else None, notes=notes,
        matched_sources=cited, sources=sources, prompt=block.prompt, response=block.response,
        config_id=config_id(config), data_kind=data_kind,
    )


def render_record_yaml(results: list[ScoreResult], blocks: list[ResponseBlock]) -> str:
    # JSON is a YAML 1.2 subset: safely preserves dates, numeric keywords and multiline text.
    by_key = {identity(asdict(b)): b for b in blocks}
    rows = []
    for result in results:
        row = asdict(result)
        b = by_key.get(identity(row))
        if b:
            row.update(prompt=b.prompt, response=b.response, sources_cited=b.sources)
        row["week"] = iso_week(row["date"])
        rows.append(row)
    return json.dumps({"schema_version": SCHEMA_VERSION, "records": rows}, ensure_ascii=False, indent=2) + "\n"


def render_weekly_markdown(results: list[ScoreResult], week: str) -> str:
    scored = [r for r in results if r.score is not None]
    total = sum(r.score for r in scored)
    cited = sum(r.zhaozhao_cited for r in results)
    kinds = ", ".join(sorted({r.data_kind for r in results}))
    out = [f"# GEO 观测周报 {week}", "", f"数据性质：{kinds or '无数据'}",
           f"指标版本：{METRIC_VERSION}；配置：{', '.join(sorted({r.config_id for r in results}))}",
           "", "> 仅离线处理提供的文本；未调用 AI 引擎。sample 为演示，unverified 为来源未确认；"
           "observed 仅表示提交者声明为实测。链接出现不证明自然发现、有效引用或内容被吸收。",
           "", f"- 样本数：{len(results)}",
           f"- 可评分样本：{len(scored)} / {len(results)}",
           f"- 主题启发式总分：{total} / {len(scored) * 3}（不是 PAWC 或 GEO 收益）",
           f"- 明确项目链接出现：{cited} / {len(results)}",
           "- 未采样组合不按 0 分处理；无语言词表显示 N/A。",
           "", "## 分语言、问题与引擎", "",
           "| 语言 | 题号 | 引擎 | 样本数 | 主题均分 / 3 | 项目链接出现 |",
           "| --- | --- | --- | --- | --- | --- |"]
    groups = defaultdict(list)
    for r in results:
        groups[(r.language, r.query_id, r.engine)].append(r)
    for (language, qid, engine), group in sorted(groups.items()):
        values = [r.score for r in group if r.score is not None]
        average = f"{sum(values) / len(values):.2f}" if values else "N/A"
        out.append(f"| {language} | {qid} | {engine} | {len(group)} | {average} | "
                   f"{sum(r.zhaozhao_cited for r in group)}/{len(group)} |")
    out += ["", "## 人工复核提示", "", render_alerts(results), "",
            "先核对数据真实性、采样模式、链接及其支持关系，再判断内容是否需要修改。"
            "没有匹配或没有链接不代表答案错误；不要为提高分数堆词、添加无依据数字或改变历史结论。",
            "", "趋势比较须固定题目、提示词、引擎版本、搜索模式、语言和采样方式。"
            "当前块格式未结构化记录模型版本、搜索开关或会话来源，应在采样时另行保存；"
            "无法确认同条件时不作因果推断。", ""]
    return "\n".join(out)


def render_alerts(results: list[ScoreResult]) -> str:
    if not results:
        return "无观测数据；不能解释为没有预警。"
    out = []
    for r in results:
        prefix = f"- {r.query_id} / {r.engine} / {r.language} / {r.date}"
        flags = []
        if not r.zhaozhao_cited:
            flags.append("未检测到配置范围内的项目链接")
        if r.score is None:
            flags.append("主题评分 N/A（无语言词表）")
        elif r.score == 0:
            flags.append("主题关键词未匹配（不等于未引用）")
        if r.query_id.startswith("D"):
            flags.append("需人工判断立场")
        if flags:
            out.append(prefix + "：" + "；".join(flags))
    notice = "数据性质：" + ", ".join(sorted({r.data_kind for r in results})) + "。未匹配链接不等于答案错误。"
    return notice + "\n\n" + ("\n".join(out) if out else "未发现自动检查项；仍须人工核对引用与事实。")


def atomic_write(path: Path, text: str) -> None:
    """Replace one generated file atomically; retain content-addressed backup on change."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        previous = path.read_bytes()
        if previous == text.encode("utf-8"):
            return
        digest = hashlib.sha256(previous).hexdigest()[:16]
        backup = path.parent / ".backups" / f"{path.name}.{digest}.bak"
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_bytes(previous)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name, delete=False) as f:
            temporary = Path(f.name)
            f.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_history(records_dir: Path, week: str, results: list[ScoreResult]) -> None:
    """A complete weekly snapshot, NOT an append-only log. Re-running is idempotent."""
    validate_week(week)
    rows = []
    for r in results:
        if iso_week(r.date) != week:
            raise ValueError(f"记录日期 {r.date} 不属于 {week}")
        rows.append(dict(asdict(r), week=week))
    atomic_write(records_dir / week / "history.jsonl",
                 "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))


def load_history(records_dir: Path) -> list[dict]:
    rows = []
    if not records_dir.exists():
        return rows
    for directory in sorted(records_dir.iterdir()):
        if not directory.is_dir() or not re.fullmatch(r"\d{4}-W\d{2}", directory.name):
            continue
        validate_week(directory.name)
        path = directory / "history.jsonl"
        if not path.exists():
            continue
        seen = set()
        legacy = 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("记录不是对象")
                if "schema_version" not in row:
                    legacy += 1
                    continue
                if row["schema_version"] != SCHEMA_VERSION:
                    raise ValueError("不支持的记录版本")
                result = ScoreResult(**{k: row[k] for k in ScoreResult.__dataclass_fields__})
                if (row.get("week") != directory.name or iso_week(result.date) != directory.name
                        or result.engine not in ENGINES or result.language not in LANGUAGES
                        or result.query_id not in KEYWORDS or result.data_kind not in DATA_KINDS
                        or (result.score is not None and (type(result.score) is not int or not 0 <= result.score <= 3))
                        or type(result.zhaozhao_cited) is not bool):
                    raise ValueError("记录字段、分数或所属周无效")
                key = identity(row)
                if key in seen:
                    raise ValueError("重复历史记录")
                seen.add(key)
                rows.append(row)
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(f"{path.name} ({directory.name}) 第 {number} 行：{e}") from e
        if legacy:
            print(f"警告：{directory.name} 跳过 {legacy} 条旧版记录；请用原始输入重算，不能混合旧分数。",
                  file=sys.stderr)
    return rows


def render_trend(history: list[dict], weeks: int) -> str:
    if weeks < 1:
        raise ValueError("--weeks 必须大于 0")
    if not history:
        return "无历史数据"
    # N calendar weeks ending at the newest sample, not N distinct observation days.
    latest = max(date.fromisocalendar(int(r["week"][:4]), int(r["week"][-2:]), 1) for r in history)
    groups = defaultdict(list)
    for r in history:
        monday = date.fromisocalendar(int(r["week"][:4]), int(r["week"][-2:]), 1)
        if (latest - monday).days < weeks * 7:
            groups[(r["week"], r["metric_version"], r["config_id"], r["data_kind"], r["language"])].append(r)
    out = [f"# 最近 {weeks} 个日历周观测（截止 {iso_week(latest.isoformat())}）", "",
           "按指标版本、配置、数据性质及语言隔离；缺失周不补零，不保证跨周采样条件相同。",
           "", "| 周 | 指标 / 配置 | 数据性质 | 语言 | 样本数 | 主题均分 / 3 | 项目链接出现 |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for (week, metric, config, kind, language), rows in sorted(groups.items()):
        scores = [r["score"] for r in rows if r["score"] is not None]
        average = f"{sum(scores) / len(scores):.2f}" if scores else "N/A"
        out.append(f"| {week} | {metric} / {config} | {kind} | {language} | {len(rows)} | {average} | "
                   f"{sum(r['zhaozhao_cited'] for r in rows)}/{len(rows)} |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="离线 GEO 观测：项目链接检测 + 主题关键词启发式（非 PAWC）")
    parser.add_argument("--week", help="ISO 周，如 2026-W37")
    parser.add_argument("--input", type=Path, help="原始回答文本")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--alerts", action="store_true", help="只读预警；无 input 时读取该周历史")
    mode.add_argument("--trend", action="store_true", help="只读跨周趋势")
    parser.add_argument("--weeks", type=int, default=8)
    parser.add_argument("--records-dir", type=Path, default=Path(__file__).resolve().parent.parent / "records")
    parser.add_argument("--config", type=Path, help="JSON：来源路径前缀及分语言关键词")
    parser.add_argument("--data-kind", choices=sorted(DATA_KINDS), default="unverified")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    args = parser.parse_args()
    try:
        if args.weeks < 1:
            raise ValueError("--weeks 必须大于 0")
        if args.trend:
            if args.week or args.input or args.config or args.dry_run or args.data_kind != "unverified":
                raise ValueError("--trend 不与单周输入、配置或数据性质参数组合")
            print(render_trend(load_history(args.records_dir), args.weeks))
            return 0
        if not args.week:
            raise ValueError("须指定 --week（或使用 --trend）")
        validate_week(args.week)
        if args.alerts and args.input is None:
            if args.config or args.data_kind != "unverified":
                raise ValueError("读取既有预警不重新配置或改变数据性质")
            rows = [r for r in load_history(args.records_dir) if r["week"] == args.week]
            if not rows:
                raise ValueError("该周无新版历史；请提供 --input 重新检查")
            results = [ScoreResult(**{k: r[k] for k in ScoreResult.__dataclass_fields__}) for r in rows]
            print(render_alerts(results))
            return 0
        if args.input is None:
            raise ValueError("完整评分须指定 --input")
        config = load_config(args.config)
        text = args.input.read_text(encoding="utf-8")
        blocks = parse_responses(text)
        for block in blocks:
            actual = iso_week(block.date)
            if actual != args.week:
                raise ValueError(f"日期 {block.date} 属于 {actual}，与 --week {args.week} 不符；未写入文件")
        results = [score_response(b, config, args.data_kind) for b in blocks]
        if args.alerts:
            print(render_alerts(results))
            return 0
        report = render_weekly_markdown(results, args.week)
        print(report)
        if not args.dry_run:
            week_dir = args.records_dir / args.week
            destinations = [week_dir / name for name in ("record.yaml", "weekly.md", "history.jsonl")]
            if args.input.resolve() in [p.resolve() for p in destinations]:
                raise ValueError("输出文件不能覆盖原始输入")
            atomic_write(destinations[0], render_record_yaml(results, blocks))
            atomic_write(destinations[1], report)
            save_history(args.records_dir, args.week, results)
            print(f"已写入 {week_dir}；整周快照，重复运行不累加；变更前版本保存在 .backups/。")
        return 0
    except (OSError, ValueError, TypeError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
