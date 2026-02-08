"""
Pydantic 数据模型定义
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# =====================
# GitHub 相关模型
# =====================

class GitHubDigestItem(BaseModel):
    """GitHub项目摘要项"""
    repo_name: str = Field(..., description="仓库全名 (owner/repo)")
    repo_url: str = Field(..., description="仓库链接")
    stars: int = Field(..., description="Star总数")
    stars_today: int = Field(default=0, description="今日新增Star")
    forks: int = Field(default=0, description="Fork数")
    description: Optional[str] = Field(default=None, description="项目描述")
    main_language: Optional[str] = Field(default=None, description="主要编程语言")
    topics: List[str] = Field(default_factory=list, description="项目标签")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="最后更新时间")
    
    # Gemini 分析结果
    summary: Optional[str] = Field(default=None, description="项目核心总结")
    why_trending: Optional[str] = Field(default=None, description="为什么火")
    key_innovations: List[str] = Field(default_factory=list, description="关键创新点")
    practical_value: Optional[str] = Field(default=None, description="实用价值")
    learning_points: List[str] = Field(default_factory=list, description="学习要点")


# =====================
# YouTube 相关模型
# =====================

class YouTubeDigestItem(BaseModel):
    """YouTube视频摘要项"""
    video_id: str = Field(..., description="视频ID")
    title: str = Field(..., description="视频标题")
    channel: str = Field(..., description="频道名称")
    channel_url: Optional[str] = Field(default=None, description="频道链接")
    video_url: str = Field(..., description="视频链接")
    thumbnail_url: Optional[str] = Field(default=None, description="缩略图链接")
    view_count: int = Field(default=0, description="观看量")
    like_count: int = Field(default=0, description="点赞数")
    comment_count: int = Field(default=0, description="评论数")
    published_at: Optional[str] = Field(default=None, description="发布时间")
    duration: Optional[str] = Field(default=None, description="视频时长")
    
    # Gemini 分析结果
    content_summary: Optional[str] = Field(default=None, description="内容总结")
    key_points: List[str] = Field(default_factory=list, description="核心观点")
    why_popular: Optional[str] = Field(default=None, description="为什么受欢迎")
    practical_takeaways: Optional[str] = Field(default=None, description="实用收获")
    recommended_for: Optional[str] = Field(default=None, description="推荐人群")


# =====================
# 摘要记录模型
# =====================

class DigestRecord(BaseModel):
    """每日摘要记录"""
    id: Optional[int] = None
    digest_date: date = Field(..., description="摘要日期")
    github_data: List[GitHubDigestItem] = Field(default_factory=list)
    youtube_data: List[YouTubeDigestItem] = Field(default_factory=list)
    email_sent: bool = Field(default=False, description="邮件是否已发送")
    email_sent_at: Optional[datetime] = Field(default=None, description="邮件发送时间")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DigestRecordBrief(BaseModel):
    """摘要记录简要信息（用于列表）"""
    id: int
    digest_date: date
    github_count: int = 0
    youtube_count: int = 0
    email_sent: bool = False
    created_at: Optional[datetime] = None


# =====================
# 执行日志模型
# =====================

class ExecutionLog(BaseModel):
    """执行日志"""
    id: Optional[int] = None
    execution_time: datetime = Field(..., description="执行时间")
    status: str = Field(..., description="执行状态: success/failed")
    github_count: int = Field(default=0, description="GitHub结果数")
    youtube_count: int = Field(default=0, description="YouTube结果数")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    duration_seconds: Optional[float] = Field(default=None, description="执行耗时(秒)")
    created_at: Optional[datetime] = None


# =====================
# 配置模型
# =====================

class ConfigItem(BaseModel):
    """配置项"""
    key: str = Field(..., description="配置键")
    value: str = Field(..., description="配置值")
    description: Optional[str] = Field(default=None, description="配置描述")


class ConfigUpdate(BaseModel):
    """配置更新请求"""
    gmail_sender: Optional[str] = None
    gmail_app_password: Optional[str] = None
    digest_recipient: Optional[str] = None
    schedule_hour: Optional[int] = None
    schedule_minute: Optional[int] = None
    timezone: Optional[str] = None
    ai_keywords: Optional[List[str]] = None


# =====================
# API 响应模型
# =====================

class ApiResponse(BaseModel):
    """通用API响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[dict] = None


class StatusResponse(BaseModel):
    """系统状态响应"""
    status: str = "running"
    version: str = "1.0.0"
    last_execution: Optional[datetime] = None
    next_execution: Optional[datetime] = None
    database_connected: bool = True
    config_valid: bool = True
    github_configured: bool = False
    youtube_configured: bool = False
    gemini_configured: bool = False
    email_configured: bool = False


class TriggerRequest(BaseModel):
    """手动触发请求"""
    force: bool = Field(default=False, description="是否强制重新生成（即使今天已有数据）")
    send_email: bool = Field(default=True, description="是否发送邮件")


class TriggerResponse(BaseModel):
    """触发响应"""
    success: bool
    message: str
    task_id: Optional[str] = None
    digest_date: Optional[date] = None