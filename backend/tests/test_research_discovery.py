import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import httpx

from app.agents.arxiv_agent import ArxivAgent
from app.agents.github_agent import GitHubAgent
from app.content_profile import (
    extract_explicit_arxiv_ids,
    github_social_grade,
    is_research_relevant,
    matching_profiles,
    quality_grade,
    value_evidence,
)
from app.config import Settings
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


def test_popular_active_search_is_bounded_and_never_queries_created(monkeypatch):
    class FakeRepo:
        def __init__(self, repo_id: int):
            self.id = repo_id
            self.full_name = f"org/repo-{repo_id}"
            self.html_url = f"https://github.com/{self.full_name}"
            self.description = "vision-language benchmark implementation"
            self.language = "Python"
            self.stargazers_count = repo_id
            self.forks_count = 12
            self.subscribers_count = 8
            self.open_issues_count = 15
            self.created_at = datetime(2026, 7, 1)
            self.updated_at = datetime(2026, 7, 15)

    class FakeClient:
        def __init__(self):
            self.calls = []

        def search_repositories(self, query, sort, order):
            self.calls.append((query, sort, order))
            return [FakeRepo(index) for index in range(1, 5)]

    agent = GitHubAgent()
    agent.client = FakeClient()
    monkeypatch.setattr("app.agents.github_agent.settings.github_candidate_limit", 6)
    monkeypatch.setattr("app.agents.github_agent.settings.github_search_queries", "q1;q2")

    candidates = asyncio.run(agent.search_popular_active_candidates())

    assert len(candidates) <= 6
    assert {item["source_channel"] for item in candidates} == {"search"}
    assert len(agent.client.calls) == 2
    assert all("pushed:" in query and "created:" not in query for query, _, _ in agent.client.calls)
    assert all(sort == "stars" and order == "desc" for _, sort, order in agent.client.calls)


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


def test_fallback_candidates_deduplicate_by_numeric_repository_id():
    class FakeRepo:
        id = 42
        full_name = "org/new-name"
        stargazers_count = 5000
        forks_count = 50
        subscribers_count = 25
        open_issues_count = 30

    repo = FakeRepo()
    agent = GitHubAgent()
    agent.fetch_trending_repos = AsyncMock(return_value=[])
    agent.search_popular_active_candidates = AsyncMock(
        return_value=[
            {"repo_id": 42, "full_name": "org/new-name", "source_channel": "search", "repo": repo},
            {"repo_id": 42, "full_name": "org/old-name", "source_channel": "search", "repo": repo},
        ]
    )
    agent.fetch_repo_details = AsyncMock(return_value={"readme_content": "readme", "topics": []})
    agent.is_ai_related = Mock(return_value=True)
    agent.fetch_recent_issue_comment_count = AsyncMock(return_value=12)
    agent.candidate_quality = Mock(return_value=("B", {"recent_conversation"}, ["agentic"]))
    candidate = github_item("org/new-name", "B")
    agent.analyze_repo = AsyncMock(return_value=candidate)

    results = asyncio.run(agent.get_research_repos())

    assert results == [candidate]
    assert agent.fetch_repo_details.await_count == 1
    assert agent.analyze_repo.await_args.kwargs["deep_analysis"] is False


def test_unrelated_trending_candidate_is_not_used_as_fallback():
    class FakeRepo:
        id = 7
        full_name = "org/unrelated"
        stargazers_count = 100_000
        forks_count = 500
        subscribers_count = 100
        open_issues_count = 200

    repo = FakeRepo()
    agent = GitHubAgent()
    agent.fetch_trending_repos = AsyncMock(
        return_value=[{"full_name": repo.full_name, "source_channel": "trending", "repo": repo}]
    )
    agent.search_popular_active_candidates = AsyncMock(return_value=[])
    agent.fetch_repo_details = AsyncMock(return_value={"readme_content": "generic utility", "topics": []})
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


def test_trending_uses_one_global_attempt_budget_and_cycles_access_methods(monkeypatch):
    agent = GitHubAgent()
    agent._build_fallback_urls = Mock(return_value=[("direct", None), ("proxy", "http://proxy")])
    agent._fetch_single_url = AsyncMock(return_value=(False, [], RuntimeError("unavailable")))
    monkeypatch.setattr("app.agents.github_agent.settings.github_trending_max_attempts", 10)
    monkeypatch.setattr("app.agents.github_agent.asyncio.sleep", AsyncMock())

    result = asyncio.run(agent.fetch_trending_repos("daily"))

    assert result == []
    assert agent._fetch_single_url.await_count == 10
    attempted_urls = [call.args[0] for call in agent._fetch_single_url.await_args_list]
    assert attempted_urls == ["direct", "proxy"] * 5
    assert [call.kwargs["attempt_number"] for call in agent._fetch_single_url.await_args_list] == list(range(1, 11))


