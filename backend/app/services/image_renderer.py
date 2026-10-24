"""长图渲染：分段截图 + 纵向拼接。

为什么必须分段：Chromium 单张纹理的最大边长是 16384px，超过后 full-page
截图不会报错，它静默截断 —— 得到的图看起来完整，底部内容凭空消失。24 条
内容的摘要在 2× DPR 下轻松超过这个数，所以分段不是优化项。

拼接的正确性判据只有一条：拼完的高度必须精确等于整页高度×缩放。少一像素
意味着某个分段的偏移算错了，视觉上表现为接缝或丢带 —— 而这两种缺陷在
单张图里很难被看出来，所以用等式去卡而不是靠肉眼。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.config import settings
from app.services.font_check import FontReport, font_stack, inspect_fonts, verify_fonts_or_raise

logger = logging.getLogger(__name__)

# Chromium 单张纹理上限。配置值必须小于它，这里作为断言的上界。
CHROMIUM_MAX_TEXTURE_PX = 16384


@dataclass(frozen=True)
class Segment:
    """一个分段。css_offset 用于滚动定位，device_height 用于拼接。"""

    index: int
    css_offset: int
    css_height: int
    device_height: int


def segment_plan(
    total_css_height: int,
    scale: int,
    max_device_height: int,
) -> list[Segment]:
    """把整页切成互不重叠、无缝隙、恰好覆盖全页的分段。

    在 CSS 像素空间切分再乘缩放，而不是在设备像素空间切分：后者需要把设备
    高度换回 CSS 偏移，除不尽时会产生半像素偏移，拼接处出现一条重复或缺失的
    像素行。
    """
    if total_css_height <= 0:
        raise ValueError(f"页面高度必须为正，收到 {total_css_height}")
    if scale <= 0:
        raise ValueError(f"缩放必须为正，收到 {scale}")
    if max_device_height < scale:
        raise ValueError(
            f"分段上限 {max_device_height} 小于单个 CSS 像素的设备高度 {scale}，无法切分"
        )

    max_css_height = max_device_height // scale
    segments: list[Segment] = []
    offset = 0
    index = 0
    while offset < total_css_height:
        css_height = min(max_css_height, total_css_height - offset)
        segments.append(
            Segment(
                index=index,
                css_offset=offset,
                css_height=css_height,
                device_height=css_height * scale,
            )
        )
        offset += css_height
        index += 1

    assert sum(seg.css_height for seg in segments) == total_css_height
    return segments


def needs_segmentation(total_css_height: int, scale: int, max_device_height: int) -> bool:
    return total_css_height * scale > max_device_height


def stitch_vertically(images: Sequence["object"]) -> "object":
    """纵向拼接。宽度取最大值，高度为各段之和。

    宽度理论上应当一致；取最大值并居左粘贴，是为了让宽度不一致时表现为右侧
    空白（可见）而不是内容被裁掉（不可见）。
    """
    from PIL import Image

    if not images:
        raise ValueError("没有分段可拼接")
    if len(images) == 1:
        return images[0]

    width = max(img.width for img in images)
    height = sum(img.height for img in images)
    canvas = Image.new("RGB", (width, height), "#FFFFFF")
    y = 0
    for img in images:
        canvas.paste(img.convert("RGB") if img.mode != "RGB" else img, (0, y))
        y += img.height
    return canvas


def preflight(report: FontReport | None = None) -> FontReport:
    """渲染前的准入检查。缺字体在这里终止，不进浏览器。"""
    return verify_fonts_or_raise(report if report is not None else inspect_fonts())


def _output_dir() -> Path:
    path = Path(settings.render_output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


class LongImageRenderer:
    """把摘要 HTML 渲染成一张超高清长图。

    Playwright 是延迟导入的：渲染默认关闭，未装浏览器的环境（本地开发、
    只跑测试的 CI）不应该因为一个 import 就起不来。
    """

    def __init__(self, viewport_width: int = 800) -> None:
        self.viewport_width = viewport_width
        self.scale = settings.render_device_scale_factor
        self.max_device_height = min(settings.render_segment_max_height, CHROMIUM_MAX_TEXTURE_PX - 1)

    def plan_for(self, total_css_height: int) -> list[Segment]:
        return segment_plan(total_css_height, self.scale, self.max_device_height)

    async def render(self, html: str, output_path: Path | str) -> Path:
        """渲染并写盘，返回实际路径。"""
        preflight()

        from playwright.async_api import async_playwright  # 延迟导入
        from PIL import Image
        import io

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timeout_ms = int(settings.render_timeout_seconds * 1000)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                args=[
                    # 容器内 /dev/shm 只有 64MB，Chromium 会以看不出原因的方式崩溃
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--font-render-hinting=none",
                ]
            )
            try:
                context = await browser.new_context(
                    viewport={"width": self.viewport_width, "height": 1200},
                    device_scale_factor=self.scale,
                )
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)
                await page.set_content(html, wait_until="load")
                await page.evaluate("document.fonts ? document.fonts.ready : null")

                total_css_height = await page.evaluate(
                    "Math.ceil(document.documentElement.scrollHeight)"
                )
                segments = self.plan_for(total_css_height)
                logger.info(
                    "长图渲染 | 页高=%spx | 缩放=%s | 分段=%s",
                    total_css_height,
                    self.scale,
                    len(segments),
                )

                if len(segments) == 1:
                    await page.screenshot(path=str(output_path), full_page=True)
                else:
                    shots = []
                    for seg in segments:
                        raw = await page.screenshot(
                            # full_page 必须和 clip 一起给。clip 的坐标是相对
                            # "截出来的那张图"的，不是相对文档：只给 clip 时那张图
                            # 只有视口大小，于是第一段之后的每一段都落在图外，报
                            # "Clipped area is either empty or outside the resulting
                            # image"。容器内实测：页高 10000、视口 1200 时，
                            # y=5000 裸 clip 失败，加 full_page=True 得到 (1600,6000)。
                            full_page=True,
                            clip={
                                "x": 0,
                                "y": seg.css_offset,
                                "width": self.viewport_width,
                                "height": seg.css_height,
                            }
                        )
                        shots.append(Image.open(io.BytesIO(raw)))
                    stitched = stitch_vertically(shots)
                    expected = total_css_height * self.scale
                    if stitched.height != expected:
                        raise RuntimeError(
                            f"拼接高度 {stitched.height} 不等于整页高度×缩放 {expected}，"
                            "说明分段偏移算错了，产出会有接缝或丢带"
                        )
                    stitched.save(output_path)
            finally:
                await browser.close()

        logger.info("长图已写入 %s", output_path)
        return output_path

    async def render_frame(
        self, html: str, output_path: Path | str, width: int, height: int
    ) -> Path:
        """渲染一张定宽定高的平台图。

        与长图分开而不是复用 render()：平台图的高度是画幅规定的常量，不能由
        内容决定。用 full_page 截图会在文字比预期多时把图截高，得到一张比例
        不对的图 —— 而比例不对意味着平台替我们裁边，正是本次要消灭的缺陷。
        所以这里 clip 到画幅，超出部分由质检报 overflow，交给修正循环收紧。
        """
        preflight()

        from playwright.async_api import async_playwright  # 延迟导入

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timeout_ms = int(settings.render_timeout_seconds * 1000)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                args=["--disable-dev-shm-usage", "--no-sandbox", "--font-render-hinting=none"]
            )
            try:
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=self.scale,
                )
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)
                await page.set_content(html, wait_until="load")
                await page.evaluate("document.fonts ? document.fonts.ready : null")
                await page.screenshot(
                    path=str(output_path),
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                )
            finally:
                await browser.close()

        logger.info("平台图已写入 %s（%sx%s @%sx）", output_path, width, height, self.scale)
        return output_path


def html_font_stack() -> str:
    """供模板注入的 font-family 值。"""
    return font_stack()
