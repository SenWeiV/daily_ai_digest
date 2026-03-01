"""
数据库操作模型 - CRUD 操作封装
"""

import json
from datetime import datetime, date
from typing import Optional, List

import aiosqlite

from app.schemas import (
    DigestRecord, 
    DigestRecordBrief,
    GitHubDigestItem, 
    YouTubeDigestItem,
    ExecutionLog,
    ConfigItem
)


class DigestRecordModel:
    """摘要记录数据库操作"""
    
    @staticmethod
    async def create_with_type(db: aiosqlite.Connection, record: DigestRecord) -> int:
        """创建新的摘要记录（支持 digest_type）"""
        github_json = json.dumps([item.model_dump() for item in record.github_data], ensure_ascii=False)
        youtube_json = json.dumps([item.model_dump() for item in record.youtube_data], ensure_ascii=False)
        
        digest_type = getattr(record, 'digest_type', 'daily')
        
        cursor = await db.execute(
            """
            INSERT INTO digest_records (digest_date, digest_type, github_data, youtube_data, email_sent, email_sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(digest_date, digest_type) DO UPDATE SET
                github_data = excluded.github_data,
                youtube_data = excluded.youtube_data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record.digest_date.isoformat(),
                digest_type,
                github_json,
                youtube_json,
                1 if record.email_sent else 0,
                record.email_sent_at.isoformat() if record.email_sent_at else None
            )
        )
        await db.commit()
        return cursor.lastrowid
    
    @staticmethod
    async def create(db: aiosqlite.Connection, record: DigestRecord) -> int:
        """创建新的摘要记录（向后兼容）"""
        return await DigestRecordModel.create_with_type(db, record)
    
    @staticmethod
    async def get_by_date(db: aiosqlite.Connection, digest_date: date, digest_type: str = "daily") -> Optional[DigestRecord]:
        """根据日期和类型获取摘要记录"""
        cursor = await db.execute(
            "SELECT * FROM digest_records WHERE digest_date = ? AND digest_type = ?",
            (digest_date.isoformat(), digest_type)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        
        return DigestRecordModel._row_to_record(row)
    
    @staticmethod
    async def get_by_date_and_type(db: aiosqlite.Connection, digest_date: date, digest_type: str = "daily") -> Optional[DigestRecord]:
        """根据日期和类型获取摘要记录（别名方法）"""
        return await DigestRecordModel.get_by_date(db, digest_date, digest_type)
    
    @staticmethod
    async def get_latest(db: aiosqlite.Connection) -> Optional[DigestRecord]:
        """获取最新的摘要记录"""
        cursor = await db.execute(
            "SELECT * FROM digest_records ORDER BY digest_date DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        
        return DigestRecordModel._row_to_record(row)
    
    @staticmethod
    async def get_history(
        db: aiosqlite.Connection, 
        limit: int = 30, 
        offset: int = 0
    ) -> List[DigestRecordBrief]:
        """获取历史摘要列表"""
        return await DigestRecordModel.get_history_by_type(db, "daily", limit, offset)
    
    @staticmethod
    async def get_history_by_type(
        db: aiosqlite.Connection,
        digest_type: str = "daily",
        limit: int = 30, 
        offset: int = 0
    ) -> List[DigestRecordBrief]:
        """根据类型获取历史摘要列表"""
        cursor = await db.execute(
            """
            SELECT id, digest_date, github_data, youtube_data, email_sent, created_at
            FROM digest_records 
            WHERE digest_type = ?
            ORDER BY digest_date DESC 
            LIMIT ? OFFSET ?
            """,
            (digest_type, limit, offset)
        )
        rows = await cursor.fetchall()
        
        result = []
        for row in rows:
            github_data = json.loads(row['github_data']) if row['github_data'] else []
            youtube_data = json.loads(row['youtube_data']) if row['youtube_data'] else []
            
            result.append(DigestRecordBrief(
                id=row['id'],
                digest_date=date.fromisoformat(row['digest_date']),
                github_count=len(github_data),
                youtube_count=len(youtube_data),
                email_sent=bool(row['email_sent']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
            ))
        
        return result
    
    @staticmethod
    async def update_email_status(
        db: aiosqlite.Connection, 
        digest_date: date, 
        digest_type: str = "daily",
        sent: bool = True
    ):
        """更新邮件发送状态"""
        await db.execute(
            """
            UPDATE digest_records 
            SET email_sent = ?, email_sent_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE digest_date = ? AND digest_type = ?
            """,
            (1 if sent else 0, datetime.now().isoformat(), digest_date.isoformat(), digest_type)
        )
        await db.commit()
    
    @staticmethod
    def _row_to_record(row) -> DigestRecord:
        """将数据库行转换为DigestRecord对象"""
        github_data = []
        youtube_data = []
        
        if row['github_data']:
            github_list = json.loads(row['github_data'])
            github_data = [GitHubDigestItem(**item) for item in github_list]
        
        if row['youtube_data']:
            youtube_list = json.loads(row['youtube_data'])
            youtube_data = [YouTubeDigestItem(**item) for item in youtube_list]
        
        # 兼容旧数据，如果没有 digest_type 字段则默认为 daily
        try:
            digest_type = row['digest_type']
        except (KeyError, IndexError):
            digest_type = 'daily'
        
        return DigestRecord(
            id=row['id'],
            digest_date=date.fromisoformat(row['digest_date']),
            digest_type=digest_type,
            github_data=github_data,
            youtube_data=youtube_data,
            email_sent=bool(row['email_sent']),
            email_sent_at=datetime.fromisoformat(row['email_sent_at']) if row['email_sent_at'] else None,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
        )


class ExecutionLogModel:
    """执行日志数据库操作"""
    
    @staticmethod
    async def create(db: aiosqlite.Connection, log: ExecutionLog) -> int:
        """创建执行日志"""
        cursor = await db.execute(
            """
            INSERT INTO execution_logs 
            (execution_time, status, github_count, youtube_count, error_message, duration_seconds, digest_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log.execution_time.isoformat(),
                log.status,
                log.github_count,
                log.youtube_count,
                log.error_message,
                log.duration_seconds,
                log.digest_type
            )
        )
        await db.commit()
        return cursor.lastrowid
    
    @staticmethod
    async def get_recent(db: aiosqlite.Connection, limit: int = 50) -> List[ExecutionLog]:
        """获取最近的执行日志"""
        cursor = await db.execute(
            """
            SELECT * FROM execution_logs 
            ORDER BY execution_time DESC 
            LIMIT ?
            """,
            (limit,)
        )
        rows = await cursor.fetchall()
        
        return [
            ExecutionLog(
                id=row['id'],
                execution_time=datetime.fromisoformat(row['execution_time']),
                status=row['status'],
                github_count=row['github_count'],
                youtube_count=row['youtube_count'],
                error_message=row['error_message'],
                duration_seconds=row['duration_seconds'],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
            )
            for row in rows
        ]
    
    @staticmethod
    async def get_last_successful(db: aiosqlite.Connection) -> Optional[ExecutionLog]:
        """获取最后一次成功的执行"""
        cursor = await db.execute(
            """
            SELECT * FROM execution_logs 
            WHERE status = 'success'
            ORDER BY execution_time DESC 
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        if not row:
            return None
        
        return ExecutionLog(
            id=row['id'],
            execution_time=datetime.fromisoformat(row['execution_time']),
            status=row['status'],
            github_count=row['github_count'],
            youtube_count=row['youtube_count'],
            error_message=row['error_message'],
            duration_seconds=row['duration_seconds'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


class ConfigModel:
    """配置数据库操作"""
    
    @staticmethod
    async def get(db: aiosqlite.Connection, key: str) -> Optional[str]:
        """获取配置值"""
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()
        return row['value'] if row else None
    
    @staticmethod
    async def set(db: aiosqlite.Connection, key: str, value: str, description: str = None):
        """设置配置值"""
        await db.execute(
            """
            INSERT INTO config (key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                description = COALESCE(excluded.description, config.description),
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value, description)
        )
        await db.commit()
    
    @staticmethod
    async def get_all(db: aiosqlite.Connection) -> List[ConfigItem]:
        """获取所有配置"""
        cursor = await db.execute("SELECT key, value, description FROM config")
        rows = await cursor.fetchall()
        
        return [
            ConfigItem(key=row['key'], value=row['value'], description=row['description'])
            for row in rows
        ]
    
    @staticmethod
    async def delete(db: aiosqlite.Connection, key: str):
        """删除配置"""
        await db.execute("DELETE FROM config WHERE key = ?", (key,))
        await db.commit()