"""平台文案的字数计算与接地校验。

两处容易写错、且错了会在发布时才暴露的地方：

1. **X 把 CJK 按两个字符计入 280。** 用 `len()` 算中文文案会过校验、发帖被拒。
   拒绝发生在平台侧，本地看不出来。
2. **文案里的链接和数字必须来自摘要。** 模型很会编一个看起来对的仓库地址或
   star 数。编造的内容不能被"悄悄改正" —— 悄悄改会把一次幻觉变成一条
   看不见的事实错误，所以校验失败就是这个平台的文案失败。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.publishers.styles import PlatformStyle

# CJK 统一汉字、扩展 A、兼容表意文字，以及 CJK 标点、假名、全角形式。
# X 把这些都按两个字符计。
_WIDE_RANGES = (
    (0x1100, 0x115F),    # 韩文字母
    (0x2E80, 0x303E),    # CJK 部首与标点
    (0x3041, 0x33FF),    # 假名、注音、兼容
    (0x3400, 0x4DBF),    # 扩展 A
    (0x4E00, 0x9FFF),    # 统一汉字
    (0xA000, 0xA4CF),    # 彝文
    (0xAC00, 0xD7A3),    # 韩文音节
    (0xF900, 0xFAFF),    # 兼容表意
    (0xFE30, 0xFE4F),    # CJK 兼容形式
    (0xFF00, 0xFF60),    # 全角形式
    (0xFFE0, 0xFFE6),
    (0x20000, 0x2FFFD),  # 扩展 B 及以后
    (0x30000, 0x3FFFD),
)

# URL 用正向字符集，不再维护“哪些中英文标点不属于 URL”的黑名单。
#
# 真实端到端里，小红书/微信/知乎三份文案都用了中文包裹格式：
#   （https://github.com/org/repo）：说明文字
# 旧正则排除了 ASCII `)`，却漏了全角 `）` 和中文分号 `；`，于是把右括号与
# 后续中文一起吞进 URL，三个**真实链接**全被误报成模型编造。继续往黑名单补字符
# 没有尽头；RFC 3986 URL 本来就应由 ASCII 字符组成，国际化域名应使用 punycode，
# 所以只接受 URI 的 ASCII 字符集，遇到任何 CJK 字符自然停止。
URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
# 这些 ASCII 标点既可出现在 URL 内，也常被自然语言当作句尾。只从尾部剥离；
# `)` / `]` 单独按配平处理，不能无脑剥，否则 Wikipedia 的 `Foo_(bar)` 会被截坏。
_URL_TRAILING_PUNCTUATION = ".,;:!?\"'"
NUMBER_PATTERN = re.compile(r"\d[\d,\.]*[kKmM]?")
HASHTAG_PATTERN = re.compile(r"#[^\s#，。！？]+")


def _trim_url_wrapper(url: str) -> str:
    """剥掉包裹 URL 的句尾标点，同时保留 URL 自身配平的括号。"""
    while url:
        if url[-1] in _URL_TRAILING_PUNCTUATION:
            url = url[:-1]
            continue
        if url[-1] == ")" and url.count(")") > url.count("("):
            url = url[:-1]
            continue
        if url[-1] == "]" and url.count("]") > url.count("["):
            url = url[:-1]
            continue
        break
    return url


def _extract_urls(text: str) -> list[str]:
    """从自然语言文案中提取 URL；返回值已去掉外层标点。"""
    return [_trim_url_wrapper(match) for match in URL_PATTERN.findall(text)]


def _is_wide(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _WIDE_RANGES)


def weighted_length(text: str, counts_cjk_as_two: bool) -> int:
    """按平台规则计长度。

    X 的 280 是"加权字符数"，不是 `len()`。用 `len()` 算中文会过本地校验、
    在平台侧被拒 —— 而那时候已经在发布流程里了。
    """
    if not counts_cjk_as_two:
        return len(text)
    return sum(2 if _is_wide(char) else 1 for char in text)


def fits_limit(text: str, limit: int, counts_cjk_as_two: bool) -> bool:
    return weighted_length(text, counts_cjk_as_two) <= limit


def truncate_weighted(text: str, limit: int, counts_cjk_as_two: bool, ellipsis: str = "") -> str:
    """兼容旧 API，但不再截断或生成省略号。

    平台硬限制必须由文案修正调用解决；本地截断会丢失事实内容并掩盖失败原因。
    """
    return text


# --- 接地校验 -------------------------------------------------------------


@dataclass(frozen=True)
class Grounding:
    """当天摘要提供的事实集合。文案不得越出这个集合。"""

    urls: frozenset[str]
    numbers: frozenset[str]

    @classmethod
    def from_items(cls, items: list[dict]) -> "Grounding":
        urls: set[str] = set()
        numbers: set[str] = set()
        for item in items:
            for key in ("repo_url", "arxiv_url", "video_url"):
                value = item.get(key)
                if value:
                    urls.add(_normalize_url(str(value)))
            for key in ("github_urls",):
                for value in item.get(key) or []:
                    urls.add(_normalize_url(str(value)))
            for key in ("stars", "forks", "recent_stars", "stars_today", "view_count",
                        "recent_issue_comments", "open_issues"):
                value = item.get(key)
                if isinstance(value, int):
                    numbers.add(str(value))
                    numbers.add(_format_compact(value))
        return cls(urls=frozenset(urls), numbers=frozenset(numbers))


def _normalize_url(url: str) -> str:
    return url.rstrip("/").lower()


def _format_compact(value: int) -> str:
    """复用邮件里的写法，好让 "12.3K" 这种引用也能被认出来是接地的。"""
    from app.utils.helpers import format_number

    return format_number(value).lower()


@dataclass(frozen=True)
class GroundingFailure:
    kind: str  # url / number
    value: str


def check_grounding(text: str, grounding: Grounding, *, check_numbers: bool = True) -> list[GroundingFailure]:
    """找出文案里所有不在摘要事实集合中的链接与指标数字。

    返回失败列表而不是清洗后的文本：悄悄改正会把一次幻觉变成一条看不见的
    事实错误，而看不见的错误比看得见的失败更贵。
    """
    failures: list[GroundingFailure] = []

    for url in _extract_urls(text):
        if _normalize_url(url) not in grounding.urls:
            failures.append(GroundingFailure("url", url))

    if check_numbers:
        known = {n.lower() for n in grounding.numbers}
        for token in _statistic_tokens(text):
            if token.replace(",", "").lower() not in known:
                failures.append(GroundingFailure("number", token))

    return failures


# 指标词。数字只有出现在指标语境里才算"引用了一个统计量"；
# 否则日期、序号、版本号都会被判成编造，每条文案都会失败。
_METRIC_WORDS = (
    "star", "stars", "⭐", "fork", "forks", "watch", "watcher", "watchers",
    "view", "views", "download", "downloads", "issue", "issues", "comment", "comments",
    "收藏", "点赞", "观看", "评论", "下载", "关注",
)
_METRIC_ALTERNATION = "|".join(re.escape(word) for word in _METRIC_WORDS)
# 数字在指标词之前（"4200 stars"）或之后（"stars: 4200"）
_METRIC_BEFORE = re.compile(
    rf"(\d[\d,\.]*\s*[kKmM]?)\s*(?:个|次)?\s*(?:{_METRIC_ALTERNATION})", re.IGNORECASE
)
_METRIC_AFTER = re.compile(
    rf"(?:{_METRIC_ALTERNATION})\s*[:：+]?\s*(\d[\d,\.]*\s*[kKmM]?)", re.IGNORECASE
)
# 带 k/m 后缀的数字总是统计量，无论上下文
_SUFFIXED = re.compile(r"\b(\d[\d,\.]*\s*[kKmM])\b")


def _statistic_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for pattern in (_METRIC_BEFORE, _METRIC_AFTER, _SUFFIXED):
        for match in pattern.findall(text):
            token = match.strip().strip(".,")
            if token:
                tokens.append(re.sub(r"\s+", "", token))
    return tokens


# --- 平台校验 -------------------------------------------------------------


@dataclass(frozen=True)
class CopyDraft:
    platform: str
    title: str
    body: str
    hashtags: tuple[str, ...] = ()
    # X 的有序 thread；旧 payload 没有该字段时退化为单个 body post。
    thread: tuple[str, ...] = ()


@dataclass(frozen=True)
class CopyIssue:
    field: str
    detail: str


def validate_copy(draft: CopyDraft, style: PlatformStyle, grounding: Grounding) -> list[CopyIssue]:
    """校验一个平台的文案。返回问题列表，空列表表示可发。"""
    issues: list[CopyIssue] = []
    rules = style.copy

    omission = re.compile(r"(?:\.{2,}|…+|。{2,})")
    checked_texts = [
        ("title", draft.title),
        ("body", draft.body),
        ("hashtags", " ".join(draft.hashtags)),
        *(("body", part) for part in draft.thread),
    ]
    for field, text in checked_texts:
        if omission.search(text):
            issues.append(CopyIssue(field, "包含省略号或连续句点，必须改写为完整文本"))

    if rules.title_max_chars is not None and draft.title:
        if not fits_limit(draft.title, rules.title_max_chars, rules.counts_cjk_as_two):
            issues.append(
                CopyIssue("title", f"标题超过 {rules.title_max_chars} 字（按平台计数规则）")
            )

    body_parts = draft.thread if style.key == "x" and draft.thread else (draft.body,)
    for index, part in enumerate(body_parts, start=1):
        if not part.strip():
            issues.append(CopyIssue("body", f"第 {index} 条 thread 为空"))
            continue
        if not fits_limit(part, rules.body_max_chars, rules.counts_cjk_as_two):
            label = f"thread 第 {index} 条" if len(body_parts) > 1 else "正文"
            issues.append(
                CopyIssue(
                    "body",
                    f"{label} {weighted_length(part, rules.counts_cjk_as_two)} "
                    f"超过 {rules.body_max_chars}（CJK 计两字={rules.counts_cjk_as_two}）",
                )
            )

    if not rules.allow_hashtags:
        if draft.hashtags or HASHTAG_PATTERN.search(draft.body):
            issues.append(CopyIssue("hashtags", f"{style.display_name} 不使用标签"))
    else:
        count = len(draft.hashtags)
        if count < rules.hashtag_min or count > rules.hashtag_max:
            issues.append(
                CopyIssue("hashtags", f"标签数 {count} 不在 {rules.hashtag_min}–{rules.hashtag_max}")
            )

    for failure in check_grounding(f"{draft.title}\n{draft.body}", grounding):
        issues.append(
            CopyIssue(
                "grounding",
                f"{failure.kind} '{failure.value}' 不在当天摘要中；"
                "编造内容按该平台文案失败处理，不做静默修改",
            )
        )

    return issues


def enforce_limits(draft: CopyDraft, style: PlatformStyle) -> CopyDraft:
    """返回原文，让超限结果进入明确的修正/失败路径。"""
    return draft
