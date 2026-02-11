"""
API 路由模块 - 所有REST API接口定义
"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query

from app.config import settings
from app.schemas import (
    ApiResponse,
    StatusResponse,
    TriggerRequest,
    TriggerResponse,
    YouTubeAnalyzeRequest,
    DigestRecord,
    DigestRecordBrief,
    ExecutionLog,
    ConfigUpdate
)
from app.services.digest_service import digest_service
from app.services.scheduler import scheduler_service
from app.services.email_service import email_service
from app.agents.github_agent import github_agent
from app.agents.youtube_agent import youtube_agent
from app.agents.gemini_analyzer import gemini_analyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# =====================
# 摘要相关接口
# =====================

@router.get("/digest/today", response_model=Optional[DigestRecord])
async def get_today_digest():
    """获取今日摘要"""
    record = await digest_service.get_today_digest()
    return record


@router.get("/digest/latest", response_model=Optional[DigestRecord])
async def get_latest_digest():
    """获取最新摘要"""
    from app.database import get_db
    from app.models import DigestRecordModel
    
    async with get_db() as db:
        return await DigestRecordModel.get_latest(db)


@router.get("/digest/history")
async def get_digest_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """获取历史摘要列表"""
    records = await digest_service.get_history(limit, offset)
    return {
        "items": records,
        "total": len(records),
        "limit": limit,
        "offset": offset
    }


@router.get("/digest/{digest_date}", response_model=Optional[DigestRecord])
async def get_digest_by_date(digest_date: str):
    """获取指定日期的摘要"""
    try:
        target_date = date.fromisoformat(digest_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD 格式")
    
    record = await digest_service.get_digest_by_date(target_date)
    if not record:
        raise HTTPException(status_code=404, detail=f"未找到 {digest_date} 的摘要数据")
    
    return record


@router.post("/digest/trigger", response_model=TriggerResponse)
async def trigger_digest(
    request: TriggerRequest,
    background_tasks: BackgroundTasks
):
    """手动触发摘要生成"""
    if digest_service.is_running:
        return TriggerResponse(
            success=False,
            message="任务正在执行中，请稍后再试",
            digest_date=date.today()
        )
    
    # 在后台执行
    async def run_digest():
        await scheduler_service.trigger_now(
            send_email=request.send_email,
            force=request.force
        )
    
    background_tasks.add_task(run_digest)
    
    return TriggerResponse(
        success=True,
        message="摘要生成任务已启动，请稍后查看结果",
        task_id=f"digest_{date.today().isoformat()}",
        digest_date=date.today()
    )


# =====================
# 系统状态接口
# =====================

@router.get("/status", response_model=StatusResponse)
async def get_system_status():
    """获取系统状态"""
    from app.database import get_db
    from app.models import ExecutionLogModel
    
    # 获取最后执行时间
    last_execution = None
    async with get_db() as db:
        last_log = await ExecutionLogModel.get_last_successful(db)
        if last_log:
            last_execution = last_log.execution_time
    
    # 获取下次执行时间
    next_execution = scheduler_service.get_next_run_time()
    
    return StatusResponse(
        status="running" if scheduler_service.is_started else "stopped",
        version="1.0.0",
        last_execution=last_execution,
        next_execution=next_execution,
        database_connected=True,
        config_valid=True,
        github_configured=github_agent.is_available,
        youtube_configured=youtube_agent.is_available,
        gemini_configured=gemini_analyzer.is_available,
        email_configured=email_service.is_configured
    )


@router.get("/logs")
async def get_execution_logs(
    limit: int = Query(default=50, ge=1, le=200)
):
    """获取执行日志"""
    logs = await digest_service.get_execution_logs(limit)
    return {
        "items": logs,
        "total": len(logs)
    }


@router.get("/scheduler")
async def get_scheduler_info():
    """获取调度器信息"""
    return scheduler_service.get_job_info()


# =====================
# 配置接口
# =====================

@router.get("/config")
async def get_config():
    """获取当前配置（敏感信息脱敏）"""
    return {
        "schedule_hour": settings.schedule_hour,
        "schedule_minute": settings.schedule_minute,
        "timezone": settings.timezone,
        "github_top_n": settings.github_top_n,
        "youtube_top_n": settings.youtube_top_n,
        "ai_keywords": settings.ai_keywords,
        # 脱敏显示
        "gmail_sender": _mask_email(settings.gmail_sender),
        "digest_recipient": _mask_email(settings.digest_recipient),
        "github_configured": bool(settings.github_token),
        "youtube_configured": bool(settings.youtube_api_key),
        "gemini_configured": bool(settings.gemini_api_key),
        "email_configured": bool(settings.gmail_sender and settings.gmail_app_password)
    }


@router.put("/config")
async def update_config(config: ConfigUpdate):
    """更新配置"""
    updated = {}
    
    # 更新调度时间
    if config.schedule_hour is not None or config.schedule_minute is not None:
        hour = config.schedule_hour if config.schedule_hour is not None else settings.schedule_hour
        minute = config.schedule_minute if config.schedule_minute is not None else settings.schedule_minute
        
        if scheduler_service.is_started:
            scheduler_service.reschedule(hour, minute)
        
        updated["schedule_hour"] = hour
        updated["schedule_minute"] = minute
    
    return ApiResponse(
        success=True,
        message="配置更新成功",
        data=updated
    )


# =====================
# 邮件测试接口
# =====================

@router.post("/email/test")
async def send_test_email(recipient: Optional[str] = None):
    """发送测试邮件"""
    if not email_service.is_configured:
        raise HTTPException(status_code=400, detail="邮件服务未配置")
    
    success = await email_service.send_test_email(recipient)
    
    if success:
        return ApiResponse(success=True, message="测试邮件发送成功")
    else:
        raise HTTPException(status_code=500, detail="测试邮件发送失败")


# =====================
# YouTube 工具接口
# =====================

@router.post("/youtube/analyze")
async def analyze_youtube_video(request: YouTubeAnalyzeRequest):
    """分析指定YouTube视频（URL/ID）"""
    if not youtube_agent.is_available:
        raise HTTPException(status_code=400, detail="YouTube API 未配置")

    if not gemini_analyzer.is_available:
        raise HTTPException(status_code=400, detail="Gemini API 未配置或网络不可达")

    try:
        result = await youtube_agent.analyze_video_by_id(
            video_url=request.video_url,
            video_id=request.video_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"YouTube 单视频分析失败: {e}")
        raise HTTPException(status_code=500, detail="YouTube 视频分析失败")


# =====================
# 工具函数
# =====================

def _mask_email(email: str) -> str:
    """邮箱脱敏"""
    if not email or "@" not in email:
        return ""
    
    parts = email.split("@")
    if len(parts[0]) <= 2:
        return f"{parts[0][0]}***@{parts[1]}"
    return f"{parts[0][:2]}***@{parts[1]}"
