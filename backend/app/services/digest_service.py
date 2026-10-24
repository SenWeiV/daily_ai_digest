"""
摘要生成服务 - 整合 GitHub 与 arXiv 生成每日/每周/每月摘要
"""

import asyncio
import logging

from aiosmtplib import errors as smtp_errors
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Literal
from zoneinfo import ZoneInfo

from app.content_window import ContentWindow, content_window
from app.config import settings
from app.database import get_db
from app.model_roles import role_usage
from app.schemas import DigestRecord, GitHubDigestItem, ArxivDigestItem, ExecutionLog
from app.models import DigestRecordModel, ExecutionLogModel
from app.agents.github_agent import github_agent
from app.agents.arxiv_agent import arxiv_agent
from app.agents.gemini_analyzer import gemini_analyzer
from app.services.email_service import PartialDeliveryError, email_service
from app.services.content_selector import select_research_items
from app.services.digest_assets import AssetBundle, build_assets, cleanup_old_renders

logger = logging.getLogger(__name__)


def local_today() -> date:
    """按业务时区取"今天"。容器跑在 UTC，北京时间早上 8 点前的 date.today() 还是前一天。"""
    return datetime.now(ZoneInfo(settings.timezone)).date()


def default_target_date(digest_type: str, today: Optional[date] = None) -> date:
    """日报整理前一天的内容；周报、月报仍以当天所在的周/月为准。

    日报早上发出，读者要的是"昨天发生了什么"。记录日期必须跟着内容走，
    否则早上 9 点的邮件标着今天的日期，而今天几乎还没有内容。
    """
    today = today or local_today()
    return today - timedelta(days=1) if digest_type == "daily" else today


