"""视觉质检：把渲染好的图交给多模态模型，判它能不能发。

这个模块有一条压倒性的设计原则：**任何不确定都算失败**。

原因是这里的错误不对称。判错成失败，代价是一次重试或一张图不发；判错成通过，
代价是把豆腐块发出去 —— 而质检存在的唯一理由就是拦住它。所以：
解析不出结论算失败、模型不可达算"没有任何图通过"、送检副本太小到看不清字
也算失败（因为"看不清所以没发现问题"会被报成通过，这是本设计里最坏的结果）。

同理，缩小送检副本是应对体积超限最自然的做法，做到极端就会产出一个读不出
文字的副本，然后报通过。所以到了分辨率下限还超体积时必须**分段送检**，
不能继续缩小。分段更慢，但慢是对的。
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum

from app.config import settings
from app.model_roles import Capability, require_capability, role_usage, vision_role

logger = logging.getLogger(__name__)

# 超过这个纵横比就分段。视觉模型会把单张超长图缩到自己的视觉 token 网格里；
# 1600x15620 的正文因此只剩约十分之一线性尺寸，即使原始文件仅 4MB、远低于
# 请求字节上限，也已经读不清。3:1 让每段保留足够的横向与纵向细节；所有分段
# 会按从上到下顺序放在**同一次多图请求**里，模型仍能做全局完整性检查。
MAX_INSPECTION_SEGMENT_ASPECT_RATIO = 3.0


class Defect(str, Enum):
    """六类缺陷。每一类对应一个不同的修正动作，否则重试就是原地重放。"""

    MISSING_GLYPH = "missing_glyph"      # 豆腐块：字体缺失
    CLIPPED_AT_EDGE = "clipped_at_edge"  # 文字被画幅边缘切断
    OVERFLOW = "overflow"                # 文字溢出容器
    OVERLAP = "overlap"                  # 文字互相遮挡
    ILLEGIBLE = "illegible"              # 正文在预期尺寸下不可读
    MISSING_TEXT = "missing_text"        # 应当出现的文本没出现


# 缺陷 → 修正动作。重试必须带着不同的参数回来；
# 相同参数的重试是 bug，它只会得到相同的缺陷和更少的预算。
CORRECTION_FOR: dict[Defect, str] = {
    Defect.MISSING_GLYPH: "fallback_font",
    Defect.CLIPPED_AT_EDGE: "tighter_truncation",
    Defect.OVERFLOW: "tighter_truncation",
    Defect.OVERLAP: "reduce_type_scale",
    Defect.ILLEGIBLE: "reduce_content",
    Defect.MISSING_TEXT: "reduce_content",
}


class VisionUnavailable(RuntimeError):
    """视觉角色不可达。此时没有任何图算通过。"""


@dataclass(frozen=True)
class DefectReport:
    category: Defect
    location: str = ""


@dataclass(frozen=True)
class Verdict:
    passed: bool
    defects: tuple[DefectReport, ...] = field(default_factory=tuple)
    raw: str = ""

    @property
    def categories(self) -> tuple[Defect, ...]:
        return tuple(d.category for d in self.defects)


FAILED_UNPARSEABLE = "verdict_unparseable"


def parse_verdict(text: str) -> Verdict:
    """解析模型返回的结论。解析不出就是失败，绝不当成通过。"""
    if not text or not text.strip():
        return Verdict(passed=False, defects=(DefectReport(Defect.MISSING_TEXT, "空响应"),), raw="")

    payload = _extract_json(text)
    if payload is None:
        logger.warning("视觉质检结论无法解析，按失败处理：%s", text.strip()[:200])
        return Verdict(passed=False, defects=(), raw=text)

    if "pass" not in payload:
        logger.warning("视觉质检结论缺少 pass 字段，按失败处理")
        return Verdict(passed=False, defects=(), raw=text)

    raw_defects = payload.get("defects") or []
    defects: list[DefectReport] = []
    for entry in raw_defects:
        if isinstance(entry, dict):
            category, location = entry.get("category"), entry.get("location", "")
        else:
            category, location = entry, ""
        try:
            defects.append(DefectReport(Defect(category), str(location)))
        except (ValueError, TypeError):
            # 无法识别的缺陷类别不能忽略：忽略它等于把一个真实缺陷降级成通过
            logger.warning("视觉质检返回未知缺陷类别 %r，按失败处理", category)
            return Verdict(passed=False, defects=tuple(defects), raw=text)

    passed = bool(payload["pass"])
    if passed and defects:
        # 自相矛盾的结论按失败处理
        logger.warning("视觉质检同时报告通过与缺陷，按失败处理")
        passed = False
    return Verdict(passed=passed, defects=tuple(defects), raw=text)


def _extract_json(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


# --- 送检副本的尺寸与分段 -------------------------------------------------


@dataclass(frozen=True)
class InspectionPlan:
    """怎么把一张图送进去检。

    scale 是缩小比例（≤1），segments 是分段数。两者不会同时激进使用：
    缩到下限还超体积就转为分段，而不是继续缩。
    """

    scale: float
    segments: int

    @property
    def is_segmented(self) -> bool:
        return self.segments > 1


def plan_inspection(
    width: int,
    height: int,
    byte_size: int,
    *,
    max_bytes: int | None = None,
    min_dimension: int | None = None,
) -> InspectionPlan:
    """决定缩放与分段。

    这里有两个彼此独立的上限：
    1. 请求字节数：先在不低于分辨率下限的前提下缩小；仍超体积则分段。
    2. 纵横比：即使文件很小，超长图也必须分段，否则 provider 会把整图压进
       一张视觉 token 网格，正文缩到不可读后仍可能误判通过。

    最终分段数取两者较大值。
    """
    max_bytes = max_bytes if max_bytes is not None else settings.qa_max_request_bytes
    min_dimension = min_dimension if min_dimension is not None else settings.qa_min_inspect_dimension

    if width <= 0 or height <= 0:
        raise ValueError(f"图片尺寸必须为正，收到 {width}x{height}")

    aspect_segments = max(
        1,
        math.ceil(height / (width * MAX_INSPECTION_SEGMENT_ASPECT_RATIO)),
    )

    if byte_size <= max_bytes:
        return InspectionPlan(scale=1.0, segments=aspect_segments)

    # 允许的最大缩小比例：短边不能低于下限
    shortest = min(width, height)
    floor_scale = min(1.0, min_dimension / shortest) if shortest > min_dimension else 1.0

    # 体积大致随面积线性变化
    needed_scale = (max_bytes / byte_size) ** 0.5
    if needed_scale >= floor_scale:
        return InspectionPlan(
            scale=min(1.0, needed_scale),
            segments=aspect_segments,
        )

    # 缩到下限仍不够 —— 转为分段。绝不继续缩：读不出字的检查会报假通过。
    scale = floor_scale
    remaining = byte_size * (scale ** 2)
    size_segments = max(2, math.ceil(remaining / max_bytes))
    return InspectionPlan(scale=scale, segments=max(aspect_segments, size_segments))


def respects_resolution_floor(
    plan: InspectionPlan, width: int, height: int, min_dimension: int | None = None
) -> bool:
    min_dimension = min_dimension if min_dimension is not None else settings.qa_min_inspect_dimension
    shortest = min(width, height)
    if shortest <= min_dimension:
        return plan.scale >= 1.0
    return int(shortest * plan.scale) >= min_dimension


# --- 请求构造 -------------------------------------------------------------

_SYSTEM_PROMPT = """你是社交图片的准出检查员。只报告你在图中**实际看到**的缺陷。

