"""把摘要变成可发的资产：长图、平台图、平台文案、附件。

这一层的存在理由是"每一步都能独立失败"。渲染、生图、质检、文案四个环节各自
依赖一个外部系统（浏览器、Ark、Kimi、文本模型），任何一个挂掉都不能导致
今天的摘要邮件不发 —— 邮件每天到达比图片好看重要得多。

所以这里几乎没有向上抛的异常：每个环节包在自己的 try 里，失败落成"这张图
没有"并被点名，然后继续走下一环节。被点名是关键 —— 静默省略会让读者分不清
"今天没做这张图"和"今天这张图有缺陷"，而这两件事的处理方式完全不同。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from app.config import settings
from app.publishers.copy_generator import CopyResult, generate_platform_copy
from app.publishers.email_sections import (
    render_copy_section_html,
    render_copy_section_text,
    render_withheld_html,
)
from app.publishers.styles import PlatformStyle, enabled_styles, platform_of_slug
from app.publishers.templates import build_page_specs, expected_texts, render_page_html
from app.services.attachment_budget import (
    LONG_IMAGE_SLUG,
    Attachment,
    apply_budget,
    attachment_filename,
)
from app.services.delivery_encoding import delivery_extension, encode_for_delivery
from app.services.font_check import FontUnavailableError, font_stack, verify_fonts_or_raise
from app.services.image_generation import resolve_backgrounds
from app.services.image_renderer import LongImageRenderer
from app.services.qa_gate import Correction, run_gate
from app.services.visual_qa import Verdict, visual_qa

logger = logging.getLogger(__name__)


@dataclass
class AssetBundle:
    """一次运行产出的、可以直接交给邮件的东西。

    withheld 与 dropped 分开：前者是"做了但没通过质检"，后者是"通过了但装不进
    邮件体积"。两者都必须在邮件里说明，但原因不同，读者的下一步动作也不同。
    """

    attachments: list[Attachment] = field(default_factory=list)
    withheld: list[tuple[str, str]] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)
    copy_result: CopyResult | None = None
    copy_section_html: str = ""
    copy_section_text: str = ""
    withheld_html: str = ""
    long_image_path: Path | None = None
    written_paths: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        """记录一次省略。每个可选环节被跳过的原因都要能从日志里读到。"""
        self.notes.append(message)
        logger.info("资产环节省略：%s", message)


def _run_dir(digest_label: str) -> Path:
    path = Path(settings.render_output_dir) / digest_label
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _inspect(image_bytes: bytes, texts: list[str]) -> Verdict:
    """送检一张图。视觉质检关闭时抛 VisionUnavailable 而不是返回通过。

    "没检查"和"检查通过"必须区别对待，否则质检形同不存在。
    """
    return await visual_qa.inspect(image_bytes, texts)


async def build_platform_images(
    style: PlatformStyle,
    items: list[dict],
    digest_label: str,
    *,
    font_family: str,
    renderer: LongImageRenderer | None = None,
    already_generated: int = 0,
) -> tuple[list[Attachment], list[tuple[str, str]], int]:
    """产出一个平台的全部图片，返回（通过的附件, 被扣下的, 新增生成张数）。

    每张图独立走质检循环：一张被扣下不影响同组其他图。整组一起扣会把一个
    局部缺陷放大成"今天没有小红书图"。
    """
    specs = build_page_specs(style, items, digest_label)
    if not specs:
        return [], [], 0

    topics = [it.get("repo_name") or it.get("title") or "" for it in items]
    backgrounds, generated = await resolve_backgrounds(
        style, topics, digest_label, len(specs), already_generated=already_generated
    )

    attachments: list[Attachment] = []
    withheld: list[tuple[str, str]] = []

    for spec, background in zip(specs, backgrounds):
        page_renderer = renderer if renderer is not None else LongImageRenderer(
            viewport_width=spec.width
        )
        # 送检文本必须来自**这一次**渲染的规格。修正只调整字号、字体和分页，
        # 不再截断字段；holder 保证渲染与检查始终引用同一份完整文本。
        current_texts: list[str] = expected_texts(spec)

        async def _render(correction: Correction, spec=spec, background=background) -> bytes:
            adjusted = build_page_specs(
                style,
                items,
                digest_label,
                correction.type_scale,
                truncation_attempt=correction.truncation_attempt,
                content_reduction=correction.content_reduction,
            )
            current = next((s for s in adjusted if s.slug == spec.slug), spec)
            current_texts[:] = expected_texts(current)
            stack = font_stack() if correction.use_fallback_font else font_family
            html = render_page_html(current, style, stack, background.data_url)
            out = _run_dir(digest_label) / f"{spec.slug}.png"
            await page_renderer.render_frame(html, out, current.width, current.height)
            # 投递编码放在送检**之前**：质检看到的必须就是收件人收到的字节。
            # 反过来做（检 PNG、发 JPEG）等于质检的对象不是交付物 —— 压缩产生的
            # 字缘退化恰好属于质检该管的那一类缺陷。
            return encode_for_delivery(out.read_bytes(), spec.slug)

        result = await run_gate(
            spec.slug,
            _render,
            lambda image, texts=current_texts: _inspect(image, list(texts)),
            expected_texts=current_texts,
        )
        if result.passed and result.image is not None:
            attachments.append(
                Attachment(
                    slug=spec.slug,
                    filename=attachment_filename(
                        spec.slug,
                        digest_label,
                        delivery_extension(spec.slug, result.image),
                    ),
                    content=result.image,
                )
            )
        else:
            categories = "、".join(d.value for d in result.defect_categories)
            reason = result.withheld_reason + (f"（缺陷：{categories}）" if categories else "")
            withheld.append((spec.slug, reason))

    return attachments, withheld, generated


class _VisibleTextCollector(HTMLParser):
    """从正式摘要 HTML 提取视觉模型要逐项核对的可见文本节点。"""

    _HIDDEN = {"style", "script", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self._HIDDEN:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._HIDDEN and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        text = " ".join(data.split())
        if text:
            self.texts.append(text)


def _visible_texts(html: str) -> list[str]:
    """按 DOM 顺序返回去重后的可见文本，供长图完整性检查。"""
    parser = _VisibleTextCollector()
    parser.feed(html)
    # 保序去重。邮件模板里移动端/桌面端可能重复同一标签；重复列给模型只会浪费
    # 上下文，不会增加完整性证据。
    return list(dict.fromkeys(parser.texts))


def _correct_long_html(html: str, correction: Correction) -> str:
    """把 QA 的定向修正落实到长图，而不是用相同 HTML 原地重试。"""
    if correction.signature() == Correction().signature():
        return html

    factor = correction.type_scale.factor
    # 长图没有固定高度，illegible 时应把字放大、让页面变长；平台图才需要减内容。
    factor *= 1.08 ** correction.content_reduction
    # clipped/overflow 对应 truncation_attempt。正式摘要不能截内容，用轻微整体收紧代替。
    factor *= 0.96 ** correction.truncation_attempt
    declarations = [
        f"html {{ zoom: {factor:.4f}; }}",
        f"body {{ width: {100 / factor:.4f}% !important; }}",
        "* { overflow-wrap: anywhere; }",
    ]
    if correction.use_fallback_font:
        declarations.append(f"* {{ font-family: {font_stack()} !important; }}")
    style = "<style data-longimage-correction>" + "".join(declarations) + "</style>"
    return html.replace("</head>", style + "</head>", 1) if "</head>" in html else style + html


async def _build_long_image(
    html: str, digest_label: str, bundle: AssetBundle
) -> Attachment | None:
    """长图也走视觉准出门；未经检查或失败时扣下，不阻断正文邮件。"""
    if not visual_qa.is_available:
        bundle.withheld.append((LONG_IMAGE_SLUG, "视觉质检未启用或未配置，未经检查的长图不发"))
        return None

    renderer = LongImageRenderer()
    out = _run_dir(digest_label) / f"{attachment_filename(LONG_IMAGE_SLUG, digest_label)}"
    expected = _visible_texts(html)

    async def _render(correction: Correction) -> bytes:
        corrected_html = _correct_long_html(html, correction)
        await renderer.render(corrected_html, out)
        if out not in bundle.written_paths:
            bundle.written_paths.append(out)
        bundle.long_image_path = out
        return out.read_bytes()

    result = await run_gate(
        LONG_IMAGE_SLUG,
        _render,
        lambda image: _inspect(image, expected),
        expected_texts=expected,
    )
    if not result.passed or result.image is None:
        categories = "、".join(defect.value for defect in result.defect_categories)
        reason = result.withheld_reason + (f"（缺陷：{categories}）" if categories else "")
        bundle.withheld.append((LONG_IMAGE_SLUG, reason))
        return None

    return Attachment(
        slug=LONG_IMAGE_SLUG,
        filename=attachment_filename(LONG_IMAGE_SLUG, digest_label),
        content=result.image,
    )


async def build_assets(
    *,
    digest_html: str,
    items: list[dict],
    digest_label: str,
) -> AssetBundle:
    """跑完所有可选环节，返回可以直接交给邮件的一束东西。

    这个函数不抛异常。每个环节都包在自己的 try 里，因为它们依赖四个互不相干的
    外部系统；把它们串成一条会抛的链，等于让任何一个外部故障吃掉今天的邮件。
    """
    bundle = AssetBundle()
    started = time.monotonic()
    attachments: list[Attachment] = []

    # 1. 长图
    if not settings.render_enabled:
        bundle.note("长图渲染未启用（RENDER_ENABLED=false）")
    else:
        try:
            long_image = await _build_long_image(digest_html, digest_label, bundle)
            if long_image is not None:
                attachments.append(long_image)
        except FontUnavailableError as exc:
            bundle.note(f"长图未渲染：{exc}")
            bundle.withheld.append((LONG_IMAGE_SLUG, f"字体自检未通过：{exc}"))
        except Exception as exc:  # noqa: BLE001 - 渲染失败不阻断邮件
            logger.error("长图渲染失败: %s", exc, exc_info=True)
            bundle.withheld.append((LONG_IMAGE_SLUG, f"渲染失败：{exc}"))

    # 2. 平台图。质检关闭时不产出 —— 未经检查的图不发，这正是本次改动的要点。
    platform_font: str = ""
    if not settings.render_enabled:
        platform_font = ""
    elif not visual_qa.is_available:
        bundle.note("视觉质检未启用或未配置，平台图不产出（未经检查的图不发）")
    else:
        try:
            platform_font = font_stack(verify_fonts_or_raise())
        except FontUnavailableError as exc:
            bundle.note(f"平台图未产出：{exc}")

    if platform_font:
        generated_total = 0
        for style in enabled_styles(settings.publish_platforms_list):
            if not style.image_slugs:
                continue
            try:
                kept, held, generated = await build_platform_images(
                    style,
                    items,
                    digest_label,
                    font_family=platform_font,
                    already_generated=generated_total,
                )
            except Exception as exc:  # noqa: BLE001 - 单平台失败不影响其他平台
                logger.error("平台图产出失败 [%s]: %s", style.key, exc, exc_info=True)
                bundle.withheld.extend(
                    (slug, f"产出失败：{exc}") for slug in style.image_slugs
                )
                continue
            attachments.extend(kept)
            bundle.withheld.extend(held)
            generated_total += generated

    # 3. 平台文案
    try:
        copy_result = await generate_platform_copy(items, digest_label)
    except Exception as exc:  # noqa: BLE001 - 文案失败不阻断邮件
        logger.error("文案生成失败: %s", exc, exc_info=True)
        copy_result = CopyResult()
        bundle.note(f"平台文案未产出：{exc}")
    bundle.copy_result = copy_result

    # 4. 附件预算。丢弃发生在质检之后：先保证每张都合格，再决定哪几张装得下。
    budget = apply_budget(attachments)
    bundle.attachments = budget.kept
    bundle.dropped = budget.dropped

    # 5. 邮件区块
    names_by_platform: dict[str, list[str]] = {}
    for item in bundle.attachments:
        key = platform_of_slug(item.slug)
        if key:
            names_by_platform.setdefault(key, []).append(item.filename)

    bundle.copy_section_html = render_copy_section_html(
        copy_result.accepted, copy_result.truncated, copy_result.failed, names_by_platform
    )
    bundle.copy_section_text = render_copy_section_text(
        copy_result.accepted, copy_result.truncated, copy_result.failed
    )
    bundle.withheld_html = render_withheld_html(bundle.withheld, bundle.dropped)

    logger.info(
        "资产产出完成 | 附件=%s | 扣下=%s | 超预算丢弃=%s | 文案 %s | 耗时=%.1fs",
        len(bundle.attachments),
        len(bundle.withheld),
        len(bundle.dropped),
        copy_result.summary(),
        time.monotonic() - started,
    )
    return bundle


def cleanup_old_renders(current_label: str, retention_days: int | None = None) -> list[Path]:
    """删掉过期的渲染产物，返回删掉的目录。

    以"目录名不等于本次的 digest_label"作为保护条件，而不是靠 mtime 判断本次
    产物：mtime 在补跑、时区偏移、容器时钟漂移下都会误判，而误判的方向是删掉
    这一秒钟刚渲染好、还没发出去的图。目录名是本次运行自己写的，不会看错。
    """
    days = retention_days if retention_days is not None else settings.render_retention_days
    root = Path(settings.render_output_dir)
    if not root.exists() or days <= 0:
        return []

    cutoff = time.time() - days * 86400
    removed: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name == current_label:
            continue
        try:
            if child.stat().st_mtime >= cutoff:
                continue
            import shutil

            shutil.rmtree(child)
            removed.append(child)
        except OSError as exc:
            logger.warning("清理渲染产物失败 [%s]: %s", child, exc)

    if removed:
        logger.info("清理过期渲染产物 %s 个目录（保留 %s 天）", len(removed), days)
    return removed




