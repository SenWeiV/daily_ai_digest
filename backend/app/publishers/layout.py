"""平台图片的文字适配：截断与字号降级。

这里的两个函数是视觉质检唯一能"改参数重试"的手柄。质检报了溢出，重试必须
带着一个不同的参数回来 —— 相同参数的重试是 bug，它只会得到相同的缺陷和
更少的预算。所以截断长度和字号档位都做成可枚举的、单调收紧的序列。
"""

from __future__ import annotations

from dataclasses import dataclass

# 字号档位。每一档整体缩小，档位之间的比例保持一致，
# 这样降级后多页之间的视觉层级不会错乱。
TYPE_SCALE_STEPS: tuple[float, ...] = (1.0, 0.92, 0.84, 0.76, 0.68, 0.60)


def truncate_to(text: str, max_chars: int, *, ellipsis: str = "") -> str:
    """保留完整字段；尺寸参数只作为布局预算，不得静默丢字。

    HTML/CSS 负责换行，视觉 QA 负责发现真正的溢出。过去在这里加省略号会让
    已通过接地校验的事实内容变成不可恢复的半句话。
    """
    return text


@dataclass(frozen=True)
class TypeScale:
    """字号档位。step 越大字越小。"""

    step: int = 0

    @property
    def factor(self) -> float:
        return TYPE_SCALE_STEPS[min(self.step, len(TYPE_SCALE_STEPS) - 1)]

    @property
    def can_reduce(self) -> bool:
        return self.step < len(TYPE_SCALE_STEPS) - 1

    def reduced(self) -> "TypeScale":
        """降一档。已到最小档时抛错而不是静默返回自己 —— 静默返回会让
        质检重试拿到和上次完全相同的参数。"""
        if not self.can_reduce:
            raise ValueError(
                f"字号已降到最小档（step={self.step}），无法再降。"
                "此时应当减少内容或放弃这张图，而不是用相同参数重试。"
            )
        return TypeScale(self.step + 1)

    def px(self, base_px: float) -> float:
        return round(base_px * self.factor, 2)


def tightened_limit(max_chars: int, attempt: int) -> int:
    """按尝试次数逐步收紧截断长度。

    每次收紧 15%，并保证严格递减：不递减的"收紧"等于没有改参数。
    """
    if attempt <= 0:
        return max_chars
    limit = max_chars
    for _ in range(attempt):
        limit = max(4, int(limit * 0.85) - 1)
    return limit
