"""渲染前的字体自检。

这个模块存在的唯一理由是豆腐块：缺字体时 Chromium 不报错、不警告，直接把
汉字画成空心方框，把 emoji 画成方框。缺陷只在成品图里可见，而如果没有自检，
发现方式就是让视觉质检把每张图的重试预算耗光 —— 花一整轮 vision 调用的钱，
只为了得到"字体没装"这一个事实。

所以：启动时用 fontconfig 问一次（Chromium 在 Linux 上正是通过 fontconfig
解析字体），拿到实际族名写进日志，缺任何一类就拒绝渲染。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# fontconfig 的语言标签查询。zh-cn 覆盖简体中文；
# und-zsye 是 fontconfig 2.13+ 给 emoji 字体分配的标签。
_CJK_QUERY = ":lang=zh-cn"
_EMOJI_QUERY = ":lang=und-zsye"

# 送进浏览器的兜底字符串，只在 fontconfig 不可用时使用（例如本地 macOS 开发）。
_GENERIC_CJK_FALLBACKS = ("Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "Heiti SC")
_GENERIC_EMOJI_FALLBACKS = ("Noto Color Emoji", "Apple Color Emoji")

# 简体中文族的优先级。为什么需要排序而不是直接取 fc-list 的前几个：
# fonts-noto-cjk 一个包就装出 15 个匹配 :lang=zh-cn 的族（SC/TC/HK/JP/KR ×
# Sans/Serif/Mono），而 fc-list 的输出顺序不保证。容器里实测拿到的前三个是
# "Noto Serif CJK JP / KR / HK" —— 于是简体正文用日文字形变体渲染。
# 这不是豆腐块（每个字都有字形），所以像素级的方框检测放它过去，视觉质检也
# 大概率报通过，缺陷只体现为"字看着有点怪"：直、骨、込 在 SC 与 JP 里是不同
# 字形，已用同一个 .ttc 的逐像素指纹证实。
# 排序规则：先按语言变体（SC 最优，TC/HK 次之，JP/KR 最差），再按字型
# （Sans 优于 Serif，正文用无衬线），Mono 排到最后（等宽正文会撑破排版）。
_CJK_LANG_RANK = (("CJK SC", 0), ("SC", 1), ("CJK TC", 2), ("CJK HK", 3), ("TC", 4), ("HK", 5))
_CJK_STYLE_RANK = (("Mono", 2), ("Serif", 1))


def _cjk_family_priority(name: str) -> tuple[int, int, str]:
    """(语言变体, 字型, 名字) —— 越小越优先。名字参与排序只为让结果稳定。"""
    lang = next((rank for token, rank in _CJK_LANG_RANK if token in name), 9)
    style = next((rank for token, rank in _CJK_STYLE_RANK if token in name), 0)
    return (lang, style, name)


def _order_cjk_families(families: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(families, key=_cjk_family_priority))


_FC_TIMEOUT_SECONDS = 10


class FontUnavailableError(RuntimeError):
    """缺少中文或 emoji 字体。抛出即意味着本次不渲染。"""


@dataclass(frozen=True)
class FontReport:
    cjk_families: tuple[str, ...]
    emoji_families: tuple[str, ...]
    fontconfig_available: bool

    def __post_init__(self) -> None:
        """中文族在构造时就排好序。

        排序放在这里而不是放在 inspect_fonts() 或 font_stack() 里，是因为这两个
        地方都会读 cjk_families：一个写日志，一个决定浏览器实际用哪个族。只在
        其中一处排序，就会出现"日志说用 SC、浏览器用 JP"这种查不出来的分歧。
        """
        object.__setattr__(self, "cjk_families", _order_cjk_families(self.cjk_families))

    @property
    def has_cjk(self) -> bool:
        return bool(self.cjk_families)

    @property
    def has_emoji(self) -> bool:
        return bool(self.emoji_families)

    @property
    def is_complete(self) -> bool:
        return self.has_cjk and self.has_emoji

    def missing(self) -> tuple[str, ...]:
        gaps = []
        if not self.has_cjk:
            gaps.append("简体中文字体（fonts-noto-cjk）")
        if not self.has_emoji:
            gaps.append("彩色 emoji 字体（fonts-noto-color-emoji，必须是 CBDT 位图版）")
        return tuple(gaps)


def _query_families(query: str) -> tuple[str, ...]:
    """用 fc-list 列出满足查询的字体族名。

    刻意不用 fc-match：fc-match 永远返回一个结果（最差也给 DejaVu Sans），
    "有返回"不等于"有字形"，用它做存在性判断会得到假通过。
    """
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return ()
    try:
        result = subprocess.run(
            [fc_list, query, "family"],
            capture_output=True,
            text=True,
            timeout=_FC_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("fc-list 查询失败 [%s]: %s", query, exc)
        return ()

    families: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        # 一行可能是 "Noto Sans CJK SC,思源黑体"，取第一个可读族名
        name = line.split(",")[0].strip()
        if name and name not in seen:
            seen.add(name)
            families.append(name)
    return tuple(families)


def inspect_fonts() -> FontReport:
    """查询系统字体现状。不抛错，只报告。"""
    available = shutil.which("fc-list") is not None
    if not available:
        # 本地 darwin 开发常态。不假装通过，也不假装失败 —— 由调用方决定。
        logger.info("未找到 fontconfig（fc-list），跳过字体族枚举")
        return FontReport((), (), fontconfig_available=False)
    return FontReport(
        cjk_families=_query_families(_CJK_QUERY),
        emoji_families=_query_families(_EMOJI_QUERY),
        fontconfig_available=True,
    )


def verify_fonts_or_raise(report: FontReport | None = None) -> FontReport:
    """渲染前调用。缺字体就抛错，绝不"先渲染再看看"。"""
    report = report if report is not None else inspect_fonts()

    if not report.fontconfig_available:
        raise FontUnavailableError(
            "无法通过 fontconfig 确认中文与 emoji 字体是否存在。"
            "渲染必须在装有 fontconfig 的容器内执行 —— 未经确认就渲染，"
            "缺字体的结果是静默的空心方框而不是报错。"
        )

    if not report.is_complete:
        raise FontUnavailableError(
            "渲染字体不完整，缺少：" + "、".join(report.missing()) +
            "。缺字体时 Chromium 不报错，直接把字符画成空心方框，"
            "所以这里拒绝渲染而不是产出带豆腐块的图。"
        )

    logger.info(
        "字体自检通过 | 中文族=%s | emoji 族=%s",
        ", ".join(report.cjk_families[:3]),
        ", ".join(report.emoji_families[:3]),
    )
    return report


def font_stack(report: FontReport | None = None) -> str:
    """构建 CSS font-family 值，实现逐字符回退。

    浏览器对 font-family 列表是逐字符匹配的：某个字符在前一个族里没有字形，
    就继续往后找。所以中文族与 emoji 族都必须显式出现在同一个栈里 ——
    只写中文族时，emoji 会落到默认族上变成方框。
    """
    report = report if report is not None else inspect_fonts()

    stack: list[str] = [
        "-apple-system",
        "BlinkMacSystemFont",
        "Segoe UI",
        "Helvetica Neue",
        "Arial",
    ]
    cjk = list(report.cjk_families[:3]) or list(_GENERIC_CJK_FALLBACKS)
    emoji = list(report.emoji_families[:2]) or list(_GENERIC_EMOJI_FALLBACKS)

    stack.extend(cjk)
    # emoji 族放在 sans-serif 之前：sans-serif 会匹配上任何字符，
    # 排在它后面的族永远轮不到。
    stack.extend(emoji)
    stack.append("sans-serif")

    seen: set[str] = set()
    quoted: list[str] = []
    for name in stack:
        if name in seen:
            continue
        seen.add(name)
        quoted.append(f"'{name}'" if " " in name else name)
    return ", ".join(quoted)
