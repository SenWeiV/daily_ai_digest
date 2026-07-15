"""Research topic matching and evidence checks for digest candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ResearchProfile:
    name: str
    domain_terms: tuple[str, ...]
    content_terms: tuple[str, ...]


RESEARCH_PROFILES: tuple[ResearchProfile, ...] = (
    ResearchProfile(
        "multimodal",
        (
            "multimodal", "mllm", "vlm", "vision-language", "vision language",
            "video-language", "video language", "audio-language", "audio language",
            "omnimodal", "any-to-any", "visual reasoning", "grounding",
            "spatial reasoning", "document understanding",
        ),
        (
            "model", "inference", "training", "benchmark", "evaluation", "dataset",
            "implementation", "demo", "paper", "research",
        ),
    ),
    ResearchProfile(
        "data-evaluation",
        (
            "evaluation", "eval", "benchmark", "leaderboard", "dataset",
            "data curation", "annotation", "synthetic data", "data quality",
            "contamination", "leakage", "robustness", "calibration", "hallucination",
            "factuality",
        ),
        (
            "llm", "language model", "multimodal", "agent", "machine learning",
            "deep learning",
        ),
    ),
    ResearchProfile(
        "agentic",
        (
            "agent", "agents", "agentic", "tool use", "computer use", "browser agent", "coding agent",
            "research agent", "workflow", "orchestration", "planning", "memory",
            "mcp", "multi-agent", "multi agent", "long-horizon", "trajectory",
            "observability",
        ),
        (
            "llm", "language model", "automation", "benchmark", "evaluation",
            "implementation", "framework", "workflow",
        ),
    ),
    ResearchProfile(
        "principles-methodology",
        (
            "methodology", "framework", "survey", "taxonomy", "analysis",
            "architecture", "training recipe", "evaluation protocol", "reproducibility",
            "ablation",
        ),
        (
            "llm", "language model", "multimodal", "agent", "machine learning",
            "deep learning",
        ),
    ),
)


def normalize_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def _contains_term(text: str, term: str) -> bool:
    if " " in term or "-" in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def matching_profiles(text: str) -> list[str]:
    """Return profiles where both domain and content signals are present."""
    normalized = normalize_text(text)
    matches: list[str] = []
    for profile in RESEARCH_PROFILES:
        has_domain = any(_contains_term(normalized, term) for term in profile.domain_terms)
        has_content = any(_contains_term(normalized, term) for term in profile.content_terms)
        if has_domain and has_content:
            matches.append(profile.name)
    return matches


def is_research_relevant(text: str) -> bool:
    return bool(matching_profiles(text))


def extract_explicit_arxiv_ids(text: str) -> list[str]:
    """Extract canonical arXiv IDs, retaining no version suffix."""
    matches = re.findall(r"arxiv\.org/(?:abs|pdf)/([a-zA-Z0-9.\-]+)", text or "", re.I)
    ids: list[str] = []
    for value in matches:
        normalized = re.sub(r"v\d+$", "", value)
        if normalized not in ids:
            ids.append(normalized)
    return ids


def extract_explicit_github_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text or "", re.I)
    result: list[str] = []
    for url in urls:
        clean = url.rstrip("/.,);]")
        if clean not in result:
            result.append(clean)
    return result


def value_evidence(repo_info: dict[str, Any], details: dict[str, Any] | None = None) -> set[str]:
    """Collect inspectable evidence that a new repository contains real work."""
    details = details or {}
    evidence: set[str] = set()
    description = str(repo_info.get("description") or "").strip()
    readme = str(details.get("readme_content") or "").strip()
    topics = repo_info.get("topics") or []
    code_files = details.get("code_files") or {}
    root_entries = [str(entry).lower() for entry in details.get("root_entries") or []]
    searchable = normalize_text(description, readme, " ".join(map(str, topics)), " ".join(root_entries))

    if len(description) >= 80:
        evidence.add("technical_description")
    if len(readme) >= 240 and not re.search(r"(coming soon|work in progress|placeholder)", readme, re.I):
        evidence.add("substantive_readme")
    if topics and any(is_research_relevant(str(topic)) for topic in topics):
        evidence.add("research_topics")
    implementation_entries = any(
        entry in {"src", "app", "lib", "package.json", "pyproject.toml", "setup.py", "cargo.toml"}
        or re.search(r"\.(py|js|ts|tsx|jsx|go|rs|java|cpp|cc)$", entry)
        for entry in root_entries
    )
    if code_files or implementation_entries:
        evidence.add("implementation")
    if re.search(r"(test|example|demo|benchmark|evaluation|dataset|experiment)", searchable, re.I):
        evidence.add("artifacts_or_experiments")
    if extract_explicit_arxiv_ids(searchable):
        evidence.add("paper_link")
    return evidence


def quality_grade(*, relevant: bool, evidence: Iterable[str], source: str = "github") -> str:
    evidence_set = set(evidence)
    if not relevant:
        return "C"
    if source == "arxiv":
        return "A" if {"method", "evaluation"}.issubset(evidence_set) else "B"
    substantive = "substantive_readme" in evidence_set
    concrete = bool({"implementation", "artifacts_or_experiments", "paper_link"} & evidence_set)
    reproducible = {"implementation", "artifacts_or_experiments"}.issubset(evidence_set)
    if (substantive and concrete) or reproducible:
        return "A"
    if evidence_set:
        return "B"
    return "C"
