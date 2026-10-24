"""邮件里的平台文案区块与"缺了什么"的说明。

两条都关于同一件事：读者要能分清"没产出"和"产出了但没通过"。静默省略会让
这两种情况看起来一样，而它们的处理方式完全不同 —— 一个是配置没开，
一个是今天的图有缺陷。
"""

from __future__ import annotations

from html import escape

from app.publishers.formatting import format_body
from app.publishers.styles import PLATFORM_STYLES
from app.publishers.validation import CopyDraft


def _copy_text(draft: CopyDraft) -> str:
    """拼成可直接复制去发布的纯文本。"""
    parts = []
    if draft.title:
        parts.append(draft.title)
    if draft.thread:
        parts.extend(
            f"Thread {index}: {format_body(draft.platform, part)}"
            for index, part in enumerate(draft.thread, start=1)
        )
    else:
        parts.append(format_body(draft.platform, draft.body))
    if draft.hashtags:
        parts.append(" ".join(draft.hashtags))
    return "\n\n".join(part for part in parts if part)


def render_copy_section_html(
    accepted: dict[str, CopyDraft],
    truncated: set[str],
    failed: dict[str, list],
    attachment_names: dict[str, list[str]],
) -> str:
    """平台文案区块。放在正式摘要各节之后。"""
    if not accepted and not failed:
        return ""

    blocks = []
    for key, draft in accepted.items():
        style = PLATFORM_STYLES.get(key)
        name = escape(style.display_name if style else key)
        files = attachment_names.get(key) or []
        file_note = (
            f'<p style="color:#57606a;font-size:13px;margin:4px 0 8px;">配图附件：{escape(", ".join(files))}</p>'
            if files
            else '<p style="color:#57606a;font-size:13px;margin:4px 0 8px;">该平台以纯文本发布，无配图</p>'
        )
        trimmed_note = (
            '<p style="color:#bf8700;font-size:13px;margin:4px 0;">⚠️ 超出平台字数上限，已截断</p>'
            if key in truncated
            else ""
        )
        blocks.append(
            f"""
        <div style="background:#f6f8fa;border-radius:8px;padding:16px;margin-bottom:16px;border-left:4px solid #6e7781;">
            <h3 style="margin:0 0 8px;color:#24292f;">{name}</h3>
            {file_note}
            {trimmed_note}
            <pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;color:#24292f;margin:0;background:#ffffff;padding:12px;border-radius:6px;border:1px solid #d0d7de;">{escape(_copy_text(draft))}</pre>
        </div>"""
        )

    failure_block = ""
    if failed:
        rows = "".join(
            f"<li>{escape(PLATFORM_STYLES[key].display_name if key in PLATFORM_STYLES else key)}："
            f"{escape('; '.join(getattr(issue, 'detail', str(issue)) for issue in issues))}</li>"
            for key, issues in failed.items()
        )
        failure_block = f"""
        <div style="background:#fff8f0;border-radius:8px;padding:16px;margin-bottom:16px;border-left:4px solid #d1242f;">
            <h3 style="margin:0 0 8px;color:#d1242f;">未产出文案的平台</h3>
            <ul style="margin:4px 0;padding-left:20px;color:#24292f;font-size:14px;">{rows}</ul>
        </div>"""

    return f"""
    <div style="margin:32px 0;">
        <h2 style="color:#24292f;border-bottom:2px solid #6e7781;padding-bottom:8px;">各平台文案</h2>
        {"".join(blocks)}
        {failure_block}
    </div>"""


def render_withheld_html(withheld: list[tuple[str, str]], dropped: list[tuple[str, str]]) -> str:
    """点名被扣下的图与被丢弃的附件。

    静默省略会让读者无法区分"缺的资产"和"没做的资产"。
    """
    if not withheld and not dropped:
        return ""

    items = "".join(
        f"<li><strong>{escape(slug)}</strong>：{escape(reason)}</li>" for slug, reason in withheld
    ) + "".join(
        f"<li><strong>{escape(slug)}</strong>：{escape(reason)}</li>" for slug, reason in dropped
    )
    return f"""
    <div style="background:#fff8f0;border-radius:8px;padding:16px;margin:24px 0;border-left:4px solid #bf8700;">
        <h3 style="margin:0 0 8px;color:#9a6700;">本次未附上的图片</h3>
        <ul style="margin:4px 0;padding-left:20px;color:#24292f;font-size:14px;">{items}</ul>
    </div>"""


def render_copy_section_text(
    accepted: dict[str, CopyDraft],
    truncated: set[str],
    failed: dict[str, list],
) -> str:
    if not accepted and not failed:
        return ""

    lines = ["", "-" * 60, "各平台文案", "-" * 60, ""]
    for key, draft in accepted.items():
        style = PLATFORM_STYLES.get(key)
        lines.append(f"【{style.display_name if style else key}】" + ("（已截断）" if key in truncated else ""))
        lines.append(_copy_text(draft))
        lines.append("")
    for key, issues in failed.items():
        style = PLATFORM_STYLES.get(key)
        detail = "; ".join(getattr(issue, "detail", str(issue)) for issue in issues)
        lines.append(f"【{style.display_name if style else key}】未产出：{detail}")
    lines.append("")
    return "\n".join(lines)
