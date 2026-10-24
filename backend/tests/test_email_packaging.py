"""单封邮件打包的测试

对应 add-longimage-and-publishers §9。核心结构断言：
mixed 外层 + alternative 内层。反过来（直接往 alternative 上挂附件）会让
部分客户端把图片当成正文的替代版本，正文因此消失 —— 这是"图片把正文顶掉"
的实际机制。
"""

import asyncio
from datetime import date

import pytest

from app.publishers.email_sections import (
    render_copy_section_html,
    render_copy_section_text,
    render_withheld_html,
)
from app.publishers.validation import CopyDraft, CopyIssue
from app.schemas import ArxivDigestItem, GitHubDigestItem
from app.services.attachment_budget import (
    LONG_IMAGE_SLUG,
    PLATFORM_DROP_ORDER,
    Attachment,
    apply_budget,
    attachment_filename,
    base64_wire_size,
    estimated_message_wire_size,
)
from app.services.email_service import EmailService


def _github():
    return [GitHubDigestItem(repo_name="org/repo", repo_url="https://github.com/org/repo", stars=100)]


def _arxiv():
    return [
        ArxivDigestItem(
            arxiv_id="2501.00001",
            title="Paper",
            abstract="abs",
            arxiv_url="https://arxiv.org/abs/2501.00001",
        )
    ]


def _attachment(slug: str, size: int) -> Attachment:
    return Attachment(slug=slug, filename=f"{slug}.png", content=b"x" * size)


class _CapturingService(EmailService):
    """替换 SMTP 发送，捕获构造好的 message。"""

    def __init__(self):
        super().__init__()
        self.sender_email = "sender@example.com"
        self.app_password = "secret"
        self.recipient_email = "to@example.com"
        self.sent = []

    async def _deliver(self, msg, recipient):  # pragma: no cover - 覆盖真实发送
        self.sent.append(msg)
        return True


def _send(service, **kwargs):
    async def _fake_smtp(*args, **kwargs_inner):
        raise AssertionError("测试不应触达真实 SMTP")

    return kwargs


# --- MIME 结构 ------------------------------------------------------------


