import asyncio
from datetime import date, datetime

import aiosqlite

from app.config import settings
from app.database import get_db, init_database
from app.models import DigestRecordModel, ExecutionLogModel
from app.schemas import ArxivDigestItem, DigestRecord, ExecutionLog, GitHubDigestItem


def test_arxiv_persistence_and_legacy_empty_default(tmp_path):
    original_path = settings.database_path
    settings.database_path = str(tmp_path / "digest.db")

    async def run():
        await init_database()
        record = DigestRecord(
            digest_date=date(2026, 7, 15),
            github_data=[GitHubDigestItem(repo_name="org/repo", repo_url="https://github.com/org/repo", stars=1)],
            arxiv_data=[
                ArxivDigestItem(
                    arxiv_id="2501.01234",
                    title="Paper",
                    arxiv_url="https://arxiv.org/abs/2501.01234",
                )
            ],
        )
        async with get_db() as db:
            await DigestRecordModel.create_with_type(db, record)
            loaded = await DigestRecordModel.get_by_date(db, record.digest_date)
            assert loaded is not None
            assert loaded.arxiv_data[0].arxiv_id == "2501.01234"
            history = await DigestRecordModel.get_history_by_type(db, "daily")
            assert history[0].arxiv_count == 1

            await db.execute(
                "INSERT INTO digest_records (digest_date, digest_type, github_data, arxiv_data, youtube_data) VALUES (?, ?, ?, NULL, ?)",
                ("2026-07-14", "daily", "[]", "[]"),
            )
            await db.commit()
            legacy = await DigestRecordModel.get_by_date(db, date(2026, 7, 14))
            assert legacy is not None
            assert legacy.arxiv_data == []

    try:
        asyncio.run(run())
    finally:
        settings.database_path = original_path


def test_legacy_unique_constraint_rebuild_preserves_data(tmp_path):
    original_path = settings.database_path
    database_path = tmp_path / "legacy.db"
    settings.database_path = str(database_path)

    async def run():
        async with aiosqlite.connect(database_path) as db:
            await db.executescript(
                """
                CREATE TABLE digest_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    digest_date DATE NOT NULL UNIQUE,
                    digest_type TEXT DEFAULT 'daily' NOT NULL,
                    github_data TEXT,
                    youtube_data TEXT,
                    email_sent INTEGER DEFAULT 0,
                    email_sent_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO digest_records (digest_date, digest_type, github_data, youtube_data)
                VALUES ('2026-07-13', 'daily', '[]', '[]');
                """
            )

        await init_database()

        async with aiosqlite.connect(database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM digest_records")).fetchone()
            schema = await (
                await db.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='digest_records'"
                )
            ).fetchone()
            assert row["digest_date"] == "2026-07-13"
            assert row["arxiv_data"] is None
            assert "UNIQUE(digest_date, digest_type)" in schema[0]

    try:
        asyncio.run(run())
    finally:
        settings.database_path = original_path


def test_execution_logs_preserve_digest_type(tmp_path):
    original_path = settings.database_path
    settings.database_path = str(tmp_path / "execution-logs.db")

    async def run():
        await init_database()
        log = ExecutionLog(
            execution_time=datetime(2026, 7, 15, 8, 37),
            status="success",
            github_count=20,
            youtube_count=0,
            digest_type="monthly",
        )
        async with get_db() as db:
            await ExecutionLogModel.create(db, log)
            recent = await ExecutionLogModel.get_recent(db, limit=1)
            latest = await ExecutionLogModel.get_last_successful(db)
            assert recent[0].digest_type == "monthly"
            assert latest is not None
            assert latest.digest_type == "monthly"

    try:
        asyncio.run(run())
    finally:
        settings.database_path = original_path
