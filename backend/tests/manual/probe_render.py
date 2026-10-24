#!/usr/bin/env python3
"""在容器里真渲染一次，并用像素判断有没有豆腐块。

判据不能是"字体装上了"。fc-list 有输出只说明 fontconfig 解析到了族名，
Chromium 仍然可能画出空心方框 —— 那才是这个项目一再要消灭的缺陷，而它
只在成品像素里可见。所以这里落到像素上，用三条互相独立的判据：

1. 每个字都得有墨。全白的裁片意味着这个字根本没画出来。
2. 不同的字必须画得不一样。豆腐块的形状与字符无关，所有缺字形的字会得到
   逐像素相同的裁片 —— 这是"渲染成方框"最可靠的指纹，比找矩形轮廓稳。
3. emoji 裁片必须是彩色的。fonts-noto-color-emoji 是 CBDT 位图字体；
   如果 Chromium 落到了单色族上，emoji 会变成黑白线框或方框，
   而这两种情况的共同特征都是"没有饱和色"。
"""

import asyncio
import hashlib
import sys

CJK = "中文渲染测试深度求索"
EMOJI = "🎉🚀✅"

# 逐字符包在 span 里，才能拿到每个字的精确边界。整块文字的截图无法分辨
# "某一个字是方框"，因为方框在一片正常文字里只占很小一块面积。
_SPANS = "".join(f'<span id="c{i}">{ch}</span>' for i, ch in enumerate(CJK + EMOJI))
HTML = f"""<html><body style="margin:0;background:#fff">
<div id="probe" style="font-family:{{stack}};font-size:64px;line-height:1.4;
     white-space:nowrap;padding:20px;color:#000">{_SPANS}</div>
</body></html>"""


def _crop_signature(image, box):
    """裁片的像素指纹与墨量、饱和色计数。"""
    crop = image.crop(box).convert("RGB")
    pixels = list(crop.getdata())
    ink = sum(1 for r, g, b in pixels if (r + g + b) < 700)
    colored = sum(
        1
        for r, g, b in pixels
        if max(r, g, b) - min(r, g, b) > 40 and max(r, g, b) > 80
    )
    digest = hashlib.sha256(crop.tobytes()).hexdigest()[:16]
    return digest, ink, colored, len(pixels)


async def _render(stack: str, out: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=["--disable-dev-shm-usage", "--no-sandbox", "--font-render-hinting=none"]
        )
        try:
            context = await browser.new_context(
                viewport={"width": 1400, "height": 200}, device_scale_factor=2
            )
            page = await context.new_page()
            await page.set_content(HTML.format(stack=stack), wait_until="load")
            await page.evaluate("document.fonts ? document.fonts.ready : null")
            boxes = await page.evaluate(
                """() => Array.from(document.querySelectorAll('#probe span'))
                     .map(el => { const r = el.getBoundingClientRect();
                                  return [r.x, r.y, r.width, r.height, el.textContent]; })"""
            )
            await page.screenshot(path=out, full_page=True)
        finally:
            await browser.close()
    return boxes


def main() -> int:
    from PIL import Image

    from app.services.font_check import font_stack, inspect_fonts

    report = inspect_fonts()
    stack = font_stack(report)
    print(f"字体栈 = {stack}")
    print(f"中文族 = {report.cjk_families[:3]}")
    print(f"emoji 族 = {report.emoji_families[:2]}")

    failures: list[str] = []

    # 简体正文不能落到日韩字形变体上。这一条不能靠像素判：JP 变体每个字都有
    # 字形，方框检测与视觉质检都会放它过去，缺陷只表现为"字看着有点怪"。
    top = report.cjk_families[0] if report.cjk_families else ""
    if any("SC" in name for name in report.cjk_families) and "SC" not in top:
        failures.append(
            f"排在最前的中文族是 {top!r}，但系统上存在简体族 —— "
            "简体正文会用日韩字形变体渲染"
        )

    out = "/tmp/render_probe.png"
    boxes = asyncio.run(_render(stack, out))
    image = Image.open(out)
    print(f"截图 = {image.size} {image.mode}")

    scale = 2  # device_scale_factor
    signatures: dict[str, list[str]] = {}
    for x, y, w, h, char in boxes:
        if w <= 0 or h <= 0:
            failures.append(f"{char!r} 的排版盒宽或高为 0，字符没有被布局")
            continue
        box = (int(x * scale), int(y * scale), int((x + w) * scale), int((y + h) * scale))
        digest, ink, colored, total = _crop_signature(image, box)
        signatures.setdefault(digest, []).append(char)
        is_emoji = char in EMOJI
        ink_ratio = ink / total if total else 0.0
        label = "emoji" if is_emoji else "汉字"
        print(
            f"  {label} {char} 墨占比={ink_ratio:.3f} 彩色像素={colored} 指纹={digest}"
        )
        if ink_ratio < 0.01 and colored == 0:
            failures.append(f"{char!r} 几乎没有墨（{ink_ratio:.4f}），字形缺失或没画出来")
        if is_emoji and colored < total * 0.01:
            failures.append(
                f"emoji {char!r} 没有饱和色（彩色像素 {colored}/{total}），"
                "说明落到了单色字体上而不是 CBDT 彩色 emoji"
            )

    for digest, chars in signatures.items():
        if len(chars) > 1:
            failures.append(
                f"字符 {chars} 渲染出逐像素相同的图（指纹 {digest}）——"
                "这正是豆腐块的指纹：方框形状与字符无关"
            )

    if failures:
        print("\n渲染自检未通过：")
        for line in failures:
            print(f"  ✗ {line}")
        return 1
    print(f"\n渲染自检通过：{len(boxes)} 个字符各有独立字形，emoji 为彩色，无豆腐块")
    return 0


if __name__ == "__main__":
    sys.exit(main())
