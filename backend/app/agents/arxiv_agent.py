"""arXiv RSS/Atom discovery agent."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.content_profile import (
    extract_explicit_github_urls,
    is_research_relevant,
    matching_profiles,
    quality_grade,
)
from app.schemas import ArxivDigestItem

logger = logging.getLogger(__name__)


class ArxivAgent:
    """Retrieve bounded daily candidates from official arXiv feeds."""

    BASE_URL = "https://export.arxiv.org/rss/"

    def __init__(self) -> None:
        self.categories = tuple(settings.arxiv_categories_list)
        self.max_items = settings.arxiv_candidate_limit
        self.timeout = settings.arxiv_timeout_seconds

    @property
    def is_available(self) -> bool:
        return bool(self.categories)

    @staticmethod
    def normalize_id(value: str) -> str:
        value = value.strip()
        value = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", value, flags=re.I)
        value = re.sub(r"\.pdf$", "", value, flags=re.I)
        return re.sub(r"v\d+$", "", value)

    @staticmethod
    def _text(element: ET.Element | None) -> str:
        return "".join(element.itertext()).strip() if element is not None else ""

    def parse_feed(self, xml_text: str, category: str) -> list[ArxivDigestItem]:
        root = ET.fromstring(xml_text)
        items: list[ArxivDigestItem] = []
        entries = list(root.findall("./channel/item")) or list(root.findall("{*}entry"))
        for entry in entries:
            title = self._text(entry.find("title")) or self._text(entry.find("{*}title"))
            abstract = (
                self._text(entry.find("description"))
                or self._text(entry.find("summary"))
                or self._text(entry.find("{*}summary"))
            )
            raw_url = self._text(entry.find("link")) or self._text(entry.find("{*}id"))
            if not raw_url:
                for link in [*entry.findall("link"), *entry.findall("{*}link")]:
                    raw_url = link.attrib.get("href", "")
                    if raw_url:
                        break
            raw_id = raw_url or self._text(entry.find("guid"))
            version_match = re.search(r"(v\d+)(?:\.pdf)?$", raw_id, re.I)
            version = version_match.group(1) if version_match else None
            arxiv_id = self.normalize_id(raw_id)
            if not arxiv_id or not title:
                continue
            categories = [category]
            category_nodes = [*entry.findall("category"), *entry.findall("{*}category")]
            for category_node in category_nodes:
                category_text = category_node.attrib.get("term") or self._text(category_node)
                if category_text:
                    categories.extend(part.strip() for part in category_text.split(",") if part.strip())
            published = self._text(entry.find("pubDate")) or self._text(entry.find("{*}published"))
            updated = self._text(entry.find("{*}updated")) or published
            authors = [self._text(author) for author in entry.findall("author")]
            if not authors:
                authors = [self._text(author.find("{*}name")) for author in entry.findall("{*}author")]
            if not any(authors):
                creators = entry.findall("{http://purl.org/dc/elements/1.1/}creator")
                authors = [name.strip() for creator in creators for name in self._text(creator).split(",") if name.strip()]
            text = f"{title} {abstract}"
            relevant = is_research_relevant(text)
            evidence = {"method"} if re.search(r"method|approach|framework|architecture", text, re.I) else set()
            if re.search(r"evaluation|experiment|benchmark|results|dataset", text, re.I):
                evidence.add("evaluation")
            github_urls = extract_explicit_github_urls(text)
            item = ArxivDigestItem(
                arxiv_id=arxiv_id,
                title=re.sub(r"\s+", " ", title),
                abstract=re.sub(r"\s+", " ", abstract),
                authors=[author for author in authors if author],
                categories=sorted(set(categories)),
                published_at=published or None,
                updated_at=updated or None,
                version=version,
                arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
                github_urls=github_urls,
                research_topics=matching_profiles(text),
                quality_evidence=sorted(evidence),
                quality_grade=quality_grade(relevant=relevant, evidence=evidence, source="arxiv"),
                summary=re.sub(r"\s+", " ", abstract)[:800] or None,
            )
            items.append(item)
        return items

    @staticmethod
    def merge_items(items: list[ArxivDigestItem]) -> list[ArxivDigestItem]:
        merged: dict[str, ArxivDigestItem] = {}
        for item in items:
            current = merged.get(item.arxiv_id)
            if current is None:
                merged[item.arxiv_id] = item
                continue
            current.categories = sorted(set(current.categories + item.categories))
            current.github_urls = sorted(set(current.github_urls + item.github_urls))
            current.research_topics = sorted(set(current.research_topics + item.research_topics))
            current.quality_evidence = sorted(set(current.quality_evidence + item.quality_evidence))
            current.quality_grade = quality_grade(
                relevant=bool(current.research_topics),
                evidence=current.quality_evidence,
                source="arxiv",
            )
        return list(merged.values())

    async def fetch(self) -> list[ArxivDigestItem]:
        if not self.is_available:
            return []
        collected: list[ArxivDigestItem] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for category in self.categories:
                try:
                    response = await client.get(f"{self.BASE_URL}{category}")
                    response.raise_for_status()
                    collected.extend(self.parse_feed(response.text, category))
                except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                    logger.warning("arXiv feed failed [%s]: %s", category, exc)
        merged = self.merge_items(collected)
        grade_rank = {"A": 2, "B": 1, "C": 0}
        return sorted(
            merged,
            key=lambda item: (grade_rank.get(item.quality_grade, 0), item.updated_at or item.published_at or ""),
            reverse=True,
        )[: self.max_items]


arxiv_agent = ArxivAgent()
