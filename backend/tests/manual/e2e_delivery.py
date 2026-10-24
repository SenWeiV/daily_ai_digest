#!/usr/bin/env python3
"""Collect, analyze, send once, then verify the exact received message.

Run inside the configured container with --send. Uses a temporary database and
the current feature switches; never writes scheduled digest records.
"""

import argparse
import asyncio
import email
import imaplib
import json
import logging
import sys
import tempfile
import time
import uuid
from datetime import date, datetime
from email import policy
from email.utils import getaddresses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import secret_value, settings
from app.database import init_database
from app.logging_config import quiet_sensitive_http_logs
from app.model_roles import role_usage
from app.publishers.styles import enabled_styles
from app.services.digest_service import DigestService, default_target_date
from app.services.email_service import email_service, parse_recipients


def verify_received(message_id, target, recipients, platforms, attachment_names, report_dir):
    sender = email_service.sender_email
    if sender.lower() not in {r.lower() for r in recipients}:
        raise RuntimeError("发送账号不在收件人中，无法用现有 IMAP 凭据核对收件")
    host = settings.smtp_server.replace("smtp.", "imap.", 1)
    box = imaplib.IMAP4_SSL(host, 993, timeout=30)
    try:
        box.login(sender, secret_value(settings.email_password or settings.gmail_app_password))
        if b"ID" in box.capabilities or "ID" in box.capabilities:
            box.xatom("ID", '("name" "digest-e2e" "version" "1.0")')
        if box.select("INBOX", readonly=True)[0] != "OK":
            raise RuntimeError("IMAP 无法只读打开收件箱")
        ids = []
        for attempt in range(12):
            status, data = box.uid("search", None, "HEADER", "Message-ID", f'"{message_id}"')
            if status != "OK":
                raise RuntimeError("IMAP 精确查询失败")
            ids = data[0].split()
            if ids:
                break
            logging.info("等待本次测试邮件入箱 (%s/12)", attempt + 1)
            time.sleep(5)
        if len(ids) != 1:
            raise RuntimeError(f"本次 Message-ID 匹配 {len(ids)} 封，要求恰好一封")
        status, fetched = box.uid("fetch", ids[0], "(BODY.PEEK[])")
        if status != "OK":
            raise RuntimeError("IMAP PEEK 读取失败")
        raw = next(value[1] for value in fetched if isinstance(value, tuple))
        message = email.message_from_bytes(raw, policy=policy.default)
        if str(message["Message-ID"]) != message_id:
            raise RuntimeError("收到邮件的 Message-ID 不匹配")
        if str(target) not in str(message["Subject"]) or "临时测试" not in str(message["Subject"]):
            raise RuntimeError("测试邮件标题或日期不匹配")
        received_to = {address.lower() for _, address in getaddresses(message.get_all("To", []))}
        if received_to != {address.lower() for address in recipients}:
            raise RuntimeError("To 中的收件人集合不匹配")
        if message.get_content_type() != "multipart/mixed":
            raise RuntimeError("邮件外层结构错误")
        html_part, text_part = message.get_body(preferencelist=("html",)), message.get_body(preferencelist=("plain",))
        if not html_part or not text_part:
            raise RuntimeError("HTML 或纯文本正文缺失")
        html, text = html_part.get_content(), text_part.get_content()
        for style in enabled_styles(platforms):
            if style.display_name not in html or style.display_name not in text:
                raise RuntimeError(f"缺少平台文案：{style.key}")
        if "未产出文案的平台" in html:
            raise RuntimeError("实际邮件仍含平台文案失败区块")
        received_attachments = list(message.iter_attachments())
        if sorted(p.get_filename() for p in received_attachments) != sorted(attachment_names):
            raise RuntimeError("实际附件集合与发送前清单不匹配")
        for part in received_attachments:
            payload = part.get_payload(decode=True)
            if not payload or not payload.startswith((b"\x89PNG", b"\xff\xd8\xff")):
                raise RuntimeError("实际图片附件签名异常")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "received.eml").write_bytes(raw)
        (report_dir / "received.html").write_text(html)
        return {"mailbox_received": True, "matching_messages": 1, "wire_bytes": len(raw),
                "html_chars": len(html), "plain_chars": len(text), "attachment_count": len(received_attachments),
                "recipient_count": len(recipients), "subject": str(message["Subject"])}
    finally:
        box.logout()


async def run(target, report_dir):
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    message_id = f"<digest-e2e-{run_id}@{email_service.sender_email.rsplit('@', 1)[-1]}>"
    recipients = parse_recipients(email_service.recipient_email)
    service = DigestService()
    original_build = service._build_assets
    manifest = {}

    async def checked_assets(*args):
        bundle = await original_build(*args)
        if settings.publishers_enabled:
            expected = {style.key for style in enabled_styles(settings.publish_platforms_list)}
            actual = set(bundle.copy_result.accepted) if bundle.copy_result else set()
            if expected != actual:
                raise RuntimeError(f"平台文案未完整通过校验：{sorted(expected - actual)}；SMTP 未调用")
        if bundle.withheld or bundle.dropped:
            raise RuntimeError("本次图片有扣下或超预算结果；SMTP 未调用")
        manifest.update(attachments=[a.filename for a in bundle.attachments],
                        accepted_platforms=sorted(bundle.copy_result.accepted) if bundle.copy_result else [])
        return bundle

    service._build_assets = checked_assets
    with tempfile.TemporaryDirectory(prefix="digest-e2e-") as directory:
        settings.database_path = str(Path(directory) / "digest.db")
        settings.render_output_dir = str(Path(directory) / "renders")
        await init_database()
        ok, message, record = await service.generate_digest(
            target_date=target, send_email=True,
            subject_suffix=f"每日（临时测试 E2E {run_id}）", message_id=message_id,
        )
        report = {"run_id": run_id, "message_id": message_id, "target_date": str(target),
                  "smtp_success": ok, "message": message, "role_calls": role_usage.snapshot(), **manifest}
        report_dir.mkdir(parents=True, exist_ok=True)
        if record:
            (report_dir / "record.json").write_text(record.model_dump_json(indent=2))
            report.update(github_count=len(record.github_data), arxiv_count=len(record.arxiv_data), delivery_status=record.delivery_status)
        (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("SMTP_RESULT", json.dumps(report, ensure_ascii=False), flush=True)
        if not ok:
            return 1
        received = await asyncio.to_thread(verify_received, message_id, target, recipients,
                                          settings.publish_platforms_list if settings.publishers_enabled else [],
                                          manifest.get("attachments", []), report_dir)
        report.update(received)
        (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("E2E_RESULT", json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--send", action="store_true", help="Actually send one email to configured recipients")
    mode.add_argument("--verify-only", action="store_true", help="Recheck a saved run without sending again")
    parser.add_argument("--date", type=date.fromisoformat, default=default_target_date("daily"))
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    quiet_sensitive_http_logs()
    if args.verify_only:
        report = json.loads((args.report_dir / "report.json").read_text())
        if not report.get("smtp_success"):
            raise SystemExit("The saved run did not confirm SMTP acceptance; inspect its report first")
        received = verify_received(report["message_id"], date.fromisoformat(report["target_date"]),
                                   parse_recipients(email_service.recipient_email), report.get("accepted_platforms", []),
                                   report.get("attachments", []), args.report_dir)
        report.update(received)
        (args.report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("E2E_RESULT", json.dumps(report, ensure_ascii=False))
    else:
        raise SystemExit(asyncio.run(run(args.date, args.report_dir)))
