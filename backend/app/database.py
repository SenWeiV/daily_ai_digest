"""
数据库管理模块 - SQLite异步连接与初始化
"""

import aiosqlite
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import settings


# 确保数据目录存在
def ensure_data_dir():
    """确保数据目录存在"""
    db_path = Path(settings.database_path)
    db_dir = db_path.parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)


# 数据库初始化SQL
INIT_SQL = """
-- 每日摘要记录表
CREATE TABLE IF NOT EXISTS digest_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_date DATE NOT NULL,
    digest_type TEXT DEFAULT 'daily' NOT NULL,
    github_data TEXT,
    youtube_data TEXT,
    email_sent INTEGER DEFAULT 0,
    email_sent_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(digest_date, digest_type)
);

-- 配置表
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 执行日志表
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_time TEXT NOT NULL,
    status TEXT NOT NULL,
    github_count INTEGER DEFAULT 0,
    youtube_count INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds REAL,
    digest_type TEXT DEFAULT 'daily',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_digest_date ON digest_records(digest_date);
CREATE INDEX IF NOT EXISTS idx_execution_time ON execution_logs(execution_time);
"""


async def init_database():
    """初始化数据库，创建所有必要的表"""
    ensure_data_dir()
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(INIT_SQL)
        await db.commit()
        
        # 数据库迁移：检查并添加缺失的列
        await _run_migrations(db)
        
        print(f"数据库初始化完成: {settings.database_path}")


async def _run_migrations(db: aiosqlite.Connection):
    """运行数据库迁移"""
    # 检查 execution_logs 表是否有 digest_type 列
    cursor = await db.execute("PRAGMA table_info(execution_logs)")
    columns = [row[1] for row in await cursor.fetchall()]
    
    if 'digest_type' not in columns:
        await db.execute("ALTER TABLE execution_logs ADD COLUMN digest_type TEXT DEFAULT 'daily'")
        await db.commit()
        print("数据库迁移: 添加 execution_logs.digest_type 列")
    
    # 检查 digest_records 表是否有 digest_type 列
    cursor = await db.execute("PRAGMA table_info(digest_records)")
    columns = [row[1] for row in await cursor.fetchall()]
    
    if 'digest_type' not in columns:
        await db.execute("ALTER TABLE digest_records ADD COLUMN digest_type TEXT DEFAULT 'daily'")
        await db.commit()
        print("数据库迁移: 添加 digest_records.digest_type 列")


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """获取数据库连接的上下文管理器"""
    ensure_data_dir()
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def get_db_connection() -> aiosqlite.Connection:
    """获取数据库连接（用于依赖注入）"""
    ensure_data_dir()
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    return db