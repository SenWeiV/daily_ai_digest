"""投递编码的测试

对应 add-longimage-and-publishers §9 的附件体积约束。

判据不是"图变小了"。真正要钉住的是三件事：
1. 长图不被转码 —— 它是给人直接点开看的，格式必须是各客户端都能预览的 PNG。
2. 平台图的 JPEG 不做色度抽样。4:2:0 会让彩色字缘掉约 12dB（容器内实测
   39.92dB → 27.80dB），表现为"字看着发毛"，正是本项目一再消灭的缺陷类别。
3. 编码发生在送检**之前**。检 PNG 而发 JPEG 等于质检的对象不是交付物。
"""

import io

import pytest
from PIL import Image

from app.services.attachment_budget import LONG_IMAGE_SLUG
from app.services.delivery_encoding import (
    PLATFORM_JPEG_QUALITY,
    PLATFORM_JPEG_SUBSAMPLING,
    delivery_extension,
    encode_for_delivery,
)


def _png(width: int = 400, height: int = 300, *, noisy: bool = True) -> bytes:
    """一张 PNG 素材。

    noisy=True 造的是**照片式**内容：低频正弦 + 高斯噪声，定种。
    两个选择都是必要的：
    - 不用纯渐变或正弦纹理。规则图案正好落在 PNG 行滤波器擅长的方向上，
      实测 400x300 斜向渐变 PNG 只有 4KB、同图 JPEG q95 是 114KB —— 在这种
      素材上"JPEG 更小"永远为假，断言测的是素材性质而不是编码器。
    - 也不用纯随机噪声。它比真实背景熵高得多，实测 PNG 360KB / JPEG 245KB，
      虽然方向对了，但那是一种真实生成背景里不会出现的极端情形。
    定种是为了让体积断言每次运行结果一致。
    """
    import math
    import random

    image = Image.new("RGB", (width, height))
    if noisy:
        rng = random.Random(20260801)

        def _clamp(value: float) -> int:
            return max(0, min(255, int(value)))

        image.putdata([
            (
                _clamp(128 + 100 * math.sin(x / 60) + rng.gauss(0, 12)),
                _clamp(120 + 90 * math.sin(y / 48) + rng.gauss(0, 12)),
                _clamp(140 + 80 * math.sin((x + y) / 70) + rng.gauss(0, 12)),
            )
            for y in range(height)
            for x in range(width)
        ])
    else:
        image.paste("#FFFFFF", (0, 0, width, height))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _high_entropy_png(width: int = 400, height: int = 300) -> bytes:
    """纯随机噪声。专门用来触发 Pillow 的 MAXBLOCK 缓冲上限。"""
    import random

    rng = random.Random(7)
    image = Image.new("RGB", (width, height))
    image.putdata([
        (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        for _ in range(width * height)
    ])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- 格式选择 -------------------------------------------------------------


def test_long_image_keeps_png_extension():
    assert delivery_extension(LONG_IMAGE_SLUG) == "png"


def test_platform_images_use_jpg_extension():
    assert delivery_extension("x-card") == "jpg"
    assert delivery_extension("xhs-cover") == "jpg"


def test_long_image_bytes_are_returned_untouched():
    """长图不转码：Outlook 桌面版不预览 WebP，JPEG 又会动字缘。"""
    original = _png()
    assert encode_for_delivery(original, LONG_IMAGE_SLUG) is original


def test_platform_image_becomes_jpeg():
    encoded = encode_for_delivery(_png(), "x-card")
    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG"


def test_platform_image_shrinks_on_photographic_content():
    original = _png()
    assert len(encode_for_delivery(original, "x-card")) < len(original)


def test_high_entropy_image_still_encodes_to_jpeg():
    """回归：optimize=True 的 scan 缓冲区上限是全局 ImageFile.MAXBLOCK（64KB）。

    熵一高就装不下，Pillow 抛 "broken data stream when writing image file"，
    这张图于是退回 PNG —— 附件反而更大，而唯一的迹象是一行 WARNING。
    真实的生成背景恰好压得动，所以这个坑在真实素材上不显形。
    """
    original = _high_entropy_png()
    encoded = encode_for_delivery(original, "x-card")
    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG", "高熵图退回了 PNG，MAXBLOCK 上限没放开"


def test_maxblock_is_restored_after_encoding():
    """MAXBLOCK 是全局的；改了不还回去会影响进程里其他所有图片写出。"""
    from PIL import ImageFile

    before = ImageFile.MAXBLOCK
    encode_for_delivery(_high_entropy_png(), "x-card")
    assert ImageFile.MAXBLOCK == before


# --- 色度抽样 -------------------------------------------------------------


def test_subsampling_is_disabled():
    """0 = 4:4:4。这一条是硬要求：4:2:0 让字缘 PSNR 从 39.92 掉到 27.80dB。"""
    assert PLATFORM_JPEG_SUBSAMPLING == 0


def test_encoded_jpeg_actually_has_no_chroma_subsampling():
    """断在产出的字节上，而不只是断常量 —— 常量对了但没传下去一样会退化。"""
    from PIL.JpegImagePlugin import get_sampling

    encoded = encode_for_delivery(_png(), "x-card")
    with Image.open(io.BytesIO(encoded)) as image:
        assert get_sampling(image) == 0


def test_quality_stays_high_enough_for_text_edges():
    """q95 是实测下字缘 PSNR 仍在 38dB 以上的档位。"""
    assert PLATFORM_JPEG_QUALITY >= 95


def test_text_edges_survive_the_encoding():
    """真的画一段文字边缘，量编码前后的最大像素误差。

    用黑白竖条模拟字缘：它是最严苛的高频边缘，JPEG 的振铃在这里最明显。
    """
    width, height = 160, 80
    image = Image.new("RGB", (width, height), "#FFFFFF")
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            if (x // 2) % 2 == 0:
                pixels[x, y] = (0, 0, 0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    encoded = encode_for_delivery(buffer.getvalue(), "x-card")
    with Image.open(io.BytesIO(encoded)) as decoded:
        pairs = zip(image.tobytes(), decoded.convert("RGB").tobytes())
        peak = max(abs(a - b) for a, b in pairs)
    # 阈值取 96/255：黑白竖条是比真实字缘更极端的情形，真实图上实测最大误差
    # 是 17–26/255。这条断言防的是"抽样被改回 4:2:0"这类量级上的退化。
    assert peak < 96, f"字缘最大误差 {peak}/255，编码退化了"


# --- 失败与退化路径 -------------------------------------------------------


def test_unopenable_bytes_fall_back_to_the_original():
    """编码失败不该让这张图消失 —— 大一点的附件仍然能发。"""
    garbage = b"not an image at all"
    assert encode_for_delivery(garbage, "x-card") is garbage


def test_flat_image_keeps_png_when_jpeg_would_be_larger():
    """文字多、背景平坦的图上 PNG 本来就更小；取小的那个。"""
    flat = _png(noisy=False)
    assert encode_for_delivery(flat, "x-card") is flat


def test_encoding_is_deterministic():
    original = _png()
    assert encode_for_delivery(original, "x-card") == encode_for_delivery(original, "x-card")


# --- 与质检的先后顺序 -----------------------------------------------------


def test_inspection_sees_the_delivered_bytes(monkeypatch):
    """送检的字节必须与附件的字节逐字节相同。

    这是这一层最重要的一条。检 PNG 而发 JPEG 时，质检看过的东西和收件人
    收到的东西不是一份，压缩带来的字缘退化就绕过了唯一的关卡。
    """
    import asyncio

    from app.services import digest_assets

    inspected: list[bytes] = []

    async def _fake_gate(slug, render, inspect, expected_texts=None, max_attempts=None):
        from app.services.qa_gate import GateResult

        image = await render(digest_assets.Correction())
        inspected.append(image)
        return GateResult(slug, image, 1, True)

    monkeypatch.setattr(digest_assets, "run_gate", _fake_gate)

    async def _fake_render_frame(self, html, output_path, width, height):
        from pathlib import Path

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(_png(width // 4 or 40, height // 4 or 40))
        return output_path

    monkeypatch.setattr(
        digest_assets.LongImageRenderer, "render_frame", _fake_render_frame, raising=True
    )

    async def _fake_backgrounds(style, topics, label, count, already_generated=0):
        from app.services.image_generation import fallback_background

        return [fallback_background("测试") for _ in range(count)], 0

    monkeypatch.setattr(digest_assets, "resolve_backgrounds", _fake_backgrounds)

    from app.publishers.styles import PLATFORM_STYLES

    style = PLATFORM_STYLES["x"]
    items = [{"repo_name": "org/repo", "repo_url": "https://github.com/org/repo", "stars": 10}]

    attachments, withheld, _ = asyncio.run(
        digest_assets.build_platform_images(
            style, items, "2026-08-01", font_family="sans-serif"
        )
    )
    assert attachments, f"没有产出附件，withheld={withheld}"
    assert inspected
    for attachment, seen in zip(attachments, inspected):
        assert attachment.content == seen


def test_platform_attachment_filename_carries_the_delivery_extension(monkeypatch):
    """文件名后缀决定 MIME 子类型；jpg 内容配 .png 名字会让客户端认错类型。"""
    from app.services.attachment_budget import attachment_filename

    assert attachment_filename("x-card", "2026-08-01", delivery_extension("x-card")).endswith(
        ".jpg"
    )
    assert attachment_filename(
        LONG_IMAGE_SLUG, "2026-08-01", delivery_extension(LONG_IMAGE_SLUG)
    ).endswith(".png")
