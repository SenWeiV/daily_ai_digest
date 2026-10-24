import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiosmtplib.errors import SMTPAuthenticationError, SMTPReadTimeoutError

import app.services.digest_service as module
from app.agents.arxiv_agent import ArxivAgent
from app.agents.github_agent import GitHubAgent
from app.api.routes import _mask_email
from app.config import settings
from app.content_profile import matching_profiles
from app.content_window import content_window
from app.database import get_db, init_database
from app.models import DigestRecordModel, ExecutionLogModel
from app.schemas import DigestRecord, GitHubDigestItem
from app.services.digest_assets import AssetBundle
from app.services.digest_service import DigestService
from app.services.email_service import PartialDeliveryError


def configured_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "isolated.db"))
    monkeypatch.setattr(module, "gemini_analyzer", SimpleNamespace(is_available=False))
    for key, value in {"sender_email": "sender@example.com", "app_password": "fake", "recipient_email": "to@example.com"}.items():
        monkeypatch.setattr(module.email_service, key, value)
    item = GitHubDigestItem(repo_name="ai/agent", repo_url="https://github.com/ai/agent", stars=100, quality_grade="A", research_topics=["agentic"])
    service = DigestService()
    service._collect_source_data = AsyncMock(return_value=([item], []))
    service._build_assets = AsyncMock(return_value=AssetBundle())
    monkeypatch.setattr(module.github_agent, "analyze_selected_repos", AsyncMock(side_effect=lambda items: items))
    return service


def test_failed_delivery_reuses_content_and_does_not_report_success(monkeypatch, tmp_path):
    service = configured_service(monkeypatch, tmp_path)
    send = AsyncMock(side_effect=[SMTPAuthenticationError(535, "rejected"), True])
    monkeypatch.setattr(module.email_service, "send_digest_email", send)

    async def run():
        await init_database()
        first = await service.generate_digest(target_date=date(2026, 10, 23))
        assert not first[0] and first[2].delivery_status == "failed"
        async with get_db() as db:
            assert (await ExecutionLogModel.get_recent(db, 1))[0].status == "failed"
        second = await service.generate_digest(target_date=date(2026, 10, 23))
        assert second[0] and second[2].email_sent
        third = await service.generate_digest(target_date=date(2026, 10, 23))
        assert third[0]
        assert send.await_count == 2
        assert service._collect_source_data.await_count == 1
        async with get_db() as db:
            saved = await DigestRecordModel.get_by_date(db, date(2026, 10, 23))
            assert saved.email_sent and saved.delivery_status == "sent"
    asyncio.run(run())


@pytest.mark.parametrize("error,status", [(SMTPReadTimeoutError("DATA timed out"), "unknown"), (PartialDeliveryError("one refused"), "partial")])
def test_uncertain_delivery_is_not_retried_without_force(monkeypatch, tmp_path, error, status):
    service = configured_service(monkeypatch, tmp_path)
    send = AsyncMock(side_effect=error)
    monkeypatch.setattr(module.email_service, "send_digest_email", send)

    async def run():
        await init_database()
        first = await service.generate_digest(target_date=date(2026, 10, 23))
        assert not first[0] and first[2].delivery_status == status
        second = await service.generate_digest(target_date=date(2026, 10, 23))
        assert not second[0] and "核对收件箱" in second[1]
        assert send.await_count == 1
        async with get_db() as db:
            assert (await DigestRecordModel.get_by_date(db, date(2026, 10, 23))).delivery_status == status
    asyncio.run(run())


def test_regeneration_clears_stale_sent_state(monkeypatch, tmp_path):
    service = configured_service(monkeypatch, tmp_path)
    send = AsyncMock(side_effect=[True, SMTPAuthenticationError(535, "rejected")])
    monkeypatch.setattr(module.email_service, "send_digest_email", send)

    async def run():
        await init_database()
        assert (await service.generate_digest(target_date=date(2026, 10, 23)))[0]
        assert not (await service.generate_digest(target_date=date(2026, 10, 23), force=True))[0]
        async with get_db() as db:
            record = await DigestRecordModel.get_by_date(db, date(2026, 10, 23))
            assert not record.email_sent and record.email_sent_at is None
            assert record.delivery_status == "failed"
    asyncio.run(run())


def test_business_day_is_half_open_in_utc():
    window = content_window("daily", date(2026, 10, 23), "Asia/Shanghai")
    assert window.start.isoformat() == "2026-10-22T16:00:00+00:00"
    assert window.contains("2026-10-22T16:00:00Z")
    assert not window.contains("2026-10-23T16:00:00Z")
    assert not window.contains(None)
    assert "2026-10-23T15:59:59Z" in window.github_range
    assert content_window("monthly", date(2026, 10, 23), "Asia/Shanghai").start.day == 30


def test_period_is_forwarded_to_both_sources():
    service = DigestService()
    service._fetch_github_data = AsyncMock(return_value=[])
    service._fetch_arxiv_data = AsyncMock(return_value=[])
    window = content_window("daily", date(2026, 10, 23), "Asia/Shanghai")
    asyncio.run(service._collect_source_data("daily", window))
    service._fetch_github_data.assert_awaited_once_with("daily", window)
    service._fetch_arxiv_data.assert_awaited_once_with(window)


