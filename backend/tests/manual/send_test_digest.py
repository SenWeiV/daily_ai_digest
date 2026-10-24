#!/usr/bin/env python3
"""发一封临时的端到端测试邮件：读库里最新的摘要，产出资产，投递。

为什么是独立脚本而不是打 /api/digest/trigger：
触发接口会把渲染开关的状态套在**常驻服务进程**上，而那个进程正是每天 20:00
定时发信的执行者。渲染是这次新加的路径，第一次真跑就让它跑在定时任务的进程里，
等于把"临时测一封"和"每天那封"绑成同一个风险。所以这里另起一个进程，用
`docker exec -e RENDER_ENABLED=true` 只给这一次开渲染，常驻服务的配置一个字
不改 —— 定时任务照旧、开关照旧关闭。

也不重新采集：数据用**库里已经落库的最新一份**。两个原因：
- 重采会让"邮件里的内容"和"库里的内容"不是同一批，那样这封测试信就证明不了
  线上那封会长成什么样。
- 重采还会为今天写一条记录，而今晚 20:00 的定时任务正要写同一条 —— 让一次
  临时测试去和定时任务抢同一行，是把风险引回定时路径。

取"最新一份"而不是"今天那份"：跨过零点后今天还没有记录，硬取 today 会直接
退出。日期可以用第一个参数覆盖（`python send_test_digest.py 2026-08-01`）。
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime

sys.path.insert(0, "/app/backend")

from app.config import settings
from app.database import get_db
from app.logging_config import quiet_sensitive_http_logs
from app.models import DigestRecordModel
from app.publishers.styles import enabled_styles
from app.services.attachment_budget import LONG_IMAGE_SLUG
from app.services.digest_service import digest_service
from app.services.email_service import email_service

# 独立进程不继承服务的日志配置，缺了这一行质检循环的每一次尝试都无处可看 ——
# 而"每张图试了几次、报了什么缺陷"正是这条链路唯一的过程证据：产出物只显示
# 最后一次的结果，看不出中间是一次过还是修正了两轮。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
# 独立脚本不导入 app.main，所以必须在这里也应用一次。否则 httpx 会把
# Seedream 的 24 小时签名下载 URL 原样写进临时日志。
quiet_sensitive_http_logs()


async def _latest_daily_date(db) -> date | None:
    """库里最新一条 daily 摘要的日期。

    走原生 SQL 是因为这个项目的数据层就是 aiosqlite + 手写 SQL，没有 ORM。
    digest_date 在表里存的是 ISO 字符串，字典序与日期序一致，所以可以直接排序。
    """
    async with db.execute(
        "SELECT digest_date FROM digest_records WHERE digest_type = ? "
        "ORDER BY digest_date DESC LIMIT 1",
        ("daily",),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return date.fromisoformat(row[0])


async def main() -> int:
    requested = (
        datetime.strptime(sys.argv[1], "%Y-%m-%d").date() if len(sys.argv) > 1 else None
    )
    async with get_db() as db:
        target = requested if requested is not None else await _latest_daily_date(db)
        if target is None:
            print("✗ 库里没有任何 daily 摘要，先跑一次采集")
            return 1
        record = await DigestRecordModel.get_by_date(db, target, "daily")
    if record is None:
        print(f"✗ 库里没有 {target} 的 daily 摘要")
        return 1
    if target != date.today():
        print(f"! 今天（{date.today()}）还没有摘要，用库里最新的 {target}")

    github_items = record.github_data or []
    arxiv_items = record.arxiv_data or []
    youtube_items = record.youtube_data or []
    print(f"读到 {target} 的摘要：GitHub {len(github_items)} 条 / "
          f"arXiv {len(arxiv_items)} 条 / YouTube {len(youtube_items)} 条")
    print(f"渲染={settings.render_enabled} 质检={settings.visual_qa_enabled} "
          f"生图={settings.image_gen_enabled}")
    print(f"附件预算={settings.attachment_budget_bytes / 1048576:.1f}MB "
          f"SMTP超时={settings.smtp_timeout_seconds:.0f}s")

    if not email_service.is_configured:
        print("✗ SMTP 未配置")
        return 1

    summary = None
    if github_items or youtube_items:
        from app.agents.gemini_analyzer import gemini_analyzer
        if gemini_analyzer.is_available:
            try:
                summary = await gemini_analyzer.generate_period_summary(
                    [i.model_dump() for i in github_items],
                    [i.model_dump() for i in youtube_items],
                    period="今日",
                )
                print(f"总结已生成（{len(summary or '')} 字）")
            except Exception as exc:  # noqa: BLE001
                print(f"! 总结生成失败，邮件照发：{exc}")

    bundle = await digest_service._build_assets(  # noqa: SLF001
        target, github_items, arxiv_items, youtube_items, summary
    )
    total = sum(len(a.content) for a in bundle.attachments)
    print(f"附件 {len(bundle.attachments)} 个"
          + (f"（{total / 1048576:.2f}MB，base64 上线约 {total * 1.37 / 1048576:.2f}MB）"
             if bundle.attachments else ""))
    for att in bundle.attachments:
        print(f"    {att.filename} {len(att.content) / 1048576:.2f}MB")
    for slug, why in bundle.withheld:
        print(f"  扣下 {slug}：{why}")
    for slug, why in bundle.dropped:
        print(f"  超预算丢弃 {slug}：{why}")
    for note in bundle.notes:
        print(f"  省略：{note}")

    # 临时验收模式在 SMTP DATA 之前拦截不完整结果，避免把一封已知不合格的
    # 测试信送进收件箱。常驻日报不走这个分支，仍按正式策略发送并点名失败。
    if os.getenv("E2E_REQUIRE_COMPLETE", "").lower() == "true":
        expected_slugs = {LONG_IMAGE_SLUG}
        for style in enabled_styles(settings.publish_platforms_list):
            expected_slugs.update(style.image_slugs)
        actual_slugs = {attachment.slug for attachment in bundle.attachments}
        problems = []
        if bundle.withheld:
            problems.append("扣下=" + ",".join(slug for slug, _ in bundle.withheld))
        if bundle.dropped:
            problems.append("超预算丢弃=" + ",".join(slug for slug, _ in bundle.dropped))
        if bundle.copy_result and bundle.copy_result.failed:
            problems.append("文案失败=" + ",".join(sorted(bundle.copy_result.failed)))
        missing = sorted(expected_slugs - actual_slugs)
        if missing:
            problems.append("缺少附件=" + ",".join(missing))
        if problems:
            print("✗ 完整性验收失败，SMTP 未调用：" + "；".join(problems))
            return 2

    import time

    started = time.monotonic()
    sent = await email_service.send_digest_email(
        digest_date=target,
        github_items=github_items,
        arxiv_items=arxiv_items,
        youtube_items=youtube_items,
        daily_summary=summary,
        subject_suffix=f"每日（临时测试 {datetime.now().strftime('%Y%m%d-%H%M%S')}）",
        attachments=bundle.attachments,
        copy_section_html=bundle.copy_section_html,
        copy_section_text=bundle.copy_section_text,
        withheld_html=bundle.withheld_html,
    )
    elapsed = time.monotonic() - started
    print(f"投递耗时 {elapsed:.1f}s"
          + (f"（{total / 1048576 / elapsed:.2f}MB/s）" if sent and elapsed > 0 else ""))
    print("✓ 邮件已投递" if sent else "✗ 邮件投递失败")
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
