"""平台文案生成：一次主调用产出全部六个平台。

正常路径只调用一次：六次独立调用不仅贵六倍，还会让六份文案互相不知道对方
说了什么。生成后全部经过 `validate_copy`；若只有部分平台不合格，再针对这些
平台做一次有明确错误反馈的修正调用，已经通过的文案保持不动。

修正结果仍走同一套长度与接地校验。两次都失败的平台会在邮件里点名，不做本地
静默改写，因为悄悄改正会把一次幻觉变成一条看不见的事实错误。
"""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.publishers.formatting import format_draft
from app.publishers.styles import PlatformStyle, enabled_styles
from app.publishers.validation import (
    CopyDraft,
    CopyIssue,
    Grounding,
    enforce_limits,
    validate_copy,
)

logger = logging.getLogger(__name__)


def _style_brief(style: PlatformStyle) -> str:
    rules = style.copy
    lines = [
        f"### {style.key}（{style.display_name}）",
        f"- 语言：{rules.language}",
        f"- 调性：{rules.tone}",
        f"- 结构：{rules.structure}",
        f"- 正文上限：{rules.body_max_chars} 字"
        + ("（CJK 按两个字符计）" if rules.counts_cjk_as_two else ""),
    ]
    if rules.title_max_chars is not None:
        lines.append(f"- 标题上限：{rules.title_max_chars} 字")
    else:
        lines.append("- 无独立标题字段，title 留空字符串")
    if rules.allow_hashtags:
        lines.append(f"- 标签：{rules.hashtag_min}–{rules.hashtag_max} 个，放在 hashtags 数组里")
    else:
        lines.append("- 不使用标签，hashtags 必须是空数组，正文里也不要出现 #")
    return "\n".join(lines)


def build_copy_prompt(styles: list[PlatformStyle], items: list[dict], digest_label: str) -> str:
    """一次性描述全部平台要求 + 当天可用的事实。"""
    facts = []
    for index, item in enumerate(items, 1):
        name = item.get("repo_name") or item.get("title") or ""
        url = item.get("repo_url") or item.get("arxiv_url") or item.get("video_url") or ""
        summary = item.get("summary") or item.get("why_trending") or item.get("description") or ""
        stars = item.get("stars")
        star_text = f"，stars={stars}" if isinstance(stars, int) else ""
        facts.append(f"{index}. {name}｜{url}{star_text}\n   {summary}")

    platform_briefs = "\n\n".join(_style_brief(style) for style in styles)
    keys = ", ".join(style.key for style in styles)

    return f"""你是一个技术内容编辑。基于下面 {digest_label} 的摘要事实，为多个平台各写一份文案。

## 当天可用事实（这是全部可引用的内容）
{chr(10).join(facts)}

## 硬性约束
1. 只能使用上面列出的链接。不要写出任何其他 URL，包括看起来合理的仓库地址。
2. 只能引用上面出现过的数字。不确定的数字就不写，不要估算。
3. 每个平台按各自的调性与结构写，不要把同一段文字换个标点复制六遍。
4. 严格遵守各平台的长度与标签规则；长度计算包含你输出的换行符。
5. 所有句子必须完整。禁止使用省略号、连续句点或中文连续句号代替被删内容。
6. 正文必须有可复制的结构：不同段落之间使用 `\\n\\n`，列表项目各占一行；不要把整篇正文输出成没有换行的一长串。
7. 标题必须是该平台适合传播的明确钩子或问题式标题，但不得夸大、虚构数字、虚构结论或使用标题党承诺；标题也必须在平台上限内。
8. X 必须输出有序 `thread` 数组，每个元素是一条独立帖子且不超过 280 加权字符；不要把多条帖子拼成一个超长 body。

## 各平台要求
{platform_briefs}

## 输出格式
只输出 JSON，键为平台 key（{keys}），值为对象：
{{"<platform>": {{"title": "<完整标题>", "body": "<段落1>\\n\\n<段落2>", "hashtags": ["#标签"]}}, "x": {{"title": "", "thread": ["<第1条>", "<第2条>"], "hashtags": []}}}}
不要输出 JSON 以外的任何内容。"""


