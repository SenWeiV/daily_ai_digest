import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import httpx

from app.agents.arxiv_agent import ArxivAgent
from app.agents.github_agent import GitHubAgent
from app.content_profile import (
    extract_explicit_arxiv_ids,
    is_research_relevant,
    matching_profiles,
    quality_grade,
    value_evidence,
)
from app.schemas import ArxivDigestItem, GitHubDigestItem
from app.services.content_selector import select_research_items


def github_item(name: str, grade: str, topic: str = "agentic") -> GitHubDigestItem:
    return GitHubDigestItem(
        repo_name=name,
        repo_url=f"https://github.com/{name}",
        stars=1,
        quality_grade=grade,
        quality_evidence=["substantive_readme", "implementation"],
        research_topics=[topic],
    )


def arxiv_item(identifier: str, grade: str, topic: str = "multimodal") -> ArxivDigestItem:
    return ArxivDigestItem(
        arxiv_id=identifier,
        title=f"Paper {identifier}",
        abstract="A method with benchmark evaluation results.",
        arxiv_url=f"https://arxiv.org/abs/{identifier}",
        quality_grade=grade,
        quality_evidence=["method", "evaluation"],
        research_topics=[topic],
    )


def test_profile_requires_domain_and_content_signals():
    assert not is_research_relevant("agent")
    assert not is_research_relevant("dataset")
    assert "multimodal" in matching_profiles("vision-language model evaluation benchmark")
    assert "data-evaluation" in matching_profiles("LLM evaluation benchmark dataset")


def test_new_project_value_evidence_rejects_placeholder():
    empty = value_evidence({"description": "AI agent", "topics": []}, {"readme_content": "Coming soon"})
    assert quality_grade(relevant=True, evidence=empty) == "C"
    assert quality_grade(
        relevant=True,
        evidence={"technical_description", "research_topics"},
    ) == "B"

    evidence = value_evidence(
        {"description": "A concrete vision-language benchmark implementation with reproducible experiments."},
        {"readme_content": "vision-language benchmark " * 30, "code_files": {"main.py": "pass"}},
    )
    assert {"substantive_readme", "implementation", "artifacts_or_experiments"} <= evidence
    assert quality_grade(relevant=True, evidence=evidence) == "A"


def test_explicit_arxiv_relation_normalizes_version():
    assert extract_explicit_arxiv_ids("See https://arxiv.org/abs/2308.03688v3") == ["2308.03688"]


def test_dynamic_selection_examples():
    github = [github_item(f"org/a{i}", "A") for i in range(7)]
    papers = [arxiv_item(f"2401.{i:05d}", "B") for i in range(10)]
    selected_github, selected_arxiv = select_research_items(github, papers)
    assert len(selected_github) + len(selected_arxiv) == 10
    assert len(selected_github) == 7

    sixteen = [github_item(f"org/sixteen{i}", "A") for i in range(16)]
    selected_github, selected_arxiv = select_research_items(sixteen, [])
    assert len(selected_github) + len(selected_arxiv) == 16

    thirty = [github_item(f"org/thirty{i}", "A") for i in range(30)]
    selected_github, selected_arxiv = select_research_items(thirty, [])
    assert len(selected_github) + len(selected_arxiv) == 24

    sparse = [github_item(f"org/sparse{i}", "A") for i in range(4)]
    sparse.extend(github_item(f"org/b{i}", "B") for i in range(2))
    sparse.extend(github_item(f"org/c{i}", "C") for i in range(20))
    selected_github, selected_arxiv = select_research_items(sparse, [])
    assert len(selected_github) + len(selected_arxiv) == 6
    assert all(item.quality_grade != "C" for item in selected_github)


def test_selection_is_deterministic_and_deduplicates():
    items = [github_item("org/repo", "B"), github_item("org/repo", "A")]
    first = select_research_items(items, [], target_items=1, max_items=2)[0]
    second = select_research_items(reversed(items), [], target_items=1, max_items=2)[0]
    assert [item.repo_name for item in first] == [item.repo_name for item in second] == ["org/repo"]
    assert first[0].quality_grade == "A"