class DigestService:
    """摘要生成服务 - 支持每日、每周、每月三种模式"""
    
    def __init__(self):
        self.is_running = False
        self.last_execution: Optional[datetime] = None
        self.last_result: Optional[DigestRecord] = None
    
    async def generate_digest(
        self,
        digest_type: Literal["daily", "weekly", "monthly"] = "daily",
        target_date: Optional[date] = None,
        send_email: bool = True,
        force: bool = False,
        send_at: Optional[datetime] = None,
        subject_suffix: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[DigestRecord]]:
        """Generate a period digest; only acknowledged delivery counts as sent.

        A non-forced retry reuses definitively unsent content. Partial or uncertain
        delivery requires mailbox review and an explicit forced resend.
        """
        if digest_type not in {"daily", "weekly", "monthly"}:
            return False, "未知摘要类型", None
        if self.is_running:
            return False, "任务正在执行中，请稍后再试", None

        self.is_running = True
        start_time = datetime.now()
        if target_date is None and digest_type == "daily" and send_at is not None:
            # Preparation may occur before midnight for an after-midnight delivery.
            target_date = send_at.astimezone(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
        target_date = target_date or default_target_date(digest_type)
        record_date = target_date
        if digest_type == "weekly":
            record_date -= timedelta(days=target_date.weekday())
        elif digest_type == "monthly":
            record_date = target_date.replace(day=1)
        execution_log = ExecutionLog(
            execution_time=start_time, status="running", digest_type=digest_type,
        )
        digest_record = None
        try:
            role_usage.reset()
            async with get_db() as db:
                existing = await DigestRecordModel.get_by_date_and_type(db, record_date, digest_type)
            if existing and not force:
                digest_record = existing
                if not send_email or existing.email_sent:
                    return True, f"{digest_type}摘要已存在", existing
                if existing.delivery_status in {"sending", "unknown", "partial"}:
                    raise RuntimeError("已有投递结果待确认；请先核对收件箱，再决定是否强制重发")
                github_items, arxiv_items = existing.github_data, existing.arxiv_data
                daily_summary = None
                logger.info("复用未投递摘要 [%s] %s", digest_type, record_date)
            else:
                window = content_window(digest_type, target_date, settings.timezone)
                logger.info("生成 [%s] %s，内容窗口 [%s, %s)", digest_type, record_date, window.start, window.end)
                github_items, arxiv_items = await self._collect_source_data(digest_type, window)
                github_items, arxiv_items = select_research_items(
                    github_items, arxiv_items,
                    target_items=settings.target_items, max_items=settings.max_items,
                )
                github_items, arxiv_items = await asyncio.gather(
                    github_agent.analyze_selected_repos(github_items),
                    self._analyze_arxiv_items(arxiv_items),
                )
                daily_summary = None
                if gemini_analyzer.is_available and (github_items or arxiv_items):
                    try:
                        daily_summary = await gemini_analyzer.generate_period_summary(
                            [item.model_dump() for item in github_items],
                            [item.model_dump() for item in arxiv_items], period=digest_type,
                        )
                    except Exception as exc:
                        logger.warning("生成总结失败: %s", exc)
                digest_record = DigestRecord(
                    digest_date=record_date, digest_type=digest_type,
                    github_data=github_items, arxiv_data=arxiv_items,
                )
                # Probes must never suppress the scheduled delivery.
                if send_email:
                    async with get_db() as db:
                        await DigestRecordModel.create_with_type(db, digest_record)

            execution_log.github_count = len(github_items)
            if send_email:
                if not email_service.is_configured:
                    raise RuntimeError("邮件服务未配置，摘要尚未投递")
                bundle = await self._build_assets(record_date, github_items, arxiv_items, daily_summary)
                await self._wait_until(send_at)
                await self._set_delivery_status(digest_record, "sending")
                try:
                    sent = await email_service.send_digest_email(
                        digest_date=record_date, github_items=github_items,
                        arxiv_items=arxiv_items, daily_summary=daily_summary,
                        subject_suffix=subject_suffix or {"daily": "每日", "weekly": "每周", "monthly": "每月"}[digest_type],
                        message_id=message_id, attachments=bundle.attachments,
                        copy_section_html=bundle.copy_section_html,
                        copy_section_text=bundle.copy_section_text,
                        withheld_html=bundle.withheld_html,
                    )
                    if not sent:
                        await self._set_delivery_status(digest_record, "failed")
                        raise RuntimeError("SMTP 未接受邮件")
                except PartialDeliveryError:
                    await self._set_delivery_status(digest_record, "partial")
                    raise
                except (smtp_errors.SMTPAuthenticationError, smtp_errors.SMTPRecipientsRefused,
                        smtp_errors.SMTPSenderRefused, smtp_errors.SMTPDataError,
                        smtp_errors.SMTPConnectError, smtp_errors.SMTPConnectTimeoutError,
                        smtp_errors.SMTPHeloError, smtp_errors.SMTPNotSupported):
                    await self._set_delivery_status(digest_record, "failed")
                    raise
                except Exception:
                    if digest_record.delivery_status == "sending":
                        await self._set_delivery_status(digest_record, "unknown")
                    raise
                await self._set_delivery_status(digest_record, "sent")

            execution_log.status = "success"
            execution_log.duration_seconds = (datetime.now() - start_time).total_seconds()
            async with get_db() as db:
                await ExecutionLogModel.create(db, execution_log)
            self.last_execution, self.last_result = start_time, digest_record
            message = f"[{digest_type}] 摘要生成完成: GitHub {len(github_items)} 个, arXiv {len(arxiv_items)} 个"
            if digest_record.email_sent:
                message += ", 邮件已发送"
            return True, message, digest_record
        except Exception as exc:
            logger.error("摘要任务失败: %s", exc)
            execution_log.status = "failed"
            execution_log.error_message = str(exc)
            execution_log.duration_seconds = (datetime.now() - start_time).total_seconds()
            async with get_db() as db:
                await ExecutionLogModel.create(db, execution_log)
            return False, f"摘要任务失败: {exc}", digest_record
        finally:
            role_usage.log_summary()
            self.is_running = False

    @staticmethod
    async def _set_delivery_status(record: DigestRecord, status: str) -> None:
        async with get_db() as db:
            await DigestRecordModel.update_delivery_status(db, record.digest_date, record.digest_type, status)
        record.delivery_status = status
        record.email_sent = status == "sent"
        record.email_sent_at = datetime.now() if record.email_sent else None

    async def generate_daily_digest(
        self,
        target_date: Optional[date] = None,
        send_email: bool = True,
        force: bool = False
    ) -> Tuple[bool, str, Optional[DigestRecord]]:
        """生成每日摘要（向后兼容）"""
        return await self.generate_digest("daily", target_date, send_email, force)
    
    async def generate_weekly_digest(
        self,
        target_date: Optional[date] = None,
        send_email: bool = True,
        force: bool = False
    ) -> Tuple[bool, str, Optional[DigestRecord]]:
        """生成每周摘要"""
        return await self.generate_digest("weekly", target_date, send_email, force)
    
    async def generate_monthly_digest(
        self,
        target_date: Optional[date] = None,
        send_email: bool = True,
        force: bool = False
    ) -> Tuple[bool, str, Optional[DigestRecord]]:
        """生成每月摘要"""
        return await self.generate_digest("monthly", target_date, send_email, force)

    async def _build_assets(
        self,
        record_date: date,
        github_items: List[GitHubDigestItem],
        arxiv_items: List[ArxivDigestItem],
        daily_summary: Optional[str],
    ) -> AssetBundle:
        """产出长图、平台图与平台文案。任何失败都退化成"没有这部分"。

        整体再包一层 try 是刻意的：build_assets 内部已经逐环节兜底，这一层挡的是
        它自己的编程错误。三个外部系统之外还有我们自己的 bug，而一个 bug 也不
        应该让今天的摘要邮件发不出去。
        """
        try:
            digest_html = email_service._generate_html_template(  # noqa: SLF001 - 同包内模板
                record_date,
                github_items,
                arxiv_items=arxiv_items,
                daily_summary=daily_summary,
            )
            items = [item.model_dump() for item in github_items] + [
                item.model_dump() for item in arxiv_items
            ]
            digest_label = record_date.strftime("%Y-%m-%d")
            bundle = await build_assets(
                digest_html=digest_html, items=items, digest_label=digest_label
            )
            # 清理放在产出之后、发送之前，并以本次目录名为豁免条件：
            # 先清理会有删掉正在写入的目录的风险。
            cleanup_old_renders(digest_label)
            return bundle
        except Exception as exc:  # noqa: BLE001 - 资产失败绝不阻断邮件
            logger.error(f"资产产出失败，本次邮件按现状发送: {exc}", exc_info=True)
            return AssetBundle()

    async def _collect_source_data(
        self,
        digest_type: Literal["daily", "weekly", "monthly"],
        window: Optional[ContentWindow] = None,
    ) -> tuple[List[GitHubDigestItem], List[ArxivDigestItem]]:
        """Collect all independent sources concurrently; selection happens afterwards."""
        github_items, arxiv_items = await asyncio.gather(
            self._fetch_github_data(digest_type, window) if window else self._fetch_github_data(digest_type),
            self._fetch_arxiv_data(window) if window else self._fetch_arxiv_data(),
        )
        return github_items, arxiv_items

    @staticmethod
    async def _wait_until(send_at: Optional[datetime]) -> None:
        """整理得比计划快时，等到约定时刻再发；已经过点就立即发。

        只等不跳过：整理超时晚于约定时刻时，晚到的邮件仍然比没有邮件好。
        """
        if send_at is None:
            return
        now = datetime.now(send_at.tzinfo) if send_at.tzinfo else datetime.now()
        delay = (send_at - now).total_seconds()
        if delay > 0:
            logger.info(f"摘要已就绪，等待 {delay:.0f} 秒到 {send_at:%H:%M} 再发送")
            await asyncio.sleep(delay)

    async def _fetch_github_data(
        self,
        digest_type: Literal["daily", "weekly", "monthly"] = "daily",
        window: Optional[ContentWindow] = None,
    ) -> List[GitHubDigestItem]:
        """获取GitHub数据（根据类型使用不同时间范围）"""
        if not github_agent.is_available:
            logger.warning("GitHub Agent 不可用")
            return []
        
        try:
            # 将 digest_type 映射到 GitHub trending 的 since 参数
            time_range = {
                "daily": "daily",
                "weekly": "weekly", 
                "monthly": "monthly"
            }.get(digest_type, "daily")
            
            return await github_agent.get_research_repos(time_range=time_range, window=window)
        except Exception as e:
            logger.error(f"获取GitHub数据失败: {e}")
            return []

    async def _fetch_arxiv_data(self, window: Optional[ContentWindow] = None) -> List[ArxivDigestItem]:
        """获取 arXiv 候选；失败不阻断其他来源。"""
        if not arxiv_agent.is_available:
            return []
        try:
            return await arxiv_agent.fetch(window=window)
        except Exception as e:
            logger.error(f"获取 arXiv 数据失败: {e}")
            return []

    async def _analyze_arxiv_items(self, items: List[ArxivDigestItem]) -> List[ArxivDigestItem]:
        if not gemini_analyzer.is_available:
            return items

        semaphore = asyncio.Semaphore(3)

        async def analyze(item: ArxivDigestItem):
            async with semaphore:
                return await gemini_analyzer.analyze_arxiv_paper(
                    item.title,
                    item.abstract,
                    item.authors,
                    item.categories,
                )

        analyses = await asyncio.gather(
            *(analyze(item) for item in items),
            return_exceptions=True,
        )
        for item, analysis in zip(items, analyses):
            if isinstance(analysis, Exception):
                logger.warning("arXiv analysis failed [%s]: %s", item.arxiv_id, analysis)
                continue
            for field in ("summary", "problem", "method", "evaluation", "results", "limitations"):
                value = analysis.get(field)
                if value:
                    setattr(item, field, value)
        return items

    async def get_today_digest(self) -> Optional[DigestRecord]:
        """获取最新一期日报。日报记在前一天名下，所以今天没有记录时退回昨天。"""
        async with get_db() as db:
            for day in (local_today(), default_target_date("daily")):
                record = await DigestRecordModel.get_by_date_and_type(db, day, "daily")
                if record:
                    return record
            return None
    
    async def get_digest_by_date(self, target_date: date, digest_type: str = "daily") -> Optional[DigestRecord]:
        """获取指定日期和类型的摘要"""
        async with get_db() as db:
            return await DigestRecordModel.get_by_date_and_type(db, target_date, digest_type)
    
    async def get_history(self, limit: int = 30, offset: int = 0, digest_type: str = "daily"):
        """获取历史摘要列表"""
        async with get_db() as db:
            return await DigestRecordModel.get_history_by_type(db, digest_type, limit, offset)
    
    async def get_execution_logs(self, limit: int = 50):
        """获取执行日志"""
        async with get_db() as db:
            return await ExecutionLogModel.get_recent(db, limit)


# 全局实例
digest_service = DigestService()
