"""expand-research-directions 的 profile 词表与选择行为测试

覆盖 expanded-research-profiles、research-content-discovery（cs.RO 与窄查询）、
digest-quality-selection（超上限时保留主题广度）三个能力。
"""

from app.agents.github_agent import GitHubAgent
from app.config import Settings
from app.content_profile import (
    BANNED_DOMAIN_TERMS,
    DUPLICATE_DOMAIN_TERM_EXCEPTIONS,
    RESEARCH_PROFILES,
    matching_profiles,
    quality_grade,
)
from app.schemas import GitHubDigestItem
from app.services.content_selector import select_research_items

ADDED_PROFILES = {"physical-ai", "spatial-ai", "fullstack-skill-mcp", "creative-marketing"}


def _profile(name: str):
    return next(p for p in RESEARCH_PROFILES if p.name == name)


# --- 词表结构约束 ---------------------------------------------------------

def test_all_four_profiles_are_registered():
    names = {p.name for p in RESEARCH_PROFILES}
    assert ADDED_PROFILES <= names
    # 原有四个不能被替换掉
    assert {"multimodal", "data-evaluation", "agentic", "principles-methodology"} <= names


def test_domain_terms_are_unique_across_profiles():
    """一个领域词落在两个 profile 会虚增 research_topics，让 _coverage_order 误判覆盖面。"""
    seen: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for profile in RESEARCH_PROFILES:
        for term in profile.domain_terms:
            if term in seen and term not in DUPLICATE_DOMAIN_TERM_EXCEPTIONS:
                collisions.append((term, seen[term], profile.name))
            seen.setdefault(term, profile.name)
    assert collisions == []


def test_remotion_is_the_only_permitted_duplicate():
    owners = [p.name for p in RESEARCH_PROFILES if "remotion" in p.domain_terms]
    assert sorted(owners) == ["creative-marketing", "fullstack-skill-mcp"]
    assert DUPLICATE_DOMAIN_TERM_EXCEPTIONS == frozenset({"remotion"})


def test_no_banned_single_word_appears_in_any_domain_vocabulary():
    offenders = [
        (profile.name, term)
        for profile in RESEARCH_PROFILES
        for term in profile.domain_terms
        if term in BANNED_DOMAIN_TERMS
    ]
    assert offenders == []


def test_sora_is_absent_from_creative_vocabulary():
    # API 于 2026-09 关闭，留着只会退化成噪声
    assert "sora" not in _profile("creative-marketing").domain_terms


# --- 正向匹配（元数据取自真实仓库） ---------------------------------------

def test_lerobot_matches_physical_ai():
    text = (
        "huggingface/lerobot — LeRobot: Making AI for Robotics more accessible with "
        "end-to-end learning. State-of-the-art imitation learning and reinforcement "
        "learning approaches, pretrained models and datasets for real-world robotics."
    )
    matches = matching_profiles(text)
    assert "physical-ai" in matches


def test_gaussian_splatting_repo_matches_spatial_ai():
    text = (
        "graphdeco-inria/gaussian-splatting — Original reference implementation of "
        "3D Gaussian Splatting for Real-Time Radiance Field Rendering. Includes the "
        "optimizer, the rasterizer and a dataset of scenes with camera pose estimation."
    )
    assert "spatial-ai" in matching_profiles(text)


def test_mcp_server_collection_matches_fullstack_profile():
    text = (
        "modelcontextprotocol/servers — Model Context Protocol Servers. A collection of "
        "reference MCP server implementations demonstrating tool calling for filesystem, "
        "git and database access."
    )
    assert "fullstack-skill-mcp" in matching_profiles(text)


def test_open_weight_video_model_matches_creative_marketing():
    text = (
        "Wan-Video/Wan2.2 — Wan: Open and Advanced Large-Scale Video Generative Models. "
        "Text-to-video and image-to-video model weights with an inference implementation."
    )
    assert "creative-marketing" in matching_profiles(text)


# --- 负向匹配 -------------------------------------------------------------

def test_arduino_hobby_robot_arm_matches_no_added_profile():
    text = (
        "A 6-axis robot arm built with an Arduino Uno and hobby servos. "
        "3D printable STL files and a simple control sketch included."
    )
    assert not (set(matching_profiles(text)) & ADDED_PROFILES)


