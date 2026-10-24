"""
摘要生成服务 - 整合GitHub和YouTube Agent生成每日/每周/每月摘要
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Literal

from app.config import settings
from app.database import get_db
from app.model_roles import role_usage
from app.schemas import DigestRecord, GitHubDigestItem, ArxivDigestItem, YouTubeDigestItem, ExecutionLog
from app.models import DigestRecordModel, ExecutionLogModel
from app.agents.github_agent import github_agent
from app.agents.arxiv_agent import arxiv_agent
from app.agents.youtube_agent import youtube_agent
from app.agents.gemini_analyzer import gemini_analyzer
from app.services.email_service import email_service
from app.services.content_selector import select_research_items
from app.services.digest_assets import AssetBundle, build_assets, cleanup_old_renders

logger = logging.getLogger(__name__)


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
        force: bool = False
    ) -> Tuple[bool, str, Optional[DigestRecord]]:
        """
        生成摘要（支持每日、每周、每月）
        
        Args:
            digest_type: 摘要类型 - daily(每日), weekly(每周), monthly(每月)
            target_date: 目标日期（默认今天）
            send_email: 是否发送邮件
            force: 是否强制重新生成
        
        Returns:
            (是否成功, 消息, 摘要记录)
        """
        if self.is_running:
            return False, "任务正在执行中，请稍后再试", None
        
        self.is_running = True
        start_time = datetime.now()
        target_date = target_date or date.today()
        
        # 根据类型确定记录日期
        if digest_type == "weekly":
            record_date = target_date - timedelta(days=target_date.weekday())  # 本周一
        elif digest_type == "monthly":
            record_date = target_date.replace(day=1)  # 本月1号
        else:
            record_date = target_date
        
        execution_log = ExecutionLog(
            execution_time=start_time,
            status="running",
            github_count=0,
            youtube_count=0
        )
        
        try:
            logger.info(f"开始生成 [{digest_type}] {record_date} 的摘要...")
            # 每次运行独立计数，否则同一进程内多次运行会把上一次的调用算进来
            role_usage.reset()
            
            # 检查是否已有数据（使用组合键：日期+类型）
            async with get_db() as db:
                existing = await DigestRecordModel.get_by_date_and_type(db, record_date, digest_type)
                if existing and not force:
                    logger.info(f"[{digest_type}] {record_date} 已有摘要数据，跳过生成")
                    self.is_running = False
                    return True, f"{digest_type}摘要已存在", existing
            
            # Source collection remains independent; YouTube is not part of research selection.
            github_items, arxiv_items, youtube_items = await self._collect_source_data(digest_type)
            github_items, arxiv_items = select_research_items(
                github_items,
                arxiv_items,
                target_items=settings.target_items,
                max_items=settings.max_items,
            )
            github_items, arxiv_items = await asyncio.gather(
                github_agent.analyze_selected_repos(github_items),
                self._analyze_arxiv_items(arxiv_items),
            )
            
            # 生成总结
            daily_summary = None
            if gemini_analyzer.is_available and (github_items or youtube_items):
                try:
                    period_text = {"daily": "今日", "weekly": "本周", "monthly": "本月"}[digest_type]
                    daily_summary = await gemini_analyzer.generate_period_summary(
                        [item.model_dump() for item in github_items],
                        [item.model_dump() for item in youtube_items],
                        period=period_text
                    )
                except Exception as e:
                    logger.error(f"生成总结失败: {e}")
            
            # 创建摘要记录
            digest_record = DigestRecord(
                digest_date=record_date,
                digest_type=digest_type,
                github_data=github_items,
                arxiv_data=arxiv_items,
                youtube_data=youtube_items,
                email_sent=False
            )
            
            # 只有会走正式投递路径的运行才写入日报记录。临时探针常用
            # send_email=False；如果把它也记成当天记录，晚上的 force=False
            # 调度会误以为日报已经完成，从而跳过真正的邮件。
            if send_email:
                async with get_db() as db:
                    await DigestRecordModel.create_with_type(db, digest_record)
                    logger.info(f"[{digest_type}] 摘要数据已保存到数据库")
            else:
                logger.info(f"[{digest_type}] 临时不发邮件运行，不写入日报记录")

            # 发送邮件
            email_sent = False
            if send_email and email_service.is_configured:
                try:
                    subject_suffix = {
                        "daily": "每日",
                        "weekly": "每周",
                        "monthly": "每月"
                    }[digest_type]

                    # 资产先于发送：一封邮件带走正文、文案和全部通过质检的图，
                    # 不拆信、不为迟到的资产补发第二封。宁可等，不能早发。
                    bundle = await self._build_assets(
                        record_date, github_items, arxiv_items, youtube_items, daily_summary
                    )

                    email_sent = await email_service.send_digest_email(
                        digest_date=record_date,
                        github_items=github_items,
                        arxiv_items=arxiv_items,
                        youtube_items=youtube_items,
                        daily_summary=daily_summary,
                        subject_suffix=subject_suffix,
                        attachments=bundle.attachments,
                        copy_section_html=bundle.copy_section_html,
                        copy_section_text=bundle.copy_section_text,
                        withheld_html=bundle.withheld_html,
                    )

                    if email_sent:
                        digest_record.email_sent = True
                        digest_record.email_sent_at = datetime.now()
                        async with get_db() as db:
                            await DigestRecordModel.update_email_status(db, record_date, digest_type, True)
                        logger.info("邮件发送成功")
                    else:
                        logger.warning("邮件发送失败")

                except Exception as e:
                    logger.error(f"邮件发送异常: {e}")
            
            # 记录执行结果
            duration = (datetime.now() - start_time).total_seconds()
            execution_log.status = "success"
            execution_log.github_count = len(github_items)
            execution_log.youtube_count = len(youtube_items)
            execution_log.duration_seconds = duration
            execution_log.digest_type = digest_type
            
            async with get_db() as db:
                await ExecutionLogModel.create(db, execution_log)
            
            self.last_execution = start_time
            self.last_result = digest_record
            
            message = (
                f"[{digest_type}] 摘要生成完成: GitHub {len(github_items)} 个, "
                f"arXiv {len(arxiv_items)} 个, YouTube {len(youtube_items)} 个"
            )
            if email_sent:
                message += ", 邮件已发送"
            
            logger.info(message)
            return True, message, digest_record
            
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            
            # 记录失败日志
            execution_log.status = "failed"
            execution_log.error_message = str(e)
            execution_log.duration_seconds = (datetime.now() - start_time).total_seconds()
            execution_log.digest_type = digest_type
            
            async with get_db() as db:
                await ExecutionLogModel.create(db, execution_log)
            
            return False, f"生成摘要失败: {str(e)}", None
            
        finally:
            # 成功与失败都要报账：失败的运行同样花了钱，隐藏它会让成本无法归因
            role_usage.log_summary()
            self.is_running = False
    
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
        youtube_items: List[YouTubeDigestItem],
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
                youtube_items,
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
    ) -> tuple[List[GitHubDigestItem], List[ArxivDigestItem], List[YouTubeDigestItem]]:
        """Collect all independent sources concurrently; selection happens afterwards."""
        github_items, arxiv_items, youtube_items = await asyncio.gather(
            self._fetch_github_data(digest_type),
            self._fetch_arxiv_data(),
            self._fetch_youtube_data(),
        )
        return github_items, arxiv_items, youtube_items

    async def _fetch_github_data(
        self,
        digest_type: Literal["daily", "weekly", "monthly"] = "daily"
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
            
            return await github_agent.get_research_repos(time_range=time_range)
        except Exception as e:
            logger.error(f"获取GitHub数据失败: {e}")
            return []

    async def _fetch_arxiv_data(self) -> List[ArxivDigestItem]:
        """获取 arXiv 候选；失败不阻断其他来源。"""
        if not arxiv_agent.is_available:
            return []
        try:
            return await arxiv_agent.fetch()
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

    async def _fetch_youtube_data(self) -> List[YouTubeDigestItem]:
        """获取YouTube数据"""
        if not youtube_agent.is_available:
            logger.warning("YouTube Agent 不可用")
            return []
        
        try:
            return await youtube_agent.get_top_videos()
        except Exception as e:
            logger.error(f"获取YouTube数据失败: {e}")
            raise
    
    async def get_today_digest(self) -> Optional[DigestRecord]:
        """获取今日摘要"""
        async with get_db() as db:
            return await DigestRecordModel.get_by_date_and_type(db, date.today(), "daily")
    
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
