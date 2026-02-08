"""
FastAPI 主应用入口
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_database
from app.api.routes import router
from app.services.scheduler import scheduler_service

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("=" * 60)
    logger.info("Daily AI Digest 服务启动中...")
    logger.info("=" * 60)
    
    # 初始化数据库
    try:
        await init_database()
        logger.info("✅ 数据库初始化完成")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
    
    # 启动定时任务调度器
    try:
        scheduler_service.start()
        logger.info("✅ 定时任务调度器启动完成")
    except Exception as e:
        logger.error(f"❌ 调度器启动失败: {e}")
    
    # 检查配置状态
    _check_config()
    
    logger.info("=" * 60)
    logger.info("服务启动完成！")
    logger.info(f"API地址: http://{settings.api_host}:{settings.api_port}")
    logger.info("=" * 60)
    
    yield
    
    # 关闭时
    logger.info("服务正在关闭...")
    scheduler_service.stop()
    logger.info("服务已关闭")


def _check_config():
    """检查配置状态"""
    issues = []
    
    if not settings.gemini_api_key:
        issues.append("⚠️  Gemini API Key 未配置")
    else:
        logger.info("✅ Gemini API Key 已配置")
    
    if not settings.github_token:
        issues.append("⚠️  GitHub Token 未配置")
    else:
        logger.info("✅ GitHub Token 已配置")
    
    if not settings.youtube_api_key:
        issues.append("⚠️  YouTube API Key 未配置")
    else:
        logger.info("✅ YouTube API Key 已配置")
    
    if not settings.gmail_sender or not settings.gmail_app_password:
        issues.append("⚠️  Gmail 邮件服务未配置")
    else:
        logger.info("✅ Gmail 邮件服务已配置")
    
    if issues:
        logger.warning("-" * 40)
        for issue in issues:
            logger.warning(issue)
        logger.warning("请参考 .env.example 配置相应的 API 密钥")
        logger.warning("-" * 40)


# 创建 FastAPI 应用
app = FastAPI(
    title="Daily AI Digest",
    description="每日AI情报摘要系统 - 自动从GitHub和YouTube获取AI领域热点内容",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(router)


# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "daily-ai-digest"}


# 根路径
@app.get("/")
async def root():
    """根路径 - 返回服务信息"""
    return {
        "service": "Daily AI Digest",
        "version": "1.0.0",
        "description": "每日AI情报摘要系统",
        "docs": "/docs",
        "api": "/api"
    }