def _build_message(attachments=None, copy_html="", copy_text="", withheld_html="", recipient=None):
    """复用 send_digest_email 的构造逻辑，但不发送。"""
    service = _CapturingService()
    sent = {}

    import aiosmtplib

    class _FakeSMTP:
        def __init__(self, **kwargs):
            sent.setdefault("kwargs", kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def login(self, *args):
            return None

        async def starttls(self, *args, **kwargs):
            return None

        async def sendmail(self, sender, recipient, raw):
            sent["raw"] = raw
            sent["recipients"] = recipient
            sent["count"] = sent.get("count", 0) + 1

    original = aiosmtplib.SMTP
    aiosmtplib.SMTP = _FakeSMTP
    try:
        ok = asyncio.run(
            service.send_digest_email(
                date(2026, 8, 1),
                _github(),
                arxiv_items=_arxiv(),
                daily_summary="今日概览",
                attachments=attachments,
                copy_section_html=copy_html,
                copy_section_text=copy_text,
                withheld_html=withheld_html,
                recipient=recipient,
            )
        )
    finally:
        aiosmtplib.SMTP = original

    import email

    _build_message.last_kwargs = sent.get("kwargs", {})
    _build_message.last_recipients = sent.get("recipients")
    return ok, email.message_from_string(sent["raw"]), sent.get("count", 0)


def test_body_parts_sit_in_alternative_nested_in_mixed():
    ok, message, _ = _build_message(attachments=[_attachment(LONG_IMAGE_SLUG, 100)])
    assert ok is True
    assert message.get_content_type() == "multipart/mixed"
    first = message.get_payload(0)
    assert first.get_content_type() == "multipart/alternative"
    assert {p.get_content_type() for p in first.get_payload()} == {"text/plain", "text/html"}


def test_attachments_are_siblings_of_the_alternative_part():
    ok, message, _ = _build_message(attachments=[_attachment(LONG_IMAGE_SLUG, 100)])
    types = [p.get_content_type() for p in message.get_payload()]
    assert types[0] == "multipart/alternative"
    assert any(t.startswith("image/") for t in types[1:])


def test_message_with_no_attachments_is_still_valid():
    ok, message, _ = _build_message(attachments=[])
    assert ok is True
    assert message.get_content_type() == "multipart/mixed"
    assert message.get_payload(0).get_content_type() == "multipart/alternative"


def test_exactly_one_message_is_sent_per_digest():
    """不拆信、不为迟到的资产补发第二封。"""
    _, _, count = _build_message(attachments=[_attachment("x-card", 10)])
    assert count == 1


def test_attachment_uses_the_date_stamped_filename():
    ok, message, _ = _build_message(
        attachments=[Attachment("x-card", attachment_filename("x-card", "2026-08-01"), b"data")]
    )
    filenames = [p.get_filename() for p in message.get_payload()[1:]]
    assert "2026-08-01-x-card.png" in filenames


def test_subtype_comes_from_the_filename_not_content_sniffing():
    """内容嗅探失败会抛 TypeError，一张认不出类型的图会让整封邮件发不出去。"""
    ok, message, _ = _build_message(
        attachments=[Attachment("x-card", "2026-08-01-x-card.png", b"not a real png")]
    )
    assert ok is True
    assert message.get_payload(1).get_content_type() == "image/png"


def test_existing_sections_are_unchanged():
    _, message, _ = _build_message()
    html = message.get_payload(0).get_payload(1).get_payload(decode=True).decode("utf-8")
    assert "GitHub Top 1" in html
    assert "arXiv 精选 1" in html
    assert "YouTube" not in html
    assert "🐙" in html


def test_copy_section_appears_after_the_main_sections():
    section = render_copy_section_html(
        {"x": CopyDraft("x", "", "post body")}, set(), {}, {"x": ["2026-08-01-x-card.png"]}
    )
    _, message, _ = _build_message(copy_html=section)
    html = message.get_payload(0).get_payload(1).get_payload(decode=True).decode("utf-8")
    assert html.index("arXiv 精选") < html.index("各平台文案")


def test_copy_section_also_present_in_the_plain_text_part():
    text_section = render_copy_section_text({"x": CopyDraft("x", "", "post body")}, set(), {})
    _, message, _ = _build_message(copy_text=text_section)
    text = message.get_payload(0).get_payload(0).get_payload(decode=True).decode("utf-8")
    assert "各平台文案" in text
    assert "post body" in text


# --- SMTP 超时 ------------------------------------------------------------
#
# 这一组是回归测试。起因是一封 17.82MB 附件（base64 后约 24.4MB）的真实投递
# 失败：SMTPReadTimeoutError。aiosmtplib 的默认超时是 60 秒，而它**每一次读**
# 都用这个值 —— 包括 DATA 命令的响应，那一次要等整封信上传完。
# 向 smtp.163.com 逐级加大 DATA 载荷量到 163 限速而非拒收：
#   13MB → 7.22MB/s   20MB → 0.12MB/s   26MB → 0.19MB/s   35MB → 0.10MB/s
# 所以两道防线都要：预算把载荷压在拐点以下，超时作为兜底余量。


def test_smtp_is_constructed_with_an_explicit_timeout():
    """不传 timeout 就等于接受 60 秒 —— 带图的信在限速下必然超时。"""
    _build_message(attachments=[_attachment(LONG_IMAGE_SLUG, 100)])
    assert "timeout" in _build_message.last_kwargs


def test_smtp_timeout_is_generous_enough_for_a_throttled_upload():
    from app.config import settings

    _build_message(attachments=[_attachment(LONG_IMAGE_SLUG, 100)])
    assert _build_message.last_kwargs["timeout"] == settings.smtp_timeout_seconds
    # 预算内的载荷实测几秒传完；这个值只在服务商开始限速时才起作用。
    assert settings.smtp_timeout_seconds >= 180


def test_ambiguous_data_timeout_is_not_retried(monkeypatch):
    """DATA 可能已被服务商接收；确认响应超时后绝不能重放整封邮件。"""
    import aiosmtplib

    calls = 0

    class _TimeoutSMTP:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def login(self, *args):
            return None

        async def starttls(self, *args, **kwargs):
            return None

        async def sendmail(self, sender, recipient, raw):
            nonlocal calls
            calls += 1
            raise aiosmtplib.errors.SMTPReadTimeoutError("DATA response timed out")

    monkeypatch.setattr(aiosmtplib, "SMTP", _TimeoutSMTP)
    service = _CapturingService()

    with pytest.raises(aiosmtplib.errors.SMTPReadTimeoutError):
        asyncio.run(
            service.send_digest_email(
                date(2026, 8, 1),
                _github(),
                arxiv_items=_arxiv(),
            )
        )

    assert calls == 1


def test_attachment_budget_stays_below_the_measured_throttle_knee():
    """预算是实测的限速拐点，不是服务商公布的上限。

    12MB 原始 ≈ 16.4MB 上线（base64 约 1.37 倍），落在 13MB 全速那一档
    附近；20MB 上线时吞吐掉两个数量级。
    """
    from app.config import settings

    assert settings.attachment_budget_bytes <= 13 * 1024 * 1024


# --- 附件预算 -------------------------------------------------------------


def test_everything_fits_nothing_dropped():
    attachments = [_attachment(LONG_IMAGE_SLUG, 100), _attachment("x-card", 100)]
    result = apply_budget(attachments, budget_bytes=estimated_message_wire_size(attachments))
    assert result.dropped == []
    assert len(result.kept) == 2


def test_wire_size_accounts_for_base64_line_wrapping_and_body_reserve():
    assert base64_wire_size(57) == 1024 + 76 + 2
    assert base64_wire_size(58) == 1024 + 80 + 4
    assert estimated_message_wire_size([]) >= 512 * 1024


def test_long_image_is_preserved_when_it_fits_by_itself():
    """它是主交付物；平台衍生图应先被扣下。"""
    attachments = [_attachment(LONG_IMAGE_SLUG, 900)] + [
        _attachment(slug, 900) for slug in PLATFORM_DROP_ORDER
    ]
    long_only_budget = estimated_message_wire_size([attachments[0]])
    result = apply_budget(attachments, budget_bytes=long_only_budget)
    assert LONG_IMAGE_SLUG in {a.slug for a in result.kept}
    assert LONG_IMAGE_SLUG not in {slug for slug, _ in result.dropped}


def test_drops_follow_the_documented_order():
    attachments = [_attachment(LONG_IMAGE_SLUG, 100)] + [
        _attachment(slug, 100) for slug in PLATFORM_DROP_ORDER
    ]
    kept_target = [attachments[0], *attachments[4:]]
    result = apply_budget(
        attachments,
        budget_bytes=estimated_message_wire_size(kept_target),
    )
    dropped = [slug for slug, _ in result.dropped]
    assert dropped == list(PLATFORM_DROP_ORDER)[:3]


def test_drop_order_covers_every_platform_slug():
    from app.publishers.styles import IMAGE_FRAMES

    assert set(PLATFORM_DROP_ORDER) == set(IMAGE_FRAMES)


def test_instagram_is_dropped_before_the_xiaohongshu_cover():
    assert PLATFORM_DROP_ORDER.index("ig-square") < PLATFORM_DROP_ORDER.index("xhs-cover")


def test_xiaohongshu_pages_drop_from_the_back():
    order = list(PLATFORM_DROP_ORDER)
    assert order.index("xhs-content-3") < order.index("xhs-content-2") < order.index("xhs-content-1")


def test_dropped_attachments_carry_a_reason():
    attachments = [_attachment(LONG_IMAGE_SLUG, 100), _attachment("ig-square", 100)]
    result = apply_budget(
        attachments,
        budget_bytes=estimated_message_wire_size([attachments[0]]),
    )
    assert result.dropped
    assert all(reason for _, reason in result.dropped)


def test_oversized_long_image_is_withheld_to_preserve_the_body(caplog):
    with caplog.at_level("WARNING"):
        result = apply_budget([_attachment(LONG_IMAGE_SLUG, 5000)], budget_bytes=100)
    assert result.kept == []
    assert result.dropped[0][0] == LONG_IMAGE_SLUG
    assert "扣下长图" in caplog.text


def test_filenames_differ_across_days():
    assert attachment_filename("x-card", "2026-08-01") != attachment_filename("x-card", "2026-08-02")


def test_long_image_filename_matches_the_spec_name():
    """spec 要求长图叫 digest-full.png，加日期前缀是为了跨天不覆盖。"""
    name = attachment_filename(LONG_IMAGE_SLUG, "2026-08-01")
    assert name == "2026-08-01-digest-full.png"


# --- 点名缺失的资产 -------------------------------------------------------


def test_withheld_images_are_named_with_their_defect():
    html = render_withheld_html([("xhs-cover", "missing_glyph 未通过")], [])
    assert "xhs-cover" in html
    assert "missing_glyph" in html


def test_dropped_attachments_are_named_too():
    html = render_withheld_html([], [("ig-square", "超出附件预算")])
    assert "ig-square" in html


def test_nothing_withheld_renders_nothing():
    assert render_withheld_html([], []) == ""


def test_failed_platform_copy_is_named_in_the_email():
    html = render_copy_section_html(
        {}, set(), {"x": [CopyIssue("grounding", "编造链接")]}, {}
    )
    assert "X (Twitter)" in html
    assert "编造链接" in html


def test_truncated_copy_is_marked_as_truncated():
    html = render_copy_section_html(
        {"x": CopyDraft("x", "", "body")}, {"x"}, {}, {"x": ["f.png"]}
    )
    assert "已截断" in html


def test_text_only_platform_says_it_has_no_image():
    html = render_copy_section_html({"zhihu": CopyDraft("zhihu", "标题", "正文")}, set(), {}, {})
    assert "无配图" in html


def test_copy_section_escapes_untrusted_copy():
    html = render_copy_section_html(
        {"x": CopyDraft("x", "", "<script>alert(1)</script>")}, set(), {}, {}
    )
    assert "<script>" not in html


def test_empty_copy_result_renders_no_section():
    assert render_copy_section_html({}, set(), {}, {}) == ""
    assert render_copy_section_text({}, set(), {}) == ""


def test_x_thread_is_numbered_in_copy_sections():
    draft = CopyDraft(
        "x", "", "first\n\nsecond", thread=("first", "second")
    )
    text = render_copy_section_text({"x": draft}, set(), {})
    html = render_copy_section_html({"x": draft}, set(), {}, {})
    assert "Thread 1: first" in text
    assert "Thread 2: second" in text
    assert "Thread 1: first" in html
    assert "Thread 2: second" in html


def test_copy_section_inserts_paragraph_breaks_for_one_line_body():
    draft = CopyDraft("reddit", "A hook", "First point. Second point. Final question.")
    text = render_copy_section_text({"reddit": draft}, set(), {})
    assert "First point.\n\nSecond point.\n\nFinal question." in text


# --- 多收件人 ---------------------------------------------------------------


def test_parse_recipients_splits_and_deduplicates():
    from app.services.email_service import parse_recipients

    assert parse_recipients("a@x.com, b@y.com;a@x.com ,") == ["a@x.com", "b@y.com"]
    assert parse_recipients("") == []


def test_one_message_goes_to_every_recipient():
    """整串地址交给 sendmail 会被当成一个地址而被拒收，必须拆成列表。"""
    _, message, count = _build_message(recipient="a@x.com,b@y.com")
    assert count == 1
    assert _build_message.last_recipients == ["a@x.com", "b@y.com"]
    assert message["To"] == "a@x.com, b@y.com"
