"""
配置管理模块 - 从环境变量加载所有配置
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置类"""
    
    # Gemini API
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    
    # GitHub API
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    
    # YouTube API
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    
    # Gmail SMTP
    gmail_sender: str = Field(default="", alias="GMAIL_SENDER")
    gmail_app_password: str = Field(default="", alias="GMAIL_APP_PASSWORD")
    digest_recipient: str = Field(default="", alias="DIGEST_RECIPIENT")
    
    # 定时任务配置
    schedule_hour: int = Field(default=8, alias="SCHEDULE_HOUR")
    schedule_minute: int = Field(default=0, alias="SCHEDULE_MINUTE")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")
    
    # 应用配置
    debug: bool = Field(default=False, alias="DEBUG")
    database_path: str = Field(default="../data/digest.db", alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # API配置
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    
    # 搜索配置
    github_top_n: int = Field(default=10, description="GitHub Top N 数量")
    youtube_top_n: int = Field(default=10, description="YouTube Top N 数量")
    
    # 搜索关键词 - 聚焦 AI Agent/AGI/LLM 领域
    ai_keywords: list[str] = Field(
        default=[
            "AI agent",
            "LLM agent",
            "AGI",
            "autonomous agent",
            "multi-agent system",
            "agentic AI",
            "AI coding assistant",
            "reasoning AI",
            "GPT-4 GPT-5",
            "Claude Anthropic"
        ],
        description="AI/AGI/AI Agent 相关搜索关键词"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 便捷访问
settings = get_settings()