def test_trending_client_errors_switch_access_method_without_backoff(monkeypatch):
    request = httpx.Request("GET", "https://github.com/trending")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("forbidden", request=request, response=response)
    agent = GitHubAgent()
    agent._build_fallback_urls = Mock(return_value=[("direct", None), ("mirror", None)])
    agent._fetch_single_url = AsyncMock(return_value=(False, [], error))
    sleep = AsyncMock()
    monkeypatch.setattr("app.agents.github_agent.settings.github_trending_max_attempts", 2)
    monkeypatch.setattr("app.agents.github_agent.asyncio.sleep", sleep)

    result = asyncio.run(agent.fetch_trending_repos("daily"))

    assert result == []
    assert [call.args[0] for call in agent._fetch_single_url.await_args_list] == ["direct", "mirror"]
    sleep.assert_not_awaited()


def test_trending_stops_after_first_success(monkeypatch):
    agent = GitHubAgent()
    agent._build_fallback_urls = Mock(return_value=[("direct", None), ("proxy", "http://proxy")])
    agent._fetch_single_url = AsyncMock(
        side_effect=[
            (False, [], RuntimeError("direct unavailable")),
            (True, [{"full_name": "org/repo"}], None),
        ]
    )
    monkeypatch.setattr("app.agents.github_agent.asyncio.sleep", AsyncMock())

    result = asyncio.run(agent.fetch_trending_repos("weekly"))

    assert result == [{"full_name": "org/repo"}]
    assert agent._fetch_single_url.await_count == 2


def test_search_failure_preserves_qualified_trending_candidates():
    class FakeRepo:
        id = 91
        full_name = "org/trending"
        stargazers_count = 250
        forks_count = 20
        subscribers_count = 15
        open_issues_count = 12

    repo = FakeRepo()
    agent = GitHubAgent()
    agent.fetch_trending_repos = AsyncMock(
        return_value=[
            {
                "full_name": repo.full_name,
                "repo": repo,
                "recent_stars": 50,
                "recent_star_velocity": 50.0,
                "trending_rank": 1,
            }
        ]
    )
    agent.search_popular_active_candidates = AsyncMock(side_effect=RuntimeError("search unavailable"))
    agent.fetch_repo_details = AsyncMock(return_value={"readme_content": "readme", "topics": []})
    agent.is_ai_related = Mock(return_value=True)
    agent.fetch_recent_issue_comment_count = AsyncMock(return_value=8)
    agent.candidate_quality = Mock(
        return_value=("A", {"trending_momentum", "recent_conversation"}, ["agentic"])
    )
    candidate = github_item(repo.full_name, "A")
    agent.analyze_repo = AsyncMock(return_value=candidate)

    results = asyncio.run(agent.get_research_repos())

    assert results == [candidate]
    agent.search_popular_active_candidates.assert_awaited_once_with()


