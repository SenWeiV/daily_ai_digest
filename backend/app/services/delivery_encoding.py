"""投递编码：附件用什么格式装进邮件。

起因是一次真实失败。7 张 PNG 合计 17.82MB，base64 后约 24.4MB，
向 smtp.163.com 的 DATA 阶段超时。用逐级加大的 DATA 探测量到 163 的行为
（探测发完不给终止符，所以那些信都被丢弃，收件箱里不会多出东西）：

    13.0MB 上行  1.8s   7.22MB/s
    20.0MB 上行  167.0s 0.12MB/s
    26.0MB 上行  138.7s 0.19MB/s
    35.0MB 上行  364.2s 0.10MB/s

也就是说 163 不拒收大信，它**限速**：13MB 附近还是全速，再往上掉两个数量级。
所以正确的对策不是把超时调到能熬过 6 分钟，而是让载荷留在快速区间里 ——
超时只作为兜底余量。（探测第一版曾报 "552 exceeded header lenght limit"，
那是探测自己的 bug：没发空行，整条流被当成信头。它量的是信头限制，不是信体。）

## 编码怎么选

按内容类型分，不按"哪张图更重要"：

- **长图仍然是 PNG。** 它是给人读的主交付物，PNG 在所有邮件客户端里都能直接
  预览；WebP 无损其实更小（2.17MB vs 4.13MB）但 Outlook 桌面版不预览它，
  对一个"点开就看"的交付物来说这是实打实的退步。
- **平台图用 JPEG q95 4:4:4。** 它们带生成的照片式背景，无损编码在这种内容上
  最贵（x-card 无损 3.68MB / q95 1.23MB），而下游每个平台都会再压一次 JPEG，
  留一份无损中间产物在下游换不到任何东西。

**4:4:4 是硬要求，不是调优。** 容器内实测把色度抽样从 4:4:4 换成 4:2:0，
字缘 PSNR 从 39.92dB 掉到 27.80dB —— 彩色文字的边缘会发糊，而"字看着发毛"
正是这个项目一直在消灭的那类缺陷。

q95 4:4:4 的实测保真度（指标落在**字缘像素**上，不是整图平均 ——
整图平均会被大片平坦背景稀释成一个好看的假数）：

    x-card         PSNR 45.21dB  字缘 38.35dB  最大误差 26/255
    xhs-content-1  PSNR 49.33dB  字缘 42.56dB  最大误差 17/255

编码发生在**送检之前**，所以视觉质检看到的就是收件人收到的字节。
反过来做（检 PNG、发 JPEG）等于质检的对象不是交付物。
"""

from __future__ import annotations

import io
import logging

from app.services.attachment_budget import LONG_IMAGE_SLUG

logger = logging.getLogger(__name__)

# 平台图的 JPEG 质量。95 是实测下字缘 PSNR 仍在 38dB 以上的档位。
PLATFORM_JPEG_QUALITY = 95
# 0 = 4:4:4（不做色度抽样）。见模块文档：换成 4:2:0 会让字缘掉 12dB。
PLATFORM_JPEG_SUBSAMPLING = 0


def delivery_extension(slug: str, content: bytes | None = None) -> str:
    """返回最终字节的真实扩展名；没有字节时只返回该槽位的首选格式。

    JPEG 编码失败或 JPEG 比 PNG 更大时，encode_for_delivery 会保留原 PNG。
    文件名/MIME 必须跟着**最终字节**走，不能仍按平台槽位写成 .jpg。
    """
    if content is not None:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if content.startswith(b"\xff\xd8\xff"):
            return "jpg"
        raise ValueError(f"{slug} 的交付字节不是受支持的 PNG 或 JPEG")
    return "png" if slug == LONG_IMAGE_SLUG else "jpg"


def encode_for_delivery(png_bytes: bytes, slug: str) -> bytes:
    """把渲染出来的 PNG 转成投递格式。长图原样返回。

    编码失败时返回原始 PNG 而不是抛错：一张大一点的附件仍然能发，
    而抛错会让这张图整个消失 —— 后者对读者是更大的损失。
    """
    if delivery_extension(slug) == "png":
        return png_bytes

    from PIL import Image, ImageFile

    try:
        with Image.open(io.BytesIO(png_bytes)) as image:
            rgb = image.convert("RGB")
            buffer = io.BytesIO()
            # optimize=True 需要把一整个 scan 缓冲下来，缓冲区大小是全局的
            # ImageFile.MAXBLOCK（默认 64KB）。图像熵一高就装不下，Pillow 抛
            # "broken data stream when writing image file" —— 于是这张图退回
            # PNG，附件反而更大。实测 400x300 的随机噪声图就能触发；照片式的
            # 生成背景恰好压得动，所以这个坑在真实素材上不显形。
            # 按整图像素数给上界：JPEG 的单个 scan 不会超过这个量级。
            previous_maxblock = ImageFile.MAXBLOCK
            ImageFile.MAXBLOCK = max(previous_maxblock, rgb.width * rgb.height * 4)
            try:
                rgb.save(
                    buffer,
                    format="JPEG",
                    quality=PLATFORM_JPEG_QUALITY,
                    subsampling=PLATFORM_JPEG_SUBSAMPLING,
                    optimize=True,
                )
            finally:
                ImageFile.MAXBLOCK = previous_maxblock
    except Exception as exc:  # noqa: BLE001 - 编码失败不该让这张图消失
        logger.warning("投递编码失败 [%s]，改用原始 PNG：%s", slug, exc)
        return png_bytes

    encoded = buffer.getvalue()
    if len(encoded) >= len(png_bytes):
        # 文字多、背景平坦的图上 PNG 可能本来就更小。取小的那个。
        logger.info(
            "投递编码 [%s] JPEG %s 字节不小于 PNG %s 字节，保留 PNG",
            slug,
            len(encoded),
            len(png_bytes),
        )
        return png_bytes

    logger.info(
        "投递编码 [%s] PNG %s → JPEG q%s 4:4:4 %s 字节（省 %.0f%%）",
        slug,
        len(png_bytes),
        PLATFORM_JPEG_QUALITY,
        len(encoded),
        100 * (1 - len(encoded) / len(png_bytes)),
    )
    return encoded
