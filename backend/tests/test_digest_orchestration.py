import asyncio
from datetime import date
from unittest.mock import AsyncMock

import app.services.digest_service as digest_module
from app.schemas import ArxivDigestItem
from app.services.digest_service import DigestService


def test_source_collection_starts_research_sources_together():
    service = DigestService()
    started: list[str] = []
    all_started = asyncio.Event()

    async def source(name: str, value: list):
        started.append(name)
        if len(started) == 2:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)
        return value

    async def fetch_github(digest_type):
        return await source("github", ["github"])

    async def fetch_arxiv():
        return await source("arxiv", ["arxiv"])

    service._fetch_github_data = AsyncMock(side_effect=fetch_github)
    service._fetch_arxiv_data = AsyncMock(side_effect=fetch_arxiv)

    result = asyncio.run(service._collect_source_data("daily"))

    assert set(started) == {"github", "arxiv"}
    assert result == (["github"], ["arxiv"])
    service._fetch_github_data.assert_awaited_once_with("daily")
    service._fetch_arxiv_data.assert_awaited_once_with()


def test_no_email_probe_does_not_suppress_the_scheduled_run(monkeypatch):
    """临时 send_email=False 运行不能制造当天记录，令晚间调度误跳过。"""
    service = DigestService()
    records = {}
    created_records = []

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def get_existing(db, record_date, digest_type):
        return records.get((record_date, digest_type))

    async def create_record(db, record):
        records[(record.digest_date, record.digest_type)] = record
        created_records.append(record)

    monkeypatch.setattr(digest_module, "get_db", lambda: _DB())
    monkeypatch.setattr(
        digest_module.DigestRecordModel,
        "get_by_date_and_type",
        get_existing,
    )
    monkeypatch.setattr(
        digest_module.DigestRecordModel,
        "create_with_type",
        create_record,
    )
    monkeypatch.setattr(
        digest_module.ExecutionLogModel,
        "create",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service,
        "_collect_source_data",
        AsyncMock(return_value=([], [])),
    )
    monkeypatch.setattr(
        service,
        "_analyze_arxiv_items",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        digest_module.github_agent,
        "analyze_selected_repos",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(digest_module.email_service, "sender_email", "")
    monkeypatch.setattr(digest_module.email_service, "app_password", "")
    monkeypatch.setattr(digest_module.email_service, "recipient_email", "")

    probe = asyncio.run(
        service.generate_digest(
            "daily", target_date=date(2026, 8, 3), send_email=False, force=True
        )
    )
    assert probe[0] is True
    assert created_records == []
    assert records == {}

    scheduled = asyncio.run(
        service.generate_digest(
            "daily", target_date=date(2026, 8, 3), send_email=True, force=False
        )
    )
    # Requested delivery without SMTP configuration must report failure.
    assert scheduled[0] is False
    assert len(created_records) == 1
    assert len(records) == 1


def test_arxiv_analysis_uses_bounded_concurrency_and_isolates_failures(monkeypatch):
    class FakeAnalyzer:
        is_available = True

        def __init__(self):
            self.active = 0
            self.max_active = 0

        async def analyze_arxiv_paper(self, title, abstract, authors, categories):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            if title == "Paper 4":
                raise RuntimeError("analysis unavailable")
            return {"summary": f"Analyzed {title}"}

    analyzer = FakeAnalyzer()
    monkeypatch.setattr("app.services.digest_service.gemini_analyzer", analyzer)
    items = [
        ArxivDigestItem(
            arxiv_id=f"2501.{index:05d}",
            title=f"Paper {index}",
            arxiv_url=f"https://arxiv.org/abs/2501.{index:05d}",
        )
        for index in range(7)
    ]

    analyzed = asyncio.run(DigestService()._analyze_arxiv_items(items))

    assert analyzer.max_active == 3
    assert analyzed[0].summary == "Analyzed Paper 0"
    assert analyzed[4].summary is None
    assert len(analyzed) == 7


def test_youtube_is_no_longer_collected():
    assert not hasattr(DigestService, "_fetch_youtube_data")


def test_daily_digest_defaults_to_the_previous_day():
    assert digest_module.default_target_date("daily", today=date(2026, 10, 25)) == date(2026, 10, 24)
    # 周报、月报仍按当天所在的周/月
    assert digest_module.default_target_date("weekly", today=date(2026, 10, 25)) == date(2026, 10, 25)
    assert digest_module.default_target_date("monthly", today=date(2026, 10, 25)) == date(2026, 10, 25)


def test_wait_until_sleeps_only_when_ready_early(monkeypatch):
    from datetime import datetime, timedelta, timezone

    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(digest_module.asyncio, "sleep", fake_sleep)
    now = datetime.now(timezone.utc)

    asyncio.run(DigestService._wait_until(now + timedelta(minutes=20)))
    asyncio.run(DigestService._wait_until(now - timedelta(minutes=5)))
    asyncio.run(DigestService._wait_until(None))

    assert len(slept) == 1
    assert 19 * 60 < slept[0] <= 20 * 60