def test_vr_headset_ui_toolkit_matches_no_added_profile():
    text = (
        "A UI toolkit for AR/VR headsets. Ready-made panels, buttons and 3d layout "
        "components for building immersive interfaces in Unity."
    )
    assert not (set(matching_profiles(text)) & ADDED_PROFILES)


def test_nextjs_tailwind_starter_matches_no_added_profile():
    text = (
        "A Next.js 15 starter template with Tailwind CSS, TypeScript, ESLint and a "
        "ready-to-deploy api route. Batteries-included fullstack boilerplate."
    )
    assert not (set(matching_profiles(text)) & ADDED_PROFILES)


def test_html5_video_player_matches_no_added_profile():
    text = (
        "A lightweight HTML5 video player component with custom controls, subtitles "
        "and a simple playback api. Framework agnostic implementation."
    )
    assert not (set(matching_profiles(text)) & ADDED_PROFILES)


# --- 冲突判定 -------------------------------------------------------------

def test_world_model_with_robotics_signal_is_physical_ai_not_spatial():
    text = (
        "A world model trained for robot policy learning, evaluated on an embodied "
        "benchmark with a released robot dataset."
    )
    matches = matching_profiles(text)
    assert "physical-ai" in matches
    assert "spatial-ai" not in matches


def test_spatial_reasoning_with_benchmark_stays_multimodal():
    text = (
        "A benchmark measuring spatial reasoning in vision language models across "
        "held-out evaluation scenes."
    )
    matches = matching_profiles(text)
    assert "multimodal" in matches
    assert "spatial-ai" not in matches


def test_bare_mcp_stays_agentic():
    text = "An llm agent framework with mcp support and an automation workflow runner."
    matches = matching_profiles(text)
    assert "agentic" in matches
    assert "fullstack-skill-mcp" not in matches


def test_video_generation_is_creative_not_multimodal():
    text = "A video generation model with a text-to-video inference implementation."
    matches = matching_profiles(text)
    assert "creative-marketing" in matches
    assert "multimodal" not in matches


# --- 发现层配置 -----------------------------------------------------------

def test_arxiv_default_categories_include_robotics(monkeypatch):
    monkeypatch.delenv("ARXIV_CATEGORIES", raising=False)
    settings = Settings(_env_file=None)
    assert set(settings.arxiv_categories_list) == {
        "cs.AI", "cs.CL", "cs.CV", "cs.LG", "cs.IR", "cs.RO",
    }


def test_compose_default_matches_application_default(monkeypatch):
    import pathlib
    import re

    monkeypatch.delenv("ARXIV_CATEGORIES", raising=False)
    settings = Settings(_env_file=None)
    compose = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"
    found = re.search(r"ARXIV_CATEGORIES=\$\{ARXIV_CATEGORIES:-([^}]+)\}", compose.read_text())
    assert found, "docker-compose.yml must pass ARXIV_CATEGORIES with a default"
    assert found.group(1) == settings.arxiv_categories


def test_fallback_queries_stay_narrow():
    """每条查询至少两个词，且不能是单个宽词构成。"""
    for query in GitHubAgent.DEFAULT_SEARCH_QUERIES:
        tokens = [t for t in query.replace('"', " ").split() if t]
        assert len(tokens) >= 2 or query.startswith("topic:"), query
        bare = [t for t in tokens if t.lower() in BANNED_DOMAIN_TERMS]
        assert len(bare) < len(tokens), f"query is only broad words: {query}"


# --- 选择行为 -------------------------------------------------------------

def _repo(index: int, topics: tuple[str, ...], *, stars: int = 100) -> GitHubDigestItem:
    return GitHubDigestItem(
        repo_name=f"org/repo{index}",
        repo_url=f"https://github.com/org/repo{index}",
        stars=stars,
        trending_period="weekly",
        quality_grade="A",
        research_topics=list(topics),
        source_channel="trending",
        recent_stars=10,
        recent_issue_comments=8,
    )


