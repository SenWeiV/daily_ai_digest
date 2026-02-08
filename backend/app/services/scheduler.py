"""
定时任务调度服务 - 使用APScheduler实现每日定时执行
"""

import logging
from datetime import datetime
from typing import Optional
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import settings
from app.services.digest_service import digest_service

logger = logging.getLogger(__name__)


class SchedulerService:
    """定时任务调度服务"""
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.job_id = "daily_digest_job"
        self.is_started = False
    
    def _job_listener(self, event):
        """任务执行事件监听器"""
        if event.exception:
            logger.error(f"定时任务执行失败: {event.exception}")
        else:
            logger.info(f"定时任务执行完成: {event.job_id}")
    
    async def _execute_daily_digest(self):
        """执行每日摘要生成任务"""
        logger.info("=" * 50)
        logger.info("定时任务触发：开始生成每日AI摘要")
        logger.info("=" * 50)
        
        try:
            success, message, record = await digest_service.generate_daily_digest(
                send_email=True,
                force=False
            )
            
            if success:
                logger.info(f"每日摘要生成成功: {message}")
            else:
                logger.error(f"每日摘要生成失败: {message}")
                
        except Exception as e:
            logger.error(f"定时任务执行异常: {e}")
    
    def start(self):
        """启动调度器"""
        if self.is_started:
            logger.warning("调度器已在运行中")
            return
        
        try:
            # 创建调度器
            self.scheduler = AsyncIOScheduler(
                timezone=settings.timezone,
                job_defaults={
                    'coalesce': True,  # 合并错过的任务
                    'max_instances': 1,  # 最多同时运行1个实例
                    'misfire_grace_time': 3600  # 1小时内的错过任务仍会执行
                }
            )
            
            # 添加事件监听器
            self.scheduler.add_listener(
                self._job_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
            )
            
            # 添加每日定时任务
            self.scheduler.add_job(
                self._execute_daily_digest,
                trigger=CronTrigger(
                    hour=settings.schedule_hour,
                    minute=settings.schedule_minute,
                    timezone=settings.timezone
                ),
                id=self.job_id,
                name="Daily AI Digest Generator",
                replace_existing=True
            )
            
            # 启动调度器
            self.scheduler.start()
            self.is_started = True
            
            next_run = self.get_next_run_time()
            logger.info(f"调度器启动成功")
            logger.info(f"每日执行时间: {settings.schedule_hour:02d}:{settings.schedule_minute:02d} ({settings.timezone})")
            logger.info(f"下次执行时间: {next_run}")
            
        except Exception as e:
            logger.error(f"调度器启动失败: {e}")
            raise
    
    def stop(self):
        """停止调度器"""
        if self.scheduler and self.is_started:
            self.scheduler.shutdown(wait=False)
            self.is_started = False
            logger.info("调度器已停止")
    
    def get_next_run_time(self) -> Optional[datetime]:
        """获取下次执行时间"""
        if not self.scheduler or not self.is_started:
            return None
        
        job = self.scheduler.get_job(self.job_id)
        if job:
            return job.next_run_time
        return None
    
    def get_job_info(self) -> dict:
        """获取任务信息"""
        if not self.scheduler or not self.is_started:
            return {
                "status": "stopped",
                "next_run": None
            }
        
        job = self.scheduler.get_job(self.job_id)
        if job:
            return {
                "status": "running",
                "job_id": job.id,
                "job_name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
        
        return {
            "status": "no_job",
            "next_run": None
        }
    
    async def trigger_now(self, send_email: bool = True, force: bool = False):
        """
        立即触发执行
        
        Args:
            send_email: 是否发送邮件
            force: 是否强制重新生成
        
        Returns:
            执行结果
        """
        logger.info("手动触发每日摘要生成任务")
        return await digest_service.generate_daily_digest(
            send_email=send_email,
            force=force
        )
    
    def reschedule(self, hour: int, minute: int):
        """
        重新设置执行时间
        
        Args:
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
        """
        if not self.scheduler or not self.is_started:
            logger.warning("调度器未启动，无法重新调度")
            return
        
        try:
            self.scheduler.reschedule_job(
                self.job_id,
                trigger=CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=settings.timezone
                )
            )
            
            next_run = self.get_next_run_time()
            logger.info(f"任务重新调度成功: {hour:02d}:{minute:02d}")
            logger.info(f"下次执行时间: {next_run}")
            
        except Exception as e:
            logger.error(f"重新调度失败: {e}")
            raise


# 全局实例
scheduler_service = SchedulerService()