def test_trending_parser_retains_period_rank_velocity_and_request_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.agents.github_agent.settings.github_trending_attempt_timeout_seconds",
        120.0,
    )
    html = """
    <article class="Box-row">
      <h2 class="h3"><a href="/org/repo">org / repo</a></h2>
      <p class="col-9">Vision-language benchmark implementation</p>
      <span itemprop="programmingLanguage">Python</span>
      <span class="d-inline-block float-sm-right">700 stars this week</span>
    </article>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    class FakeClient:
        kwargs = None

        def __init__(self, **kwargs):
            FakeClient.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            return FakeResponse()

    monkeypatch.setattr("app.agents.github_agent.httpx.AsyncClient", FakeClient)
    agent = GitHubAgent()

    success, repos, error = asyncio.run(
        agent._fetch_single_url("https://github.com/trending", None, {}, "weekly", 1)
    )

    assert success is True and error is None
    assert FakeClient.kwargs["timeout"] == 120.0
    assert repos[0]["trending_rank"] == 1
    assert repos[0]["trending_period"] == "weekly"
    assert repos[0]["recent_stars"] == 700
    assert repos[0]["recent_star_period_days"] == 7
    assert repos[0]["recent_star_velocity"] == 100.0


def test_recent_issue_comments_are_capped_and_failures_are_unavailable(monkeypatch):
    class FakeRepo:
        full_name = "org/repo"

        def get_issues_comments(self, since):
            return range(150)

    agent = GitHubAgent()
    monkeypatch.setattr("app.agents.github_agent.settings.github_recent_comment_limit", 100)
    assert asyncio.run(agent.fetch_recent_issue_comment_count(FakeRepo())) == 100

    class FailingRepo(FakeRepo):
        def get_issues_comments(self, since):
            raise RuntimeError("API unavailable")

    assert asyncio.run(agent.fetch_recent_issue_comment_count(FailingRepo())) is None


def test_social_grades_have_no_total_star_floor():
    grade, evidence = github_social_grade(
        relevant=True,
        source_channel="trending",
        recent_stars=25,
        recent_issue_comments=7,
        forks=1,
        watchers=1,
        open_issues=1,
    )
    assert grade == "A"
    assert {"trending_momentum", "recent_conversation"} <= evidence

    fallback_grade, _ = github_social_grade(
        relevant=True,
        source_channel="search",
        recent_stars=0,
        recent_issue_comments=12,
        forks=100,
        watchers=50,
        open_issues=25,
    )
    assert fallback_grade == "B"

    unrelated_grade, _ = github_social_grade(
        relevant=False,
        source_channel="trending",
        recent_stars=10_000,
        recent_issue_comments=100,
        forks=10_000,
        watchers=10_000,
        open_issues=10_000,
    )
    assert unrelated_grade == "C"


def test_trending_with_enough_qualified_items_does_not_search(monkeypatch):
    class FakeRepo:
        def __init__(self, index):
            self.full_name = f"org/repo-{index}"

    agent = GitHubAgent()
    trending = [
        {
            "full_name": f"org/repo-{index}",
            "trending_rank": index + 1,
            "recent_star_velocity": 100 - index,
        }
        for index in range(10)
    ]
    graded = [
        (
            {**trending[index], "source_channel": "trending", "recent_issue_comments": 10, "stars": 1000},
            FakeRepo(index),
            {},
            "A",
            {"trending_momentum", "recent_conversation"},
            ["agentic"],
        )
        for index in range(10)
    ]
    agent.fetch_trending_repos = AsyncMock(return_value=trending)
    agent._grade_candidates = AsyncMock(return_value=graded)
    agent.search_popular_active_candidates = AsyncMock(return_value=[])
    agent.analyze_repo = AsyncMock(
        side_effect=lambda repo, details, stars_today, deep_analysis: github_item(repo.full_name, "A")
    )
    monkeypatch.setattr("app.agents.github_agent.settings.target_items", 10)
    monkeypatch.setattr("app.agents.github_agent.settings.github_candidate_limit", 24)

    results = asyncio.run(agent.get_research_repos())

    assert len(results) == 10
    agent.search_popular_active_candidates.assert_not_awaited()


def test_schema_and_config_social_defaults_are_backward_compatible():
    item = GitHubDigestItem(repo_name="org/repo", repo_url="https://github.com/org/repo", stars=1)
    assert item.source_channel == "legacy"
    assert item.trending_rank is None
    assert item.recent_issue_comments is None
    assert item.recent_stars == 0
    assert item.watchers == 0
    assert Settings.model_fields["github_trending_attempt_timeout_seconds"].default == 120.0
    assert Settings.model_fields["github_trending_max_attempts"].default == 10
    assert Settings.model_fields["github_recent_comment_limit"].default == 100


def test_recent_star_velocity_outranks_total_stars_and_comments_break_ties():
    fast = github_item("org/fast", "A")
    fast.source_channel = "trending"
    fast.recent_star_velocity = 120.0
    fast.recent_issue_comments = 6
    fast.stars = 600

    large = github_item("org/large", "A")
    large.source_channel = "trending"
    large.recent_star_velocity = 20.0
    large.recent_issue_comments = 100
    large.stars = 100_000

    selected, _ = select_research_items([large, fast], [], target_items=1, max_items=1)
    assert [item.repo_name for item in selected] == ["org/fast"]

    more_discussed = github_item("org/discussed", "A")
    more_discussed.source_channel = "trending"
    more_discussed.recent_star_velocity = 120.0
    more_discussed.recent_issue_comments = 20
    more_discussed.stars = 500

    selected, _ = select_research_items(
        [fast, more_discussed],
        [],
        target_items=1,
        max_items=1,
    )
    assert [item.repo_name for item in selected] == ["org/discussed"]


def test_readme_and_implementation_do_not_create_social_proof():
    rich_evidence = value_evidence(
        {"description": "A concrete vision-language benchmark implementation with reproducible experiments."},
        {
            "readme_content": "vision-language benchmark " * 30,
            "root_entries": ["src", "tests", "pyproject.toml"],
        },
    )
    assert quality_grade(relevant=True, evidence=rich_evidence) == "A"

    social_grade, _ = github_social_grade(
        relevant=True,
        source_channel="search",
        recent_stars=0,
        recent_issue_comments=0,
        forks=0,
        watchers=0,
        open_issues=0,
    )
    assert social_grade == "C"
