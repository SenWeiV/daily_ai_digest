import asyncio
import logging
import os
import tempfile
from datetime import timedelta

import uvicorn

from app.agents.arxiv_agent import arxiv_agent
from app.agents.github_agent import github_agent
from app.main import app
from app.schemas import ArxivDigestItem, GitHubDigestItem
from app.schemas import DigestRecord
from app.config import settings
from app.database import get_db, init_database
from app.models import DigestRecordModel
from app.services.content_selector import select_research_items
from app.services.digest_service import local_today
from app.services.email_service import email_service
from app.api.auth import require_admin

logger = logging.getLogger("runtime-verification")


async def fake_github(time_range="daily", window=None):
    logger.info("SOURCE_START github %s", time_range)
    await asyncio.sleep(0.1)
    return [
        GitHubDigestItem(
            repo_name="research/trending-vision-agent",
            repo_url="https://github.com/research/trending-vision-agent",
            stars=4200,
            forks=320,
            watchers=85,
            open_issues=42,
            recent_issue_comments=18,
            source_channel="trending",
            trending_rank=2,
            trending_period="daily",
            recent_stars=350,
            recent_star_period_days=1,
            recent_star_velocity=350.0,
            description="A rising vision-language agent benchmark implementation.",
            summary="A reproducible benchmark for vision-language agents.",
            research_topics=["multimodal", "agentic"],
            quality_evidence=["trending_momentum", "recent_conversation", "implementation"],
            quality_grade="A",
        ),
        GitHubDigestItem(
            repo_name="research/eval-toolkit",
            repo_url="https://github.com/research/eval-toolkit",
            stars=18000,
            forks=950,
            watchers=140,
            open_issues=65,
            recent_issue_comments=7,
            source_channel="trending",
            trending_rank=6,
            trending_period="daily",
            recent_stars=120,
            recent_star_period_days=1,
            recent_star_velocity=120.0,
            description="Evaluation toolkit with datasets and examples.",
            summary="An evaluation toolkit for model and agent workflows.",
            research_topics=["data-evaluation"],
            quality_evidence=["trending_momentum", "recent_conversation", "implementation"],
            quality_grade="A",
        ),
        GitHubDigestItem(
            repo_name="marketing/keyword-only",
            repo_url="https://github.com/marketing/keyword-only",
            stars=999,
            description="AI agent news.",
            quality_grade="C",
        ),
    ]


async def fake_arxiv(window=None):
    logger.info("SOURCE_START arxiv")
    await asyncio.sleep(0.1)
    return [
        ArxivDigestItem(
            arxiv_id="2607.01234",
            title="Reliable Evaluation for Multimodal Agents",
            abstract="We propose an evaluation protocol and report benchmark results.",
            authors=["A. Researcher", "B. Engineer"],
            categories=["cs.AI", "cs.CV"],
            arxiv_url="https://arxiv.org/abs/2607.01234",
            summary="A benchmark-backed evaluation protocol for multimodal agents.",
            research_topics=["multimodal", "data-evaluation", "agentic"],
            quality_evidence=["method", "evaluation"],
            quality_grade="A",
        )
    ]


github_agent.get_research_repos = fake_github
arxiv_agent.fetch = fake_arxiv

# This fixture must never use the normal database or deliver real email.
settings.database_path = os.environ.get("DATABASE_PATH") or os.path.join(tempfile.mkdtemp(prefix="digest-fixture-"), "digest.db")
email_service.sender_email = email_service.app_password = email_service.recipient_email = ""
app.dependency_overrides[require_admin] = lambda: None


async def seed_fixture_records():
    await init_database()
    github, papers = select_research_items(await fake_github(), await fake_arxiv())
    today = local_today()
    dates = {"daily": today - timedelta(days=1), "weekly": today - timedelta(days=today.weekday()), "monthly": today.replace(day=1)}
    async with get_db() as db:
        for digest_type, target in dates.items():
            await DigestRecordModel.create_with_type(db, DigestRecord(
                digest_date=target, digest_type=digest_type, github_data=github, arxiv_data=papers,
            ))


asyncio.run(seed_fixture_records())

uvicorn.run(app, host="127.0.0.1", port=18080, log_level="info")