def _parse_copy_response(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("文案响应中没有 JSON 对象")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("文案响应顶层不是对象")
    return payload


def drafts_from_payload(payload: dict, styles: list[PlatformStyle]) -> dict[str, CopyDraft]:
    drafts: dict[str, CopyDraft] = {}
    for style in styles:
        entry = payload.get(style.key)
        if not isinstance(entry, dict):
            continue
        tags = entry.get("hashtags") or []
        raw_thread = entry.get("thread") if style.key == "x" else None
        thread = (
            tuple(str(part).strip() for part in raw_thread if str(part).strip())
            if isinstance(raw_thread, list)
            else ()
        )
        body = str(entry.get("body") or "").strip()
        if thread:
            body = "\n\n".join(thread)
        drafts[style.key] = format_draft(
            CopyDraft(
                platform=style.key,
                title=str(entry.get("title") or "").strip(),
                body=body,
                hashtags=tuple(str(tag).strip() for tag in tags if str(tag).strip()),
                thread=thread,
            )
        )
    return drafts


class CopyResult:
    """一次文案生成的产物。

    分成三类而不是两类：通过、修长度后通过、失败。中间那类要在邮件里说明
    被截断过，否则读者会以为那就是模型写出来的完整版本。
    """

    def __init__(self) -> None:
        self.accepted: dict[str, CopyDraft] = {}
        self.truncated: set[str] = set()
        self.failed: dict[str, list[CopyIssue]] = {}
        self.skipped: list[str] = []

    def summary(self) -> str:
        parts = [f"通过={len(self.accepted)}"]
        if self.truncated:
            parts.append(f"截断后通过={len(self.truncated)}")
        if self.failed:
            parts.append("失败=" + ",".join(sorted(self.failed)))
        if self.skipped:
            parts.append("未启用=" + ",".join(self.skipped))
        return " | ".join(parts)


async def generate_platform_copy(
    items: list[dict],
    digest_label: str,
    *,
    generate=None,
) -> CopyResult:
    """产出全部启用平台的文案。

    `generate` 是文本角色的调用函数，注入以便测试。默认用 gemini_analyzer ——
    它就是文本角色，不会碰图片。
    """
    result = CopyResult()

    all_keys = settings.publish_platforms_list
    styles = enabled_styles(all_keys)
    from app.publishers.styles import PLATFORM_STYLES

    # 关闭的平台不产出文案，且不算失败
    result.skipped = [key for key in PLATFORM_STYLES if key not in all_keys]

    if not settings.publishers_enabled or not styles or not items:
        return result

    if generate is None:
        from app.agents.gemini_analyzer import gemini_analyzer

        if not gemini_analyzer.is_available:
            logger.warning("文本角色不可用，跳过文案生成")
            return result
        generate = gemini_analyzer._generate_content  # noqa: SLF001 - 同包内的文本角色入口

    prompt = build_copy_prompt(styles, items, digest_label)
    try:
        raw = await generate(prompt)
        payload = _parse_copy_response(raw)
    except Exception as exc:  # noqa: BLE001 - 文案失败不阻断邮件
        logger.error("文案生成失败: %s", exc)
        for style in styles:
            result.failed[style.key] = [CopyIssue("generation", f"生成失败: {exc}")]
        return result

    grounding = Grounding.from_items(items)
    drafts = drafts_from_payload(payload, styles)

    def _evaluate(style: PlatformStyle, draft: CopyDraft | None) -> None:
        result.accepted.pop(style.key, None)
        result.truncated.discard(style.key)
        if draft is None or not draft.body:
            result.failed[style.key] = [CopyIssue("body", "模型未返回该平台文案")]
            return

        issues = validate_copy(draft, style, grounding)
        length_issues = [i for i in issues if i.field in {"title", "body", "hashtags"}]
        other_issues = [i for i in issues if i.field not in {"title", "body", "hashtags"}]

        if other_issues:
            # 接地问题不截断、不修改 —— 静默修改会把幻觉变成看不见的事实错误
            result.failed[style.key] = issues
            return

        if length_issues:
            trimmed = enforce_limits(draft, style)
            remaining = validate_copy(trimmed, style, grounding)
            if remaining:
                result.failed[style.key] = remaining
                return
            result.accepted[style.key] = trimmed
            result.truncated.add(style.key)
            result.failed.pop(style.key, None)
            return

        result.accepted[style.key] = draft
        result.failed.pop(style.key, None)

    for style in styles:
        _evaluate(style, drafts.get(style.key))

    failed_styles = [style for style in styles if style.key in result.failed]
    if failed_styles:
        feedback = {
            style.key: [f"{issue.field}: {issue.detail}" for issue in result.failed[style.key]]
            for style in failed_styles
        }
        repair_prompt = build_copy_prompt(failed_styles, items, digest_label) + (
            "\n\n## 上一版校验失败\n"
            + json.dumps(feedback, ensure_ascii=False)
            + "\n只重新生成上述失败平台，并修正这些问题。仍然只输出 JSON。"
        )
        try:
            repaired_payload = _parse_copy_response(await generate(repair_prompt))
            repaired_drafts = drafts_from_payload(repaired_payload, failed_styles)
        except Exception as exc:  # noqa: BLE001 - 保留首轮失败原因供邮件点名
            logger.warning("失败平台文案修正调用失败，保留首轮校验结果: %s", exc)
        else:
            for style in failed_styles:
                _evaluate(style, repaired_drafts.get(style.key))

    logger.info("平台文案 | %s", result.summary())
    return result
