"""附件预算：超过邮件服务商的体积上限时丢哪几张。

顺序是固定并且写下来的，不是"按大小丢最大的"。按大小丢会让每天丢掉的东西
不一样，读者无法形成预期；而固定顺序意味着"今天没有 IG 图"总是同一个原因。

长图永远第一个保留：它是这次改动的主交付物，其余平台图都是它的衍生品。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# 正文 HTML + 纯文本 + mixed/alternative 边界与附件头的保守预留。实测正式正文
# 约 34KB；留 512KiB 是为了模板增长时不把 SMTP 线上体积顶过限速拐点。
MESSAGE_BODY_RESERVE_BYTES = 512 * 1024
# email.encoders.encode_base64 每 76 个字符折行。SMTP 最终使用 CRLF，所以每行按
# 2 字节计算；附件自己的 MIME 头再留 1KiB。
BASE64_LINE_LENGTH = 76
ATTACHMENT_HEADER_RESERVE_BYTES = 1024


# 丢弃顺序：从最先丢到最后丢。
# 依据是"重做成本 + 不可替代性"：
# - Instagram / X 单张卡最容易在别处补（一张图一个主张，手工也能拼）
# - 小红书内容页从后往前丢，因为它是有序的，丢尾页只损失最靠后的条目
# - 小红书封面最后丢：没有封面整组图就不成帖
PLATFORM_DROP_ORDER: tuple[str, ...] = (
    "ig-square",
    "x-card",
    "xhs-content-3",
    "xhs-content-2",
    "xhs-content-1",
    "xhs-cover",
)

# 长图的槽位名。它不在丢弃顺序里 —— 它不可丢。
# 名字与 spec 里的 digest-full.png 对齐，加上日期前缀后是 2026-08-01-digest-full.png。
LONG_IMAGE_SLUG = "digest-full"


@dataclass(frozen=True)
class Attachment:
    slug: str
    filename: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


def base64_wire_size(raw_size: int) -> int:
    """一个附件进入 MIME 后的保守线上字节数（base64 + CRLF + 附件头）。"""
    encoded = 4 * ((raw_size + 2) // 3)
    lines = (encoded + BASE64_LINE_LENGTH - 1) // BASE64_LINE_LENGTH
    return encoded + 2 * lines + ATTACHMENT_HEADER_RESERVE_BYTES


def estimated_message_wire_size(attachments: list[Attachment]) -> int:
    """整封信在 SMTP DATA 阶段的估算体积，而不是原始文件体积。"""
    return MESSAGE_BODY_RESERVE_BYTES + sum(base64_wire_size(item.size) for item in attachments)


@dataclass
class BudgetResult:
    kept: list[Attachment]
    dropped: list[tuple[str, str]]  # (slug, 原因)

    @property
    def total_size(self) -> int:
        """保留附件的原始字节数；仅用于展示，不用于预算判定。"""
        return sum(a.size for a in self.kept)

    @property
    def estimated_wire_size(self) -> int:
        return estimated_message_wire_size(self.kept)


def apply_budget(
    attachments: list[Attachment],
    budget_bytes: int | None = None,
) -> BudgetResult:
    """按固定顺序丢弃，直到**SMTP DATA 估算体积**进入预算。

    先保长图、先丢平台衍生图；如果只剩长图仍超预算，长图也必须扣下并点名。
    让服务商拒收整封信会连正式摘要正文一起丢掉，违反"邮件每天到达优先"。
    """
    budget_bytes = budget_bytes if budget_bytes is not None else settings.attachment_budget_bytes

    by_slug = {a.slug: a for a in attachments}
    kept_slugs = [a.slug for a in attachments]
    dropped: list[tuple[str, str]] = []

    def total() -> int:
        return estimated_message_wire_size([by_slug[slug] for slug in kept_slugs])

    reason = f"SMTP DATA 估算体积超出预算 {budget_bytes} 字节"
    for slug in PLATFORM_DROP_ORDER:
        if total() <= budget_bytes:
            break
        if slug in kept_slugs:
            kept_slugs.remove(slug)
            dropped.append((slug, reason))

    if total() > budget_bytes and LONG_IMAGE_SLUG in kept_slugs:
        kept_slugs.remove(LONG_IMAGE_SLUG)
        dropped.append((LONG_IMAGE_SLUG, reason + "；为保证正式摘要正文可投递，长图也被扣下"))
        logger.warning(
            "长图单张的 SMTP DATA 估算体积超预算；扣下长图以保证正文邮件可达"
        )

    return BudgetResult(kept=[by_slug[s] for s in kept_slugs], dropped=dropped)


def attachment_filename(slug: str, digest_label: str, extension: str = "png") -> str:
    """带日期的文件名，连续几天不会互相覆盖。"""
    return f"{digest_label}-{slug}.{extension}"
