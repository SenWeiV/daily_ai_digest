import asyncio
import logging

import uvicorn

from app.agents.arxiv_agent import arxiv_agent
from app.agents.github_agent import github_agent
from app.agents.youtube_agent import youtube_agent
from app.main import app
from app.schemas import ArxivDigestItem, GitHubDigestItem, YouTubeDigestItem

logger = logging.getLogger("runtime-verification")


async def fake_github(time_range="daily"):
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


async def fake_arxiv():
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


async def fake_youtube():
    logger.info("SOURCE_START youtube")
    await asyncio.sleep(0.1)
    return [
        YouTubeDigestItem(
            video_id="verify-video",
            title="Existing YouTube digest behavior",
            channel="Verification Channel",
            video_url="https://youtube.com/watch?v=verify-video",
            view_count=100,
            like_count=10,
            comment_count=1,
            summary="The existing YouTube item remains present.",
        )
    ]


github_agent.get_research_repos = fake_github
arxiv_agent.fetch = fake_arxiv
youtube_agent._disabled = False
youtube_agent.client = object()
youtube_agent.get_top_videos = fake_youtube

uvicorn.run(app, host="127.0.0.1", port=18080, log_level="info")
