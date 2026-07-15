import asyncio
from unittest.mock import AsyncMock

from app.schemas import ArxivDigestItem
from app.services.digest_service import DigestService


def test_source_collection_starts_youtube_with_research_sources():
    service = DigestService()
    started: list[str] = []
    all_started = asyncio.Event()

    async def source(name: str, value: list):
        started.append(name)
        if len(started) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)
        return value

    async def fetch_github(digest_type):
        return await source("github", ["github"])

    async def fetch_arxiv():
        return await source("arxiv", ["arxiv"])

    async def fetch_youtube():
        return await source("youtube", ["youtube"])

    service._fetch_github_data = AsyncMock(side_effect=fetch_github)
    service._fetch_arxiv_data = AsyncMock(side_effect=fetch_arxiv)
    service._fetch_youtube_data = AsyncMock(side_effect=fetch_youtube)

    result = asyncio.run(service._collect_source_data("daily"))

    assert set(started) == {"github", "arxiv", "youtube"}
    assert result == (["github"], ["arxiv"], ["youtube"])
    service._fetch_github_data.assert_awaited_once_with("daily")
    service._fetch_arxiv_data.assert_awaited_once_with()
    service._fetch_youtube_data.assert_awaited_once_with()


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
