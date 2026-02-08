#!/usr/bin/env python3
"""
Daily AI Digest 启动脚本
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在Python路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"警告: 未找到 .env 文件，请复制 .env.example 并配置")
    print(f"  cp {project_root}/.env.example {project_root}/.env")

import uvicorn
from app.config import settings


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║           🤖 Daily AI Digest                             ║
    ║           每日AI情报摘要系统                              ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()