必须检查这六类：
- missing_glyph：空心方框、□、豆腐块等字体缺失痕迹
- clipped_at_edge：文字被画幅边缘切断
- overflow：文字溢出所在的色块或卡片
- overlap：文字互相遮挡或被图形压住
- illegible：正文在预期观看尺寸下读不清
- missing_text：给定的文本没有出现在图中

只输出 JSON：{"pass": true|false, "defects": [{"category": "...", "location": "..."}]}
看不清某处时报告 illegible，不要猜。没有缺陷时 defects 为空数组。"""


def _image_mime_type(image_bytes: bytes) -> str:
    """按字节魔数返回 MIME，不能拿渲染阶段的旧扩展名猜。

    平台图在送检前已经编码成 JPEG q95 4:4:4。旧实现仍固定声明 image/png，
    provider 目前会嗅探并容忍，但请求本身是错的；换一个兼容端点就可能拒绝。
    """
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise ValueError("送检图片不是受支持的 PNG 或 JPEG")


def build_inspection_messages_for_images(
    images: list[bytes], expected_texts: list[str]
) -> list[dict]:
    """构造一张图或一组纵向连续分段的 Kimi typed-content 请求。

    所有分段必须放在同一次请求中。分开调用时，每个调用只看得到局部，却拿着
    全图的 expected_texts，必然把其它分段里的正常文本误报成 missing_text；
    不给 expected_texts 又无法证明字段完整。多图请求让模型能跨所有分段核对。
    """
    if not images:
        raise ValueError("至少需要一张送检图片")

    listed = "\n".join(f"- {text}" for text in expected_texts if text)
    if len(images) == 1:
        intro = "检查这张成品图。"
    else:
        intro = (
            f"以下 {len(images)} 张图片是同一张超长成品图按从上到下顺序切出的"
            "连续分段；必须把它们作为一个整体检查，分段边界本身不算画幅边缘。"
        )
    content: list[dict] = []
    for image_bytes in images:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        mime_type = _image_mime_type(image_bytes)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
            }
        )
    content.append(
        {
            "type": "text",
            "text": (
                f"{intro}下面这些文字都必须在整组图片中出现且清晰可读。"
                "逐项检查，不要只看标题：\n"
                f"{listed or '- （无指定文字）'}"
            ),
        }
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def build_inspection_messages(image_bytes: bytes, expected_texts: list[str]) -> list[dict]:
    """单图兼容入口；实际构造统一走多图函数。"""
    return build_inspection_messages_for_images([image_bytes], expected_texts)


def downscale_for_inspection(image_bytes: bytes, plan: InspectionPlan) -> bytes:
    """只缩送检副本。交付图保持全分辨率。"""
    if plan.scale >= 1.0:
        return image_bytes
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    new_size = (max(1, int(image.width * plan.scale)), max(1, int(image.height * plan.scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def split_for_inspection(image_bytes: bytes, segments: int) -> list[bytes]:
    """把送检副本纵向切成连续、无重叠、无缝隙的 PNG 分段。"""
    if segments <= 1:
        return [image_bytes]

    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as image:
        parts: list[bytes] = []
        for index in range(segments):
            top = image.height * index // segments
            bottom = image.height * (index + 1) // segments
            if bottom <= top:
                raise ValueError(
                    f"分段数 {segments} 超过图片高度 {image.height}，产生空分段"
                )
            crop = image.crop((0, top, image.width, bottom))
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG", optimize=True)
            parts.append(buffer.getvalue())
    return parts


def prepare_inspection_images(image_bytes: bytes) -> tuple[InspectionPlan, list[bytes]]:
    """把交付图变成视觉模型实际接收的一张或多张送检副本。"""
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
    plan = plan_inspection(width, height, len(image_bytes))
    downscaled = downscale_for_inspection(image_bytes, plan)
    parts = split_for_inspection(downscaled, plan.segments)
    raw_bytes = sum(len(part) for part in parts)
    # data URL 会做 base64，线上体积不是原始图片字节。每段独立编码，所以逐段向上
    # 取整；忘掉这 4/3 会让"60MB 以内"的本地判定在 provider 侧变成 80MB 请求。
    wire_bytes = sum(4 * ((len(part) + 2) // 3) for part in parts)
    if wire_bytes > settings.qa_max_request_bytes:
        # 多图在同一次请求里，分段只解决纵横比，不能凭空减少总字节。超过请求上限
        # 时宁可扣图，也不能让 provider 拒绝后被错误包装成"已检查"。
        raise VisionUnavailable(
            f"送检副本 base64 后有 {wire_bytes} 字节（原始 {raw_bytes}），超过上限 "
            f"{settings.qa_max_request_bytes}"
        )
    return plan, parts


class VisualQA:
    """视觉质检客户端。禁用时不声称通过，只声称"未检查"。"""

    def __init__(self) -> None:
        self.role = vision_role()

    @property
    def is_available(self) -> bool:
        return settings.visual_qa_enabled and self.role.is_configured

    async def inspect(self, image_bytes: bytes, expected_texts: list[str]) -> Verdict:
        """送检一张图。任何异常都向上抛成 VisionUnavailable，不吞成通过。"""
        role = require_capability(self.role, Capability.VISION)
        if not self.is_available:
            raise VisionUnavailable("视觉质检未启用或未配置")

        import httpx

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
        plan, inspected_images = prepare_inspection_images(image_bytes)
        if not respects_resolution_floor(plan, width, height):
            raise VisionUnavailable(
                "送检副本会低于分辨率下限；读不出文字的检查会报假通过，因此拒绝送检"
            )

        logger.info(
            "视觉送检计划 | 原图=%sx%s %s字节 | 缩放=%.3f | 连续分段=%s | 送检=%s字节",
            width,
            height,
            len(image_bytes),
            plan.scale,
            len(inspected_images),
            sum(len(part) for part in inspected_images),
        )
        endpoint = f"{role.base_url}/chat/completions"
        body = {
            "model": role.model,
            "messages": build_inspection_messages_for_images(
                inspected_images, expected_texts
            ),
        }
        # 不带 temperature。kimi-k3 对该字段实测直接 400：
        # "invalid temperature: only 1 is allowed for this model"。
        # 而这里 400 的后果不是"少一次质检"——inspect 会抛 VisionUnavailable，
        # 于是每张图都被扣下，整组平台图消失。确定性靠 prompt 约束输出格式，
        # 不靠猜一个 provider 不接受的采样参数。
        headers = {"Authorization": f"Bearer {role.api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=settings.qa_timeout_seconds, trust_env=False) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                if response.status_code >= 400:
                    raise VisionUnavailable(
                        f"视觉质检接口 status={response.status_code}: {response.text.strip()[:200]}"
                    )
                data = response.json()
        except VisionUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VisionUnavailable(f"视觉质检请求失败: {exc}") from exc
        finally:
            # 无论成败都计一次：调用发生了，钱也花了
            role_usage.record("vision")

        content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        verdict = parse_verdict(content or "")
        logger.info(
            "视觉质检结论 | 通过=%s | 缺陷=%s",
            verdict.passed,
            ", ".join(d.category.value for d in verdict.defects) or "无",
        )
        return verdict


visual_qa = VisualQA()
