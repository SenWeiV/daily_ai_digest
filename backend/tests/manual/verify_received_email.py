"""从收件箱里把刚发的那封信取回来，验证收到的字节。

为什么要这一步：发送侧返回 True 只证明 SMTP 接受了信，不证明收件人看到的
东西是对的。MIME 结构错位（附件挂到 alternative 上）表现为**正文消失**，
而发送侧完全正常。这类缺陷只有从收件侧才能发现。

用 IMAP 只读取信，不删不改。
"""

import email
import imaplib
import os
import re
import sys
from email.header import decode_header
from email.utils import parsedate_to_datetime


def _decoded(value: str) -> str:
    parts = decode_header(value or "")
    return "".join(
        piece.decode(charset or "utf-8", errors="replace") if isinstance(piece, bytes) else piece
        for piece, charset in parts
    )


USER = os.environ.get("EMAIL_SENDER") or ""
PASSWORD = os.environ.get("EMAIL_PASSWORD") or ""
HOST = (os.environ.get("SMTP_SERVER") or "smtp.163.com").replace("smtp.", "imap.")
if not USER or not PASSWORD:
    print("✗ 容器内没有 EMAIL_SENDER/EMAIL_PASSWORD")
    sys.exit(1)

box = imaplib.IMAP4_SSL(HOST, 993)
try:
    box.login(USER, PASSWORD)
    # 163 要求客户端声明身份，否则 SELECT 报 "Unsafe Login"
    box.xatom(
        "ID",
        '("name" "digest-verify" "version" "1.0" "vendor" "local" "support-email" "%s")' % USER,
    )
    box.select("INBOX", readonly=True)
    status, data = box.search(None, "ALL")
    ids = data[0].split()
    if not ids:
        print("✗ 收件箱是空的")
        sys.exit(1)

    # 先只取信头，避免为了找目标把最近 25 封（每封约 10MB）的正文全部下载一遍。
    matching_headers = []
    for msg_id in reversed(ids[-25:]):
        status, fetched = box.fetch(
            msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])"
        )
        header = email.message_from_bytes(fetched[0][1])
        subject = _decoded(header.get("Subject", ""))
        if "临时测试" in subject:
            matching_headers.append((msg_id, subject, header.get("Date")))

    if not matching_headers:
        print("✗ 最近 25 封里没有找到标题含'临时测试'的信")
        sys.exit(1)

    msg_id, expected_subject, newest_date = matching_headers[0]
    status, fetched = box.fetch(msg_id, "(RFC822)")
    raw = fetched[0][1]
    message = email.message_from_bytes(raw)
    subject = _decoded(message.get("Subject", ""))
    exact_matches = [item for item in matching_headers if item[1] == expected_subject]
    try:
        newest_at = parsedate_to_datetime(newest_date)
        retry_window_matches = [
            item
            for item in exact_matches
            if item[2]
            and abs((parsedate_to_datetime(item[2]) - newest_at).total_seconds()) <= 300
        ]
    except (TypeError, ValueError, OverflowError):
        # 日期不可解析时采取保守策略：所有同标题邮件都视为可能重试。
        retry_window_matches = exact_matches
    print(
        f"同标题临时邮件共 {len(exact_matches)} 封；"
        f"最新投递前后 5 分钟内 {len(retry_window_matches)} 封（应为 1）"
    )
    print(f"信件 #{msg_id.decode()}  体积 {len(raw) / 1048576:.2f}MB")
    print(f"标题：{subject}")
    print(f"日期：{message.get('Date')}")
    print(f"外层类型：{message.get_content_type()}")

    parts = message.get_payload()
    print(f"顶层部件 {len(parts)} 个：")
    body_html = body_text = ""
    attachments = []
    for index, part in enumerate(parts):
        ctype = part.get_content_type()
        if ctype == "multipart/alternative":
            inner = [p.get_content_type() for p in part.get_payload()]
            print(f"  [{index}] {ctype} → {inner}")
            for sub in part.get_payload():
                decoded = sub.get_payload(decode=True).decode("utf-8", errors="replace")
                if sub.get_content_type() == "text/html":
                    body_html = decoded
                else:
                    body_text = decoded
        else:
            payload = part.get_payload(decode=True) or b""
            name = part.get_filename() or "(无名)"
            attachments.append((name, ctype, len(payload), payload[:4]))
            print(f"  [{index}] {ctype:12s} {name:34s} {len(payload) / 1048576:5.2f}MB")

    print()
    ok = True

    if len(retry_window_matches) != 1:
        print("✗ SMTP 重试窗口内同标题邮件不止一封，可能发生重复投递")
        ok = False
    if message.get_content_type() != "multipart/mixed":
        print("✗ 外层不是 multipart/mixed，附件可能顶掉正文")
        ok = False
    if not body_html:
        print("✗ 没有 HTML 正文 —— 这正是'图片把正文顶掉'的表现")
        ok = False
    else:
        print(f"✓ HTML 正文 {len(body_html)} 字符")
        for marker in (
            "GitHub Top",
            "各平台文案",
            "小红书",
            "微信公众号",
            "X (Twitter)",
            "Instagram",
            "知乎",
            "Reddit",
        ):
            if marker in body_html:
                print(f"  ✓ 含「{marker}」")
            else:
                print(f"  ✗ 缺「{marker}」")
                ok = False
        if "未产出文案的平台" in body_html:
            print("  ✗ 仍有平台文案失败区块")
            ok = False
        else:
            print("  ✓ 六平台均无失败区块")
    if not body_text:
        print("✗ 没有纯文本备份正文")
        ok = False
    else:
        print(f"✓ 纯文本正文 {len(body_text)} 字符")
        omission = re.compile(r"(?:\.{2,}|…+|。{2,})")
        if omission.search(body_text):
            print("✗ 纯文本正文仍包含省略标记")
            ok = False
        else:
            print("✓ 纯文本正文无省略标记")
        if "各平台文案" in body_text and "\n\n" in body_text:
            print("✓ 平台复制区块包含段落换行")
        else:
            print("✗ 平台复制区块缺少段落换行")
            ok = False

    print()
    print(f"附件 {len(attachments)} 个，合计 "
          f"{sum(size for _, _, size, _ in attachments) / 1048576:.2f}MB")
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", subject)
    if date_match:
        label = date_match.group(0)
        expected_names = {
            f"{label}-digest-full.png",
            f"{label}-xhs-cover.jpg",
            f"{label}-xhs-content-1.jpg",
            f"{label}-xhs-content-2.jpg",
            f"{label}-xhs-content-3.jpg",
            f"{label}-x-card.jpg",
            f"{label}-ig-square.jpg",
        }
        actual_names = {name for name, _, _, _ in attachments}
        dynamic_content = {
            name for name in actual_names
            if re.fullmatch(rf"{re.escape(label)}-xhs-content-\d+\.jpg", name)
        }
        content_numbers = sorted(
            int(re.search(r"xhs-content-(\d+)", name).group(1))
            for name in dynamic_content
        )
        expected_with_dynamic = expected_names | dynamic_content
        missing = expected_names - actual_names
        extra = actual_names - expected_with_dynamic
        contiguous = content_numbers == list(range(1, max(content_numbers, default=0) + 1))
        if not missing and not extra and contiguous:
            print(f"✓ 小红书动态内容附件 1-{max(content_numbers, default=0)} 全部到达，无多余附件")
        else:
            print(f"✗ 附件集合不符 | 缺={sorted(missing)} | 多={sorted(extra)} | 编号连续={contiguous}")
            ok = False
    else:
        print("✗ 标题里找不到摘要日期，无法核对附件集合")
        ok = False

    # 魔数校验：认扩展名不算，要看字节。JPEG 起始 FFD8FF，PNG 起始 89504E47。
    MAGIC = {"png": b"\x89PNG", "jpg": b"\xff\xd8\xff"}
    for name, ctype, size, head in attachments:
        suffix = name.rsplit(".", 1)[-1].lower()
        expected = MAGIC.get(suffix)
        if expected is None:
            print(f"  ? {name} 未知后缀")
            continue
        if head[: len(expected)] == expected[: len(head)]:
            print(f"  ✓ {name:34s} {ctype:12s} 魔数与后缀一致")
        else:
            print(f"  ✗ {name:34s} 魔数 {head.hex()} 与后缀 .{suffix} 不符")
            ok = False

    print()
    print("✓ 收件侧验证通过" if ok else "✗ 收件侧发现问题")
    sys.exit(0 if ok else 1)
finally:
    try:
        box.logout()
    except Exception:  # noqa: BLE001
        pass
