"""生图层：Seedream 5.0 Lite 背景图。

三个 provider 约束决定了这个模块的形状，每一个都反直觉：

1. **像素数有下限，不只有上限。** Lite 的总像素范围是 [3686400, 16777216]，
   下限是硬的。三个画幅的逻辑尺寸全在下限以下，所以"按想要的尺寸去请求"
   会被直接拒绝。必须按不低于下限的尺寸生成，再本地缩小。
2. **只能缩小，不能放大。** 放大后的模糊和渲染缺陷在质检眼里长得一样，
   会白烧重试预算，或者更糟 —— 蒙混过关发出去。
3. **返回的 URL 24 小时过期。** 存 URL 等于第二天存了个 404，必须当场下载。

还有一条不是 provider 约束而是设计约束：生成的像素里绝不承载文字。
Seedream 唯一公开的中文渲染数字是 3.0 论文里的 94% 可用率，4.x/5.0 没有任何
数字，字节自己也承认小字号偏弱。94% 对一个仓库名来说等于错字。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fractions import Fraction
from math import ceil, sqrt

from app.config import settings
from app.model_roles import Capability, image_gen_role, require_capability, role_usage
from app.services.background_cache import (
    BackgroundCache,
    CachedImage,
    as_data_url,
    validate_image_bytes,
)
from app.publishers.styles import IMAGE_FRAMES, PlatformStyle

logger = logging.getLogger(__name__)

# Seedream 5.0 Lite 的总像素范围。下限是硬约束，不是建议值。
PIXEL_FLOOR = 3_686_400
PIXEL_CEILING = 16_777_216
# 单边范围。超出会被拒绝。
MIN_SIDE = 1024
MAX_SIDE = 4096
# provider 对边长有对齐要求，取 16 的倍数最保险
SIDE_ALIGNMENT = 16


class GenerationUnavailable(RuntimeError):
    """无法在约束内生成。调用方应改用兜底背景，而不是放大凑数。"""


def _align_up(value: int, multiple: int = SIDE_ALIGNMENT) -> int:
    return int(ceil(value / multiple) * multiple)


@dataclass(frozen=True)
class GenerationSize:
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height

    def as_param(self) -> str:
        return f"{self.width}x{self.height}"


def select_generation_size(target_width: int, target_height: int) -> GenerationSize:
    """选出满足全部约束的最小尺寸。

    "最小"是有意的：像素越多越慢越贵，而超出目标尺寸的部分最终都会被缩掉。
    保持宽高比而不是拉伸到某个预设档位 —— 拉伸后的背景纹理方向会和画幅不符，
    缩放时还得裁边，又把"边缘截断"请回来了。
    """
    if target_width <= 0 or target_height <= 0:
        raise ValueError(f"目标尺寸必须为正，收到 {target_width}x{target_height}")

    width, height = float(target_width), float(target_height)

    # 先满足像素下限
    if width * height < PIXEL_FLOOR:
        factor = sqrt(PIXEL_FLOOR / (width * height))
        width, height = width * factor, height * factor
    # 再满足单边下限
    if min(width, height) < MIN_SIDE:
        factor = MIN_SIDE / min(width, height)
        width, height = width * factor, height * factor

    w, h = _align_up(int(ceil(width))), _align_up(int(ceil(height)))

    if w > MAX_SIDE or h > MAX_SIDE or w * h > PIXEL_CEILING:
        raise GenerationUnavailable(
            f"画幅 {target_width}x{target_height} 需要 {w}x{h} 才能同时满足像素下限与单边下限，"
            f"超出 provider 上限（单边 {MAX_SIDE}，总像素 {PIXEL_CEILING}）。"
            "此时必须使用兜底背景 —— 生成小图再放大的模糊与渲染缺陷无法区分。"
        )

    size = GenerationSize(w, h)
    assert size.pixels >= PIXEL_FLOOR
    assert size.width >= target_width and size.height >= target_height
    return size


def assert_downscale_only(generated: GenerationSize, target_width: int, target_height: int) -> None:
    """确认这是一次缩小。放大就抛错，绝不"凑合用"。"""
    if generated.width < target_width or generated.height < target_height:
        raise GenerationUnavailable(
            f"生成尺寸 {generated.width}x{generated.height} 小于目标 {target_width}x{target_height}，"
            "放大会产生与渲染缺陷无法区分的模糊，必须改用兜底背景"
        )


def aspect_preserved(generated: GenerationSize, target_width: int, target_height: int) -> bool:
    """宽高比是否与目标一致（允许对齐带来的极小偏差）。"""
    target = Fraction(target_width, target_height)
    got = Fraction(generated.width, generated.height)
    return abs(float(target) - float(got)) < 0.02


# --- 提示词 ---------------------------------------------------------------

# 每条都是"不要什么"，因为生图模型的默认行为恰好都是我们不想要的：
# 它默认会往图里写字、默认会画出像 logo 的东西、默认把画面填满。
_NEGATIVE_CLAUSES = (
    "不要出现任何文字、字母、数字或类似文字的笔画",
    "不要出现任何品牌标识、logo、产品截图或界面元素",
    "不要出现人物面部",
    "画面中部与上部保持视觉安静，留给后期叠加的文字",
)


def build_background_prompt(
    style: PlatformStyle,
    topics: list[str],
    digest_label: str,
) -> str:
    """从平台声明的风格 + 当天的实际主题拼提示词。

    主题只用于定调（比如"具身智能"给机械感的几何），不作为可画的具体对象 ——
    题材必须来自摘要，不能凭空造一个不在当天内容里的东西。
    """
    visual = style.visual
    topic_hint = "、".join(topics[:3]) if topics else "通用技术主题"
    return (
        f"为 {style.display_name} 设计一张纯背景图，用途是叠加文字的社交卡片。"
        f"整体气质：{visual.mood}。背景处理：{visual.background}。"
        f"装饰语言：{visual.decoration}。信息密度：{visual.layout_density}。"
        f"配色只使用这些十六进制色：{', '.join(visual.palette)}。"
        f"当天内容的主题基调：{topic_hint}（仅用于定调，不要把主题画成具体物体）。"
        f"日期标识：{digest_label}（不要把它画进图里）。"
        + " ".join(f"{clause}。" for clause in _NEGATIVE_CLAUSES)
    )


def prompt_mentions_only_digest_subjects(prompt: str, allowed_topics: list[str]) -> bool:
    """提示词里出现的主题必须都在摘要里。"""
    return all(topic in prompt for topic in allowed_topics[:3])


# --- 请求体 ---------------------------------------------------------------


def build_request_payload(
    prompt: str,
    size: GenerationSize,
    *,
    max_images: int = 1,
    sequential: bool = False,
) -> dict:
    """构造 Ark 生图请求。

    `watermark` 永远显式出现。provider 默认 true，缺字段就等于交付带
    "AI生成" 角标的图 —— 那不是一个我们选择过的结果。
    """
    role = require_capability(image_gen_role(), Capability.IMAGE_GEN)
    payload: dict = {
        "model": role.model,
        "prompt": prompt,
        "size": size.as_param(),
        "response_format": "url",
        # 显式发送，不依赖 provider 默认
        "watermark": bool(settings.image_gen_watermark),
    }
    if sequential:
        # 组图：只有 Lite 支持。四张小红书背景要成套，否则像四个不相干的帖子。
        payload["sequential_image_generation"] = "auto"
        payload["sequential_image_generation_options"] = {"max_images": max_images}
    else:
        payload["sequential_image_generation"] = "disabled"
    return payload


def within_run_cap(already_generated: int, requesting: int) -> bool:
    """按张数计费（¥0.22/张），所以上限是张数而不是 token。"""
    return already_generated + requesting <= settings.image_gen_max_per_run


class SeedreamClient:
    """生图调用。禁用时直接返回空，让调用方走兜底背景。"""

    def __init__(self) -> None:
        self.role = image_gen_role()

    @property
    def is_available(self) -> bool:
        return settings.image_gen_enabled and self.role.is_configured

    async def generate(
        self,
        prompt: str,
        size: GenerationSize,
        *,
        max_images: int = 1,
        sequential: bool = False,
    ) -> list[bytes]:
        """生成并**立即下载**图片字节。

        返回字节而不是 URL 是刻意的：URL 24 小时后失效，任何"先存 URL
        以后再取"的写法第二天都会拿到 404。
        """
        if not self.is_available:
            return []

        require_capability(self.role, Capability.IMAGE_GEN)
        import httpx

        payload = build_request_payload(prompt, size, max_images=max_images, sequential=sequential)
        endpoint = f"{self.role.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.role.api_key}",
            "Content-Type": "application/json",
        }

        timeout = settings.image_gen_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = response.text.strip()[:300]
                logger.error(
                    "生图接口返回错误 [%s] status=%s: %s", self.role.model, response.status_code, detail
                )
                raise GenerationUnavailable(f"生图失败 status={response.status_code}")
            data = response.json()

            urls = [entry.get("url") for entry in data.get("data", []) if entry.get("url")]
            role_usage.record("image_gen", calls=max(1, len(urls)))
            if not urls:
                raise GenerationUnavailable("生图接口未返回任何图片 URL")

            images: list[bytes] = []
            for url in urls:
                # 当场下载：URL 24 小时过期
                fetched = await client.get(url)
                fetched.raise_for_status()
                images.append(fetched.content)

        logger.info("生图完成 | 模型=%s | 尺寸=%s | 张数=%s", self.role.model, size.as_param(), len(images))
        return images


seedream_client = SeedreamClient()


# --- 兜底背景 -------------------------------------------------------------


@dataclass(frozen=True)
class Background:
    """一张图要用的背景。data_url 为 None 表示用模板自带的 CSS 渐变。

    兜底不是降级产物，而是默认状态：生图默认关闭，所以绝大多数运行都走这条
    路径。它必须是一个完整可发布的结果，不能是"没图时凑合一下"。
    """

    data_url: str | None = None
    generated: bool = False
    reason: str = ""

    @property
    def is_fallback(self) -> bool:
        return self.data_url is None


def fallback_background(reason: str) -> Background:
    return Background(data_url=None, generated=False, reason=reason)


def generated_background(image_bytes: bytes) -> Background:
    """Build a background from validated provider/cache bytes with actual MIME."""
    mime_type = validate_image_bytes(image_bytes)
    cached = CachedImage(content=image_bytes, mime_type=mime_type)
    return Background(data_url=as_data_url(cached), generated=True)


def supports_multipage_series(model: str) -> bool:
    """该模型能否出组图。Pro 不能 —— 四张图会像四个不相干的帖子。"""
    return "pro" not in model.lower()


async def resolve_backgrounds(
    style: PlatformStyle,
    topics: list[str],
    digest_label: str,
    page_count: int,
    *,
    already_generated: int = 0,
    client: SeedreamClient | None = None,
) -> tuple[list[Background], int]:
    """Resolve stable background slots, generating only cache misses."""
    client = client if client is not None else seedream_client
    if page_count <= 0:
        return [], 0

    declared_slots = list(style.image_slugs)
    slots = declared_slots[:page_count]
    if len(slots) < page_count and style.key == "xiaohongshu":
        # 动态内容页复用最后一个固定内容背景槽位，不为新增文字页重新生图。
        content_slots = [slot for slot in declared_slots if slot.startswith("xhs-content-")]
        if content_slots:
            slots.extend([content_slots[-1]] * (page_count - len(slots)))
    if not slots:
        return [fallback_background("该平台没有声明画幅") for _ in range(page_count)], 0

    dpr = settings.render_device_scale_factor
    model = client.role.model
    cache = BackgroundCache(
        settings.image_background_cache_dir,
        settings.image_background_cache_version,
    )
    resolved: dict[str, Background] = {}
    missing: list[str] = []
    for slot in slots:
        frame_width, frame_height = IMAGE_FRAMES[slot]
        cached = cache.get(
            style.key,
            slot,
            frame_width,
            frame_height,
            dpr,
            model,
        )
        if cached is None:
            missing.append(slot)
        else:
            resolved[slot] = Background(
                data_url=as_data_url(cached), generated=True, reason="固定背景缓存命中"
            )

    def _complete(backgrounds: list[Background], reason: str) -> list[Background]:
        """Keep the declared frame count explicit if a caller asks for extra pages."""
        while len(backgrounds) < page_count:
            backgrounds.append(fallback_background(reason))
        return backgrounds

    missing = list(dict.fromkeys(missing))

    if not missing:
        logger.info("固定背景缓存命中 [%s] %s 个槽位", style.key, len(slots))
        return _complete([resolved[slot] for slot in slots], "该平台没有声明额外画幅"), 0

    def _with_missing_fallback(reason: str) -> tuple[list[Background], int]:
        return _complete(
            [resolved.get(slot, fallback_background(reason)) for slot in slots], reason
        ), 0

    if not client.is_available:
        return _with_missing_fallback("生图未启用或未配置，固定背景缓存未命中")
    if len(missing) > 1 and not supports_multipage_series(model):
        return _with_missing_fallback(f"模型 {model} 不支持组图，多页会失去一致性")
    if not within_run_cap(already_generated, len(missing)):
        return _with_missing_fallback(
            f"超出每轮生成上限 {settings.image_gen_max_per_run} 张，固定背景缓存未命中"
        )

    target_width, target_height = IMAGE_FRAMES[missing[0]]
    target_width *= dpr
    target_height *= dpr
    try:
        size = select_generation_size(target_width, target_height)
        assert_downscale_only(size, target_width, target_height)
        prompt = build_background_prompt(style, topics, digest_label)
        images = await client.generate(
            prompt,
            size,
            max_images=len(missing),
            sequential=len(missing) > 1,
        )
    except Exception as exc:  # noqa: BLE001 - generation failure must not block email
        logger.warning("生图失败，改用兜底背景 [%s]: %s", style.key, exc)
        return _with_missing_fallback(f"生图失败: {exc}")

    if not images:
        return _with_missing_fallback("生图返回为空")

    generated_count = 0
    for slot, raw in zip(missing, images):
        try:
            frame_width, frame_height = IMAGE_FRAMES[slot]
            cached = cache.put(
                style.key,
                slot,
                frame_width,
                frame_height,
                dpr,
                model,
                raw,
            )
            resolved[slot] = Background(
                data_url=as_data_url(cached), generated=True, reason="固定背景首次生成"
            )
            generated_count += 1
        except Exception as exc:  # noqa: BLE001 - corrupt provider output is a miss
            logger.warning("背景缓存写入失败 [%s/%s]: %s", style.key, slot, exc)
            resolved[slot] = fallback_background(f"背景字节无效：{exc}")

    for slot in missing:
        resolved.setdefault(slot, fallback_background("生图返回张数不足"))
    return _complete(
        [resolved[slot] for slot in slots], "该平台没有声明额外画幅"
    ), generated_count
