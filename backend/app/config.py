"""
配置管理模块 - 从环境变量加载所有配置
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置类"""

    # LLM API (支持 Kimi/DeepSeek/通义等 OpenAI 兼容接口)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(default="", alias="GEMINI_BASE_URL")
    gemini_model: str = Field(default="kimi-k2.5", alias="GEMINI_MODEL")
    gemini_fallback_models: str = Field(default="", alias="GEMINI_FALLBACK_MODELS")
    
    # GitHub API
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    
    # GitHub 访问配置 (用于解决国内服务器无法访问 GitHub 的问题)
    github_proxy: str = Field(default="", alias="GITHUB_PROXY", description="代理地址，如 http://127.0.0.1:7890")
    github_mirror: str = Field(default="", alias="GITHUB_MIRROR", description="镜像地址，如 https://ghproxy.com")
    
    # YouTube API
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    
    # 邮件服务配置（支持 Gmail / 163 / QQ 等）
    smtp_server: str = Field(default="smtp.163.com", alias="SMTP_SERVER")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_use_ssl: bool = Field(default=True, alias="SMTP_USE_SSL")
    
    # 发件人邮箱和授权码
    email_sender: str = Field(default="", alias="EMAIL_SENDER")
    email_password: str = Field(default="", alias="EMAIL_PASSWORD")
    email_recipient: str = Field(default="", alias="EMAIL_RECIPIENT")
    
    # 保留旧字段兼容（向后兼容）
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

    # CORS
    # 逗号分隔，例如："https://senweiv.github.io,http://localhost:3000"
    cors_allow_origins: str = Field(default="", alias="CORS_ALLOW_ORIGINS")
    
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