def test_arxiv_feed_parsing_and_cross_category_deduplication():
    feed = """<?xml version="1.0"?>
    <rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
      <item>
        <title>Vision-language evaluation benchmark</title>
        <link>https://arxiv.org/abs/2501.01234v2</link>
        <description>We propose a method and report benchmark evaluation results. Code: https://github.com/acme/vlm-eval</description>
        <dc:creator>A. Researcher</dc:creator>
        <pubDate>Tue, 15 Jul 2026 00:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    agent = ArxivAgent()
    cv_items = agent.parse_feed(feed, "cs.CV")
    lg_items = agent.parse_feed(feed, "cs.LG")
    merged = agent.merge_items(cv_items + lg_items)
    assert len(merged) == 1
    assert merged[0].arxiv_id == "2501.01234"
    assert merged[0].categories == ["cs.CV", "cs.LG"]
    assert merged[0].github_urls == ["https://github.com/acme/vlm-eval"]
    assert merged[0].quality_grade == "A"


def test_explicit_cross_source_relation_keeps_one_entry_and_metadata():
    repo = github_item("acme/vlm-eval", "A", topic="multimodal")
    paper = arxiv_item("2501.01234", "A")
    paper.github_urls = [repo.repo_url]

    selected_github, selected_arxiv = select_research_items(
        [repo],
        [paper],
        target_items=1,
        max_items=2,
    )

    assert len(selected_github) + len(selected_arxiv) == 1
    assert selected_github[0].related_arxiv_ids == [paper.arxiv_id]
    assert paper.related_repo_names == [repo.repo_name]


def test_root_source_tree_counts_as_implementation_evidence():
    evidence = value_evidence(
        {"description": "A concrete vision-language evaluation toolkit for reproducible model comparisons."},
        {
            "readme_content": "vision-language evaluation benchmark " * 20,
            "root_entries": ["src", "tests", "pyproject.toml"],
        },
    )
    assert {"implementation", "artifacts_or_experiments"} <= evidence


def test_search_candidates_are_bounded_across_channels(monkeypatch):
    class FakeRepo:
        def __init__(self, repo_id: int):
            self.id = repo_id
            self.full_name = f"org/repo-{repo_id}"
            self.html_url = f"https://github.com/{self.full_name}"
            self.description = "vision-language benchmark implementation"
            self.language = "Python"
            self.stargazers_count = repo_id
            self.forks_count = 0
            self.created_at = datetime(2026, 7, 1)
            self.updated_at = datetime(2026, 7, 15)

    class FakeClient:
        def __init__(self):
            self.queries = []

        def search_repositories(self, query, sort, order):
            self.queries.append(query)
            offset = 100 if "pushed:" in query else 0
            return [FakeRepo(offset + index) for index in range(1, 5)]

    agent = GitHubAgent()
    agent.client = FakeClient()
    monkeypatch.setattr("app.agents.github_agent.settings.github_candidate_limit", 6)
    monkeypatch.setattr("app.agents.github_agent.settings.github_search_queries", "q1;q2")

    candidates = asyncio.run(agent.search_repository_candidates())

    assert len(candidates) <= 6
    assert {item["channel"] for item in candidates} == {"new", "updated"}
    assert len(agent.client.queries) == 4


def test_model_analysis_is_bounded_by_shared_selection():
    agent = GitHubAgent()
    candidates = [github_item(f"org/repo-{index}", "A") for index in range(8)]
    selected, _ = select_research_items(candidates, [], target_items=3, max_items=3)
    for item in candidates:
        agent._analysis_context[item.repo_url] = {"repo": object(), "details": {}}
    agent.analyze_repo = AsyncMock(return_value=github_item("org/analyzed", "A"))

    asyncio.run(agent.analyze_selected_repos(selected))

    assert agent.analyze_repo.await_count == 3


def test_arxiv_atom_parsing_reads_namespaced_summary_and_category_terms():
    feed = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2501.09999v1</id>
        <title>Agent benchmark implementation</title>
        <summary>We propose an LLM agent framework and report benchmark evaluation results.</summary>
        <author><name>B. Researcher</name></author>
        <category term="cs.AI" />
        <category term="cs.LG" />
        <published>2026-07-15T00:00:00Z</published>
        <updated>2026-07-15T01:00:00Z</updated>
      </entry>
    </feed>"""

    item = ArxivAgent().parse_feed(feed, "cs.AI")[0]

    assert item.abstract.startswith("We propose")
    assert item.categories == ["cs.AI", "cs.LG"]
    assert item.authors == ["B. Researcher"]
    assert item.quality_grade == "A"


def test_github_channels_deduplicate_by_numeric_repository_id():
    class FakeRepo:
        id = 42
        full_name = "org/new-name"

    repo = FakeRepo()
    agent = GitHubAgent()
    agent.fetch_trending_repos = AsyncMock(return_value=[])
    agent.search_repository_candidates = AsyncMock(
        return_value=[
            {"repo_id": 42, "full_name": "org/new-name", "channel": "new", "repo": repo},
            {"repo_id": 42, "full_name": "org/old-name", "channel": "updated", "repo": repo},
        ]
    )
    agent.fetch_repo_details = AsyncMock(return_value={"readme_content": "readme", "topics": []})
    agent.candidate_quality = Mock(return_value=("A", {"implementation", "substantive_readme"}, ["agentic"]))
    candidate = github_item("org/new-name", "A")
    agent.analyze_repo = AsyncMock(return_value=candidate)

    results = asyncio.run(agent.get_research_repos())

    assert results == [candidate]
    assert agent.fetch_repo_details.await_count == 1
    assert agent.analyze_repo.await_args.kwargs["deep_analysis"] is False


def test_unrelated_trending_candidate_is_not_used_as_fallback():
    class FakeRepo:
        id = 7
        full_name = "org/unrelated"

    repo = FakeRepo()
    agent = GitHubAgent()
    agent.fetch_trending_repos = AsyncMock(
        return_value=[{"full_name": repo.full_name, "channel": "trending", "repo": repo}]
    )
    agent.search_repository_candidates = AsyncMock(return_value=[])
    agent.fetch_repo_details = AsyncMock(return_value={"readme_content": "generic utility", "topics": []})
    agent.candidate_quality = Mock(return_value=("C", set(), []))
    agent.analyze_repo = AsyncMock()

    results = asyncio.run(agent.get_research_repos())

    assert results == []
    agent.analyze_repo.assert_not_awaited()


def test_arxiv_feed_failure_does_not_drop_other_categories(monkeypatch):
    feed = """<rss><channel><item>
      <title>Agent benchmark implementation</title>
      <link>https://arxiv.org/abs/2501.08888v1</link>
      <description>We propose an LLM agent method and report benchmark evaluation results.</description>
    </item></channel></rss>"""

    class FakeResponse:
        text = feed

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            if url.endswith("cs.AI"):
                raise httpx.ConnectError("unavailable")
            return FakeResponse()

    agent = ArxivAgent()
    agent.categories = ("cs.AI", "cs.LG")
    monkeypatch.setattr("app.agents.arxiv_agent.httpx.AsyncClient", lambda **kwargs: FakeClient())

    items = asyncio.run(agent.fetch())

    assert [item.arxiv_id for item in items] == ["2501.08888"]
