"""
摘要生成服务 - 整合GitHub和YouTube Agent生成每日/每周/每月摘要
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Literal

from app.config import settings
from app.database import get_db
from app.schemas import DigestRecord, GitHubDigestItem, YouTubeDigestItem, ExecutionLog
from app.models import DigestRecordModel, ExecutionLogModel
from app.agents.github_agent import github_agent
from app.agents.youtube_agent import youtube_agent
from app.agents.gemini_analyzer import gemini_analyzer
from app.services.email_service import email_service

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
            
            # 检查是否已有数据（使用组合键：日期+类型）
            async with get_db() as db:
                existing = await DigestRecordModel.get_by_date_and_type(db, record_date, digest_type)
                if existing and not force:
                    logger.info(f"[{digest_type}] {record_date} 已有摘要数据，跳过生成")
                    self.is_running = False
                    return True, f"{digest_type}摘要已存在", existing
            
            # 获取GitHub数据（根据类型使用不同的时间范围）
            github_items = await self._fetch_github_data(digest_type)
            
            # YouTube暂时保持每日模式（YouTube没有weekly/monthly trending）
            youtube_items = await self._fetch_youtube_data()
            
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
                youtube_data=youtube_items,
                email_sent=False
            )
            
            # 保存到数据库
            async with get_db() as db:
                await DigestRecordModel.create_with_type(db, digest_record)
                logger.info(f"[{digest_type}] 摘要数据已保存到数据库")
            
            # 发送邮件
            email_sent = False
            if send_email and email_service.is_configured:
                try:
                    subject_suffix = {
                        "daily": "每日",
                        "weekly": "每周",
                        "monthly": "每月"
                    }[digest_type]
                    
                    email_sent = await email_service.send_digest_email(
                        digest_date=record_date,
                        github_items=github_items,
                        youtube_items=youtube_items,
                        daily_summary=daily_summary,
                        subject_suffix=subject_suffix
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
            
            message = f"[{digest_type}] 摘要生成完成: GitHub {len(github_items)} 个, YouTube {len(youtube_items)} 个"
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
            
            return await github_agent.get_trending_repos(time_range=time_range)
        except Exception as e:
            logger.error(f"获取GitHub数据失败: {e}")
            raise
    
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
