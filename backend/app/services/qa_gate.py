"""渲染 → 质检 → 定向修正 → 复检 的有界循环。

这个模块只做一件事：保证每次重试都带着**不同的参数**回来。相同参数的重试
不是保守，是 bug —— 它必然得到相同的缺陷，只是把预算烧完。所以循环维护一个
`Correction` 状态，每轮根据上一轮报的缺陷类别推进它；推不动了就停止重试，
因为再试也是原地重放。

尝试用尽后这张图**不发**，并记下是哪张图、哪类缺陷。绝不换一张占位图或
低质量替代品顶上去 —— 读者会以为那就是今天的成品。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Awaitable, Callable

from app.config import settings
from app.publishers.layout import TypeScale, tightened_limit
from app.services.visual_qa import (
    CORRECTION_FOR,
    Defect,
    Verdict,
    VisionUnavailable,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Correction:
    """一次渲染要用的修正参数。字段全变化过就没有下一步了。"""

    attempt: int = 0
    use_fallback_font: bool = False
    truncation_attempt: int = 0
    type_scale: TypeScale = TypeScale()
    content_reduction: int = 0

    def signature(self) -> tuple:
        """用于判断"这次和上次是否真的不同"。"""
        return (
            self.use_fallback_font,
            self.truncation_attempt,
            self.type_scale.step,
            self.content_reduction,
        )


def next_correction(current: Correction, defects: tuple[Defect, ...]) -> Correction | None:
    """按报告的缺陷推进修正参数。推不动就返回 None。

    返回 None 而不是原样返回，是为了让"无法改进"在调用处显式终止，
    而不是变成一次无意义的重试。
    """
    actions = {CORRECTION_FOR[d] for d in defects if d in CORRECTION_FOR}
    if not actions:
        # 报了失败但没有可识别的缺陷类别：无从下手，不要瞎试
        return None

    candidate = replace(current, attempt=current.attempt + 1)

    if "fallback_font" in actions and not candidate.use_fallback_font:
        candidate = replace(candidate, use_fallback_font=True)
    if "tighter_truncation" in actions:
        candidate = replace(candidate, truncation_attempt=candidate.truncation_attempt + 1)
    if "reduce_type_scale" in actions and candidate.type_scale.can_reduce:
        candidate = replace(candidate, type_scale=candidate.type_scale.reduced())
    if "reduce_content" in actions:
        # 先降字号，降不动了再砍内容 —— 砍内容是信息损失，排在最后
        if candidate.type_scale.can_reduce and "reduce_type_scale" not in actions:
            candidate = replace(candidate, type_scale=candidate.type_scale.reduced())
        else:
            candidate = replace(candidate, content_reduction=candidate.content_reduction + 1)

    if candidate.signature() == current.signature():
        # 所有可用手段都用尽了。相同参数重试是 bug。
        return None
    return candidate


def truncation_limit(base_limit: int, correction: Correction) -> int:
    return tightened_limit(base_limit, correction.truncation_attempt)


@dataclass
class GateResult:
    """一张图的最终结果。"""

    slug: str
    image: bytes | None
    attempts: int
    passed: bool
    withheld_reason: str = ""
    defect_categories: tuple[Defect, ...] = ()

    @property
    def withheld(self) -> bool:
        return self.image is None


async def run_gate(
    slug: str,
    render: Callable[[Correction], Awaitable[bytes]],
    inspect: Callable[[bytes], Awaitable[Verdict]],
    expected_texts: list[str] | None = None,
    max_attempts: int | None = None,
) -> GateResult:
    """跑完一张图的质检循环。

    视觉模型不可达时不标记任何图为通过 —— 未经检查的图和检查通过的图必须
    区别对待，否则质检形同不存在。
    """
    max_attempts = max_attempts if max_attempts is not None else settings.qa_max_attempts
    correction = Correction()
    last_defects: tuple[Defect, ...] = ()
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            image = await render(correction)
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片渲染失败 [%s] 第 %s 次: %s", slug, attempt, exc)
            return GateResult(slug, None, attempt, False, f"渲染失败: {exc}")

        try:
            verdict = await inspect(image)
        except VisionUnavailable as exc:
            # 不可达 ≠ 通过。宁可不发这张图。
            logger.error("视觉质检不可达 [%s]: %s", slug, exc)
            return GateResult(slug, None, attempt, False, f"视觉质检不可达: {exc}")

        logger.info(
            "质检结果 [%s] 第 %s/%s 次 | 通过=%s | 缺陷=%s",
            slug,
            attempt,
            max_attempts,
            verdict.passed,
            ", ".join(d.category.value for d in verdict.defects) or "无",
        )

        if verdict.passed:
            return GateResult(slug, image, attempt, True)

        last_defects = verdict.categories
        advanced = next_correction(correction, last_defects)
        if advanced is None:
            return GateResult(
                slug,
                None,
                attempt,
                False,
                "无法通过定向修正改善，已停止重试（相同参数重试不会改变结果）",
                last_defects,
            )
        correction = advanced

    return GateResult(
        slug,
        None,
        attempts,
        False,
        f"重试 {attempts} 次仍未通过",
        last_defects,
    )
