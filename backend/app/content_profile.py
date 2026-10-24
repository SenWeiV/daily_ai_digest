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
    # --- 以下四个 profile 由 expand-research-directions 新增 ---
    # 领域词只收限定短语，不收 robot/3d/video/animation 这类单字宽词：
    # 两信号门只要求命中一个领域词，宽词配上近乎通用的内容词会放进几乎任何仓库。
    ResearchProfile(
        "physical-ai",
        (
            "physical ai", "embodied ai", "embodied intelligence", "embodied agent",
            "humanoid robot", "robot learning", "robot manipulation",
            "dexterous manipulation", "bimanual manipulation", "legged robot",
            "locomotion", "whole-body control", "vla", "vision-language-action",
            "robot foundation model", "sim-to-real", "sim2real", "robot simulation",
            "isaac lab", "gr00t", "world model", "lerobot", "openvla", "smolvla",
            "genesis physics",
        ),
        (
            "vla model", "robot policy", "imitation learning", "diffusion policy",
            "flow matching policy", "embodied benchmark", "robot dataset",
            "teleoperation", "action chunking", "transformer policy",
            "benchmark", "dataset", "implementation", "paper",
        ),
    ),
    ResearchProfile(
        "spatial-ai",
        (
            "spatial intelligence", "3d gaussian splatting", "3dgs", "gaussian splatting",
            "slam", "visual slam", "nerf", "neural radiance field",
            "novel view synthesis", "neural rendering", "3d reconstruction",
            "scene reconstruction", "feed-forward reconstruction", "4d reconstruction",
            "generative 3d", "3d scene generation",
        ),
        (
            "gaussian splat", "point cloud", "camera pose estimation", "monocular depth",
            "photogrammetry", "implicit representation", "multi-view stereo",
            "semantic 3d", "benchmark", "dataset", "implementation", "paper",
        ),
    ),
    ResearchProfile(
        "fullstack-skill-mcp",
        (
            "mcp server", "model context protocol", "mcp registry", "mcp client",
            "agent skill", "claude code skill", "skill.md",
            "gsap", "framer motion", "motion one", "anime.js", "lenis", "rive",
            "remotion", "scrolltrigger", "view transitions", "server components",
            "edge runtime",
        ),
        (
            "mcp integration", "tool calling", "web animation", "react animation",
            "spring animation", "keyframe animation", "component library",
            "design system", "monorepo", "api gateway", "orm",
            "implementation", "framework",
        ),
    ),
    ResearchProfile(
        "creative-marketing",
        (
            "video generation", "text-to-video", "image-to-video", "video diffusion",
            "wan video", "hunyuan video", "ltx video", "kling", "runway gen",
            "comfyui", "remotion", "manim", "motion canvas", "motion graphics",
            "ai marketing", "marketing automation", "social media automation",
            "generative engine optimization", "programmatic video",
        ),
        (
            "comfyui workflow", "video model", "caption generation", "content calendar",
            "ad generation", "render pipeline", "template",
            "implementation", "framework", "api",
        ),
    ),
)

# 领域词表禁止收录的单字宽词。每个词都覆盖 GitHub 上极大比例的仓库，
# 而两信号门只要求一个领域命中，因此宽词等于取消了领域约束。
BANNED_DOMAIN_TERMS: frozenset[str] = frozenset({
    "robot", "3d", "video", "animation", "marketing", "scene", "simulation",
    "control", "content", "seo", "api", "fullstack", "react", "nextjs", "vue",
    "tailwind", "node", "diffusion", "transformer",
})

# 唯一允许跨 profile 重复的领域词：remotion 既是 React 开发工具也是视频渲染工具。
DUPLICATE_DOMAIN_TERM_EXCEPTIONS: frozenset[str] = frozenset({"remotion"})


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
    """Grade arXiv items and retain the legacy GitHub fallback for old callers."""
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
    return "B" if evidence_set else "C"


def github_social_grade(
    *,
    relevant: bool,
    source_channel: str,
    recent_stars: int,
    recent_issue_comments: int | None,
    forks: int,
    watchers: int,
    open_issues: int,
    min_recent_comments: int = 5,
    activity_signal_threshold: int = 10,
) -> tuple[str, set[str]]:
    """Apply explicit social-proof gates without a fitted popularity score."""
    if not relevant:
        return "C", set()

    evidence: set[str] = set()
    if recent_stars > 0:
        evidence.add("trending_momentum")
    if recent_issue_comments is not None:
        evidence.add("comments_available")
        if recent_issue_comments >= min_recent_comments:
            evidence.add("recent_conversation")
    else:
        evidence.add("comments_unavailable")

    activity_signals = sum(
        value >= activity_signal_threshold
        for value in (forks, watchers, open_issues)
    )
    if activity_signals >= 2:
        evidence.add("repository_activity")

    direct_social_proof = "recent_conversation" in evidence
    fallback_social_proof = recent_issue_comments is None and "repository_activity" in evidence
    has_social_proof = direct_social_proof or fallback_social_proof

    if source_channel == "trending":
        if recent_stars > 0 and has_social_proof:
            return "A", evidence
        if recent_stars > 0 or has_social_proof:
            return "B", evidence
        return "C", evidence

    if source_channel == "search" and has_social_proof:
        return "B", evidence
    return "C", evidence