def test_thin_topics_survive_when_one_topic_exceeds_the_ceiling():
    crowded = [_repo(i, ("physical-ai",), stars=1000 - i) for i in range(25)]
    thin = [
        _repo(100 + i, (topic,), stars=1)
        for i, topic in enumerate(
            ["spatial-ai", "fullstack-skill-mcp", "creative-marketing", "agentic", "multimodal"]
        )
    ]

    github_selected, _ = select_research_items(crowded + thin, [], target_items=10, max_items=24)
    selected_topics = {t for item in github_selected for t in item.research_topics}

    assert len(github_selected) == 24
    for topic in ["spatial-ai", "fullstack-skill-mcp", "creative-marketing", "agentic", "multimodal"]:
        assert topic in selected_topics, f"thin topic dropped: {topic}"


def test_trim_is_inert_below_the_ceiling():
    items = [_repo(i, ("physical-ai",), stars=500 - i) for i in range(11)]
    items.append(_repo(99, ("spatial-ai",), stars=1))

    github_selected, _ = select_research_items(items, [], target_items=10, max_items=24)
    assert len(github_selected) == 12


def test_over_ceiling_selection_is_reproducible():
    items = [_repo(i, ("physical-ai",), stars=1000 - i) for i in range(20)] + [
        _repo(50 + i, ("spatial-ai",), stars=200 - i) for i in range(10)
    ]

    first, _ = select_research_items(items, [], target_items=10, max_items=24)
    second, _ = select_research_items(list(items), [], target_items=10, max_items=24)
    assert [i.repo_url for i in first] == [i.repo_url for i in second]


def test_multi_topic_item_does_not_outrank_on_topic_count_alone():
    """两条证据等同的 A 项，主题数量不应改变它们的相对次序。"""
    single = _repo(1, ("physical-ai",), stars=500)
    multi = _repo(2, ("physical-ai", "spatial-ai", "creative-marketing"), stars=500)

    from app.services.content_selector import _rank_key

    assert _rank_key(single)[:-1] == _rank_key(multi)[:-1]


def test_added_profile_candidate_with_no_evidence_is_graded_c():
    assert quality_grade(relevant=True, evidence=set(), source="github") == "C"
    assert quality_grade(relevant=False, evidence={"implementation"}, source="github") == "C"


# --- 决策模型（System One）方向 ---------------------------------------------

def test_jev_alternative_repo_matches_decision_model():
    text = (
        "OpenJev — an open-weight System One decision model. Returns typed choices, "
        "scores and probabilities in a single pass for routing and classification."
    )
    assert "decision-model" in matching_profiles(text)


def test_decision_model_paper_matches_without_brand_names():
    text = (
        "We train a non-generative decision model that answers structured decision "
        "queries with calibrated confidence, and evaluate latency against an LLM baseline."
    )
    assert "decision-model" in matching_profiles(text)


def test_type_safe_library_is_not_a_decision_model():
    text = (
        "A typesafe ORM for TypeScript with a schema-first api and zero-cost "
        "inference of query result types."
    )
    assert "decision-model" not in matching_profiles(text)


# --- 物理 AI 重点：世界模型 -------------------------------------------------

def test_world_model_gets_its_focus_tag_inside_physical_ai():
    text = (
        "An action-conditioned video world model for robot planning, released with "
        "a robot dataset and an evaluation benchmark."
    )
    matches = matching_profiles(text)
    assert "physical-ai" in matches
    assert "world-model" in matches


def test_plain_robot_learning_has_no_world_model_tag():
    matches = matching_profiles(text := "Robot learning with a diffusion policy and a released robot dataset.")
    assert "physical-ai" in matches, text
    assert "world-model" not in matches


def test_world_model_ranks_first_within_the_same_grade():
    others = [_repo(i, ("agentic",), stars=10_000 - i) for i in range(5)]
    world = _repo(50, ("physical-ai", "world-model"), stars=1)

    github_selected, _ = select_research_items(others + [world], [], target_items=10, max_items=24)

    assert github_selected[0].repo_name == world.repo_name


def test_world_model_focus_never_outranks_a_better_grade():
    from app.services.content_selector import _rank_key

    world_b = _repo(1, ("physical-ai", "world-model"))
    world_b.quality_grade = "B"
    agent_a = _repo(2, ("agentic",))
    assert _rank_key(agent_a) > _rank_key(world_b)