def test_after_midnight_delivery_uses_the_delivery_day_for_target(monkeypatch, tmp_path):
    from zoneinfo import ZoneInfo
    service = configured_service(monkeypatch, tmp_path)
    async def run():
        await init_database()
        result = await service.generate_digest(send_email=False, send_at=datetime(2026, 10, 25, 0, 10, tzinfo=ZoneInfo("Asia/Shanghai")))
        assert result[0] and result[2].digest_date == date(2026, 10, 24)
        assert service._collect_source_data.await_args.args[1].start == datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
    asyncio.run(run())


def test_arxiv_queries_historical_window_and_filters_upstream_results(monkeypatch):
    window = content_window("daily", date(2026, 10, 23), "Asia/Shanghai")
    requests = []
    feed = '''<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>http://arxiv.org/abs/2610.00001v1</id><title>LLM agent evaluation method</title><published>2026-10-23T01:00:00Z</published><summary>A method and benchmark results</summary><category term="cs.AI"/></entry>
      <entry><id>http://arxiv.org/abs/2610.00002v1</id><title>LLM agent evaluation method</title><published>2026-10-23T16:00:00Z</published></entry>
    </feed>'''
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=feed)
    original_client = httpx.AsyncClient
    monkeypatch.setattr("app.agents.arxiv_agent.httpx.AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw))
    result = asyncio.run(ArxivAgent().fetch(window))
    assert [item.arxiv_id for item in result] == ["2610.00001"]
    assert result[0].categories == ["cs.AI"]
    assert window.arxiv_range in requests[0].url.params["search_query"]


def test_github_search_uses_exact_activity_window(monkeypatch):
    agent = GitHubAgent()
    calls = []
    agent.client = SimpleNamespace(search_repositories=lambda **kw: calls.append(kw) or [])
    monkeypatch.setattr(settings, "github_search_queries", "topic:world-models")
    window = content_window("daily", date(2026, 10, 23), "Asia/Shanghai")
    asyncio.run(agent.search_popular_active_candidates(window))
    assert calls[0]["query"].endswith("pushed:" + window.github_range)


def test_trending_has_a_total_wall_clock_budget(monkeypatch):
    agent = GitHubAgent()
    async def stall(*args):
        await asyncio.sleep(10)
    agent._fetch_trending_repos = stall
    monkeypatch.setattr(settings, "github_trending_total_timeout_seconds", 0.01)
    assert asyncio.run(agent.fetch_trending_repos()) == []


def test_generic_workflow_is_not_an_ai_agent():
    assert matching_profiles("php/php-src A language implementation with workflow and framework documentation") == []
    assert "agentic" in matching_profiles("LLM agent workflow framework with memory")
    assert "agentic" in matching_profiles("MCP server implementation")


def test_digest_reads_are_type_specific_and_reject_invalid_type(monkeypatch, tmp_path):
    from app.main import app
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "types.db"))
    async def run():
        await init_database()
        async with get_db() as db:
            for typ, day in [("daily", 24), ("weekly", 19), ("monthly", 1)]:
                await DigestRecordModel.create_with_type(db, DigestRecord(digest_date=date(2026, 10, day), digest_type=typ))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            weekly = await client.get("/api/digest/latest?digest_type=weekly")
            assert weekly.json()["digest_type"] == "weekly"
            monthly = await client.get("/api/digest/2026-10-01?digest_type=monthly")
            assert monthly.json()["digest_type"] == "monthly"
            assert (await client.get("/api/digest/latest?digest_type=invalid")).status_code == 422
            assert (await client.get("/api/digest/2026-10-01?digest_type=invalid")).status_code == 422
    asyncio.run(run())


def test_multiple_recipient_addresses_are_masked_individually():
    assert _mask_email("alice@a.com,bob@b.com") == "al***@a.com, bo***@b.com"


def test_paid_and_mutating_api_routes_require_admin_key(monkeypatch):
    from pydantic import SecretStr
    from app.main import app
    from app.services.scheduler import scheduler_service
    monkeypatch.setattr(settings, "admin_api_key", SecretStr("test-admin-key"))
    trigger = AsyncMock()
    monkeypatch.setattr(scheduler_service, "trigger_now", trigger)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for method, path in [("POST", "/api/digest/trigger"), ("POST", "/api/email/test"), ("PUT", "/api/config")]:
                response = await client.request(method, path, json={})
                assert response.status_code == 401
            response = await client.post("/api/digest/trigger", json={"send_email": False}, headers={"Authorization": "Bearer wrong"})
            assert response.status_code == 401
            trigger.assert_not_awaited()
            response = await client.post("/api/digest/trigger", json={"send_email": False}, headers={"Authorization": "Bearer test-admin-key"})
            assert response.status_code == 200
            trigger.assert_awaited_once()
            monkeypatch.setattr(settings, "admin_api_key", SecretStr(""))
            assert (await client.post("/api/email/test")).status_code == 503
    asyncio.run(run())
