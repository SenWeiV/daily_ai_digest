"""Deterministic A/B/C selection across GitHub and arXiv content."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, TypeVar

from app.schemas import ArxivDigestItem, GitHubDigestItem


ResearchItem = TypeVar("ResearchItem", GitHubDigestItem, ArxivDigestItem)


def _item_grade(item: ResearchItem) -> str:
    return (getattr(item, "quality_grade", None) or "C").upper()


def _item_topics(item: ResearchItem) -> tuple[str, ...]:
    return tuple(getattr(item, "research_topics", None) or ())


def _item_time(item: ResearchItem) -> datetime:
    values = (
        getattr(item, "updated_at", None),
        getattr(item, "published_at", None),
        getattr(item, "created_at", None),
    )
    for value in values:
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.min


def _item_evidence_count(item: ResearchItem) -> int:
    return len(getattr(item, "quality_evidence", None) or ())


def _stable_key(item: ResearchItem) -> str:
    if isinstance(item, GitHubDigestItem):
        return f"github:{item.repo_url.rstrip('/').lower()}"
    return f"arxiv:{item.arxiv_id.lower()}"


def _rank_key(item: ResearchItem) -> tuple[int, int, datetime, int, str]:
    grade_rank = {"A": 2, "B": 1, "C": 0}.get(_item_grade(item), 0)
    momentum = getattr(item, "stars_today", 0) or getattr(item, "stars", 0) or 0
    return (grade_rank, _item_evidence_count(item), _item_time(item), int(momentum), _stable_key(item))


def _deduplicate(items: Iterable[ResearchItem]) -> list[ResearchItem]:
    best: dict[str, ResearchItem] = {}
    for item in items:
        key = _stable_key(item)
        current = best.get(key)
        if current is None or _rank_key(item) > _rank_key(current):
            best[key] = item
    return list(best.values())


def _normalize_github_url(value: str) -> str:
    return value.rstrip("/").removesuffix(".git").lower()


def _deduplicate_explicit_relations(items: list[ResearchItem]) -> list[ResearchItem]:
    """Keep the stronger entry for explicitly linked paper/repository pairs."""
    github_items = [item for item in items if isinstance(item, GitHubDigestItem)]
    arxiv_items = [item for item in items if isinstance(item, ArxivDigestItem)]
    github_by_url = {_normalize_github_url(item.repo_url): item for item in github_items}
    arxiv_by_id = {item.arxiv_id.lower(): item for item in arxiv_items}
    suppressed: set[str] = set()

    relations: dict[tuple[str, str], tuple[GitHubDigestItem, ArxivDigestItem]] = {}
    for paper in arxiv_items:
        for url in paper.github_urls:
            repo = github_by_url.get(_normalize_github_url(url))
            if repo:
                relations[(repo.repo_url.lower(), paper.arxiv_id.lower())] = (repo, paper)
    for repo in github_items:
        for arxiv_id in repo.related_arxiv_ids:
            paper = arxiv_by_id.get(arxiv_id.lower())
            if paper:
                relations[(repo.repo_url.lower(), paper.arxiv_id.lower())] = (repo, paper)

    for repo, paper in relations.values():
        if paper.arxiv_id not in repo.related_arxiv_ids:
            repo.related_arxiv_ids.append(paper.arxiv_id)
        if repo.repo_name not in paper.related_repo_names:
            paper.related_repo_names.append(repo.repo_name)

        # Grade, evidence, recency and momentum decide; the stable key makes ties deterministic.
        loser = paper if _rank_key(repo) >= _rank_key(paper) else repo
        suppressed.add(_stable_key(loser))

    return [item for item in items if _stable_key(item) not in suppressed]


def _coverage_order(items: list[ResearchItem]) -> list[ResearchItem]:
    """Prefer new source/topic coverage, then deterministic evidence/recency rank."""
    remaining = sorted(items, key=_rank_key, reverse=True)
    selected: list[ResearchItem] = []
    seen_sources: set[str] = set()
    seen_topics: set[str] = set()

    while remaining:
        def coverage_key(item: ResearchItem) -> tuple[int, int, tuple[int, int, datetime, int, str]]:
            source = "github" if isinstance(item, GitHubDigestItem) else "arxiv"
            new_source = int(source not in seen_sources)
            new_topics = len(set(_item_topics(item)) - seen_topics)
            return (new_source, new_topics, _rank_key(item))

        best = max(remaining, key=coverage_key)
        remaining.remove(best)
        selected.append(best)
        seen_sources.add("github" if isinstance(best, GitHubDigestItem) else "arxiv")
        seen_topics.update(_item_topics(best))

    return selected


def select_research_items(
    github_items: Iterable[GitHubDigestItem],
    arxiv_items: Iterable[ArxivDigestItem],
    *,
    target_items: int = 10,
    max_items: int = 24,
) -> tuple[list[GitHubDigestItem], list[ArxivDigestItem]]:
    """Select all A items up to max, then B items only to reach target."""
    if target_items < 0 or max_items <= 0 or target_items > max_items:
        raise ValueError("selection limits must satisfy 0 <= target_items <= max_items")

    combined = _deduplicate([*github_items, *arxiv_items])
    combined = _deduplicate_explicit_relations(combined)
    a_items = _coverage_order([item for item in combined if _item_grade(item) == "A"])
    b_items = _coverage_order([item for item in combined if _item_grade(item) == "B"])

    selected: list[ResearchItem] = a_items[:max_items]
    if len(selected) < target_items:
        selected.extend(b_items[: min(target_items - len(selected), max_items - len(selected))])

    github_selected = [item for item in selected if isinstance(item, GitHubDigestItem)]
    arxiv_selected = [item for item in selected if isinstance(item, ArxivDigestItem)]
    return github_selected, arxiv_selected
