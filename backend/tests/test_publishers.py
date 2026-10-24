"""平台文案的测试

对应 add-longimage-and-publishers §8。两个最容易在发布时才暴露的点：
X 的 CJK 按两个字符计（用 len() 会过本地校验、被平台拒），
以及编造的链接/数字必须让该平台失败而不是被悄悄改掉。
"""

import asyncio
import json

import pytest

from app.publishers.copy_generator import (
    build_copy_prompt,
    drafts_from_payload,
    generate_platform_copy,
)
from app.publishers.formatting import format_body
from app.publishers.styles import PLATFORM_STYLES, enabled_styles
from app.publishers.validation import (
    CopyDraft,
    Grounding,
    check_grounding,
    enforce_limits,
    fits_limit,
    truncate_weighted,
    validate_copy,
    weighted_length,
)

ITEMS = [
    {
        "repo_name": "acme/agent-kit",
        "repo_url": "https://github.com/acme/agent-kit",
        "summary": "一个多智能体编排框架",
        "stars": 4200,
        "forks": 310,
    },
    {
        "repo_name": "lab/spatial-nav",
        "repo_url": "https://github.com/lab/spatial-nav",
        "summary": "室内空间导航基线",
        "stars": 1800,
    },
]
GROUNDING = Grounding.from_items(ITEMS)


def _draft(platform, title="", body="正文", hashtags=()):
    return CopyDraft(platform=platform, title=title, body=body, hashtags=tuple(hashtags))


# --- X 的加权字数 ---------------------------------------------------------


def test_cjk_counts_as_two_for_x():
    assert weighted_length("中文", counts_cjk_as_two=True) == 4
    assert weighted_length("ab", counts_cjk_as_two=True) == 2


def test_len_would_pass_where_weighted_counting_fails():
    """这正是"过了本地校验、发帖被拒"的成因。"""
    text = "中" * 200
    assert len(text) <= 280
    assert fits_limit(text, 280, counts_cjk_as_two=True) is False


def test_other_platforms_count_plainly():
    assert weighted_length("中文", counts_cjk_as_two=False) == 2


def test_emoji_and_ascii_mix_counted():
    assert weighted_length("AI 智能", counts_cjk_as_two=True) == 3 + 4


def test_weighted_layout_preserves_complete_text_without_ellipsis():
    text = "中文标题需要被截断处理"
    for limit in range(2, 40):
        out = truncate_weighted(text, limit, counts_cjk_as_two=True)
        assert out == text
        assert "…" not in out
        assert "..." not in out


def test_x_body_over_limit_is_flagged():
    issues = validate_copy(_draft("x", body="中" * 200), PLATFORM_STYLES["x"], GROUNDING)
    assert any(i.field == "body" for i in issues)


def test_x_body_within_weighted_limit_passes():
    issues = validate_copy(_draft("x", body="a" * 270), PLATFORM_STYLES["x"], GROUNDING)
    assert issues == []


def test_x_thread_parts_are_validated_independently():
    draft = CopyDraft(
        platform="x",
        title="",
        body="first post\n\nsecond post",
        thread=("a" * 200, "b" * 200),
    )
    assert validate_copy(draft, PLATFORM_STYLES["x"], GROUNDING) == []


def test_x_thread_rejects_one_over_limit_part():
    draft = CopyDraft(
        platform="x",
        title="",
        body="thread",
        thread=("a" * 200, "中" * 141),
    )
    issues = validate_copy(draft, PLATFORM_STYLES["x"], GROUNDING)
    assert any("第 2 条" in issue.detail for issue in issues)


def test_x_payload_parses_ordered_thread():
    drafts = drafts_from_payload(
        {"x": {"title": "", "thread": ["first", "second"], "hashtags": []}},
        [PLATFORM_STYLES["x"]],
    )
    assert drafts["x"].thread == ("first", "second")
    assert drafts["x"].body == "first\n\nsecond"


def test_single_line_chinese_copy_is_split_into_paragraphs():
    text = "先给结论。这里是第一项。最后给行动建议。"
    assert format_body("xiaohongshu", text) == (
        "先给结论。\n\n这里是第一项。\n\n最后给行动建议。"
    )


def test_single_line_english_copy_is_split_into_paragraphs():
    text = "A clear hook. First practical point. Final question."
    assert format_body("reddit", text) == (
        "A clear hook.\n\nFirst practical point.\n\nFinal question."
    )


def test_payload_is_formatted_before_length_validation():
    drafts = drafts_from_payload(
        {
            "xiaohongshu": {
                "title": "今天值得看的AI项目",
                "body": "先给结论。第一项值得看。最后给建议。",
                "hashtags": ["#AI", "#Agent", "#开源"],
            }
        },
        [PLATFORM_STYLES["xiaohongshu"]],
    )
    assert "\n\n" in drafts["xiaohongshu"].body
    assert len(drafts["xiaohongshu"].title) <= 20
    assert len(drafts["xiaohongshu"].body) <= 1000


@pytest.mark.parametrize("marker", ["...", "…", "。。。"])
def test_copy_with_omission_marker_is_rejected(marker):
    issues = validate_copy(
        _draft("x", body=f"complete claim{marker}"), PLATFORM_STYLES["x"], GROUNDING
    )
    assert any("完整文本" in issue.detail for issue in issues)


# --- 各平台限制 -----------------------------------------------------------


def test_xiaohongshu_title_limit_enforced():
    issues = validate_copy(
        _draft("xiaohongshu", title="标" * 21, body="正文", hashtags=("#AI", "#Agent", "#开源")),
        PLATFORM_STYLES["xiaohongshu"],
        GROUNDING,
    )
    assert any(i.field == "title" for i in issues)


def test_xiaohongshu_tag_count_must_be_in_range():
    style = PLATFORM_STYLES["xiaohongshu"]
    too_few = validate_copy(_draft("xiaohongshu", title="标题", body="正文", hashtags=("#AI",)), style, GROUNDING)
    assert any(i.field == "hashtags" for i in too_few)
    ok = validate_copy(
        _draft("xiaohongshu", title="标题", body="正文", hashtags=("#AI", "#Agent", "#开源")),
        style,
        GROUNDING,
    )
    assert ok == []


def test_xiaohongshu_body_limit_is_one_thousand():
    issues = validate_copy(
        _draft("xiaohongshu", title="标题", body="字" * 1001, hashtags=("#a", "#b", "#c")),
        PLATFORM_STYLES["xiaohongshu"],
        GROUNDING,
    )
    assert any(i.field == "body" for i in issues)


def test_wechat_title_limit_is_sixty_four():
    issues = validate_copy(_draft("wechat", title="标" * 65, body="正文"), PLATFORM_STYLES["wechat"], GROUNDING)
    assert any(i.field == "title" for i in issues)


def test_instagram_caption_limit_is_2200():
    issues = validate_copy(
        _draft("instagram", body="a" * 2201, hashtags=("#a", "#b", "#c")),
        PLATFORM_STYLES["instagram"],
        GROUNDING,
    )
    assert any(i.field == "body" for i in issues)


def test_zhihu_and_reddit_reject_hashtags():
    for key in ("zhihu", "reddit", "wechat"):
        issues = validate_copy(_draft(key, title="标题", body="正文", hashtags=("#AI",)), PLATFORM_STYLES[key], GROUNDING)
        assert any(i.field == "hashtags" for i in issues), key


def test_hashtag_in_body_also_rejected_for_no_tag_platforms():
    issues = validate_copy(_draft("reddit", title="Title", body="Some text #ai"), PLATFORM_STYLES["reddit"], GROUNDING)
    assert any(i.field == "hashtags" for i in issues)


def test_reddit_declares_english_and_markdown_structure():
    style = PLATFORM_STYLES["reddit"]
    assert style.copy.language == "en"
    assert "Markdown" in style.copy.structure


def test_two_platforms_differ_in_structure_and_limit():
    a, b = PLATFORM_STYLES["x"], PLATFORM_STYLES["zhihu"]
    assert a.copy.structure != b.copy.structure
    assert a.copy.body_max_chars != b.copy.body_max_chars


# --- 接地校验 -------------------------------------------------------------


def test_fabricated_url_fails_validation():
    failures = check_grounding("看这里 https://github.com/fake/repo", GROUNDING)
    assert any(f.kind == "url" for f in failures)


def test_real_url_passes():
    assert check_grounding("见 https://github.com/acme/agent-kit", GROUNDING) == []


@pytest.mark.parametrize(
    "copy",
    [
        # 这三种是端到端里让小红书/微信/知乎同时失败的真实写法。旧正则只排除
        # ASCII 右括号与部分中文标点，把 `）：说明文字` 一起吞进 URL。
        "（https://github.com/acme/agent-kit）：低延迟智能体流水线",
        "项目地址：https://github.com/acme/agent-kit；建议收藏",
        "https://github.com/acme/agent-kit，然后按文档部署",
        # Markdown 链接的 ASCII 右括号是包裹符，不属于 URL。
        "[项目地址](https://github.com/acme/agent-kit)",
        # ASCII 句号与逗号同样是自然语言句尾，不是仓库名的一部分。
        "先看 https://github.com/acme/agent-kit, 再决定。",
    ],
)
def test_real_url_survives_chinese_and_markdown_wrappers(copy):
    assert check_grounding(copy, GROUNDING) == []


def test_balanced_parentheses_inside_url_are_preserved():
    """不能无脑 rstrip(')')：Wikipedia 等 URL 的路径本身允许配平括号。"""
    grounding = Grounding.from_items([
        {"repo_url": "https://en.wikipedia.org/wiki/Function_(computer_programming)"}
    ])
    copy = "见 https://en.wikipedia.org/wiki/Function_(computer_programming)。"
    assert check_grounding(copy, grounding) == []


def test_extra_wrapper_parenthesis_is_removed_but_balanced_one_is_kept():
    grounding = Grounding.from_items([
        {"repo_url": "https://en.wikipedia.org/wiki/Function_(computer_programming)"}
    ])
    copy = "[链接](https://en.wikipedia.org/wiki/Function_(computer_programming))"
    assert check_grounding(copy, grounding) == []


def test_query_fragment_and_percent_encoding_survive_extraction():
    url = "https://example.com/a%20b?q=1&r=2#part"
    grounding = Grounding.from_items([{"repo_url": url}])
    # URL 查询参数里的 1/2 是链接结构，不是文案声称的统计数字；这条测试只看 URL。
    assert check_grounding(f"详情：{url}。", grounding, check_numbers=False) == []


def test_cjk_wrapped_fabricated_url_still_fails_validation():
    """修的是误报，不能把真正的编造链接一起放过去。"""
    failures = check_grounding("（https://github.com/fake/repo）：并不存在", GROUNDING)
    assert [(failure.kind, failure.value) for failure in failures] == [
        ("url", "https://github.com/fake/repo")
    ]


def test_url_trailing_slash_still_matches():
    assert check_grounding("https://github.com/acme/agent-kit/", GROUNDING) == []


def test_fabricated_star_count_fails_validation():
    failures = check_grounding("已经 9999 stars", GROUNDING)
    assert any(f.kind == "number" for f in failures)


def test_real_star_count_passes():
    assert check_grounding("已经 4200 stars", GROUNDING) == []


def test_compact_star_notation_passes():
    """邮件里写 4.2K，文案引用同样的写法不该被判成编造。"""
    assert check_grounding("已经 4.2K stars", GROUNDING) == []


def test_small_numbers_are_not_treated_as_statistics():
    """日期、序号不做接地要求，否则每条文案都会被判失败。"""
    assert check_grounding("第 3 个项目，2026 年", GROUNDING) == []


def test_metric_stated_after_the_word_is_also_checked():
    """"stars: 9999" 和 "9999 stars" 是同一种编造。"""
    assert any(f.kind == "number" for f in check_grounding("stars: 9999", GROUNDING))


def test_suffixed_number_is_always_checked_even_without_a_metric_word():
    assert any(f.kind == "number" for f in check_grounding("已经 88.8K 了", GROUNDING))


def test_version_numbers_are_not_flagged():
    assert check_grounding("需要 Python 3.11 以上", GROUNDING) == []


def test_ungrounded_copy_fails_the_platform_rather_than_being_edited():
    issues = validate_copy(
        _draft("wechat", title="标题", body="见 https://github.com/fake/repo"),
        PLATFORM_STYLES["wechat"],
        GROUNDING,
    )
    grounding_issues = [i for i in issues if i.field == "grounding"]
    assert grounding_issues
    assert "不做静默修改" in grounding_issues[0].detail


# --- 超限处理 -------------------------------------------------------------


def test_enforce_limits_preserves_over_limit_copy_for_explicit_repair():
    draft = _draft("x", body="中" * 300)
    assert enforce_limits(draft, PLATFORM_STYLES["x"]) == draft


def test_enforce_limits_preserves_disallowed_tags_for_diagnosis():
    draft = _draft("zhihu", title="标题", body="正文", hashtags=("#AI",))
    assert enforce_limits(draft, PLATFORM_STYLES["zhihu"]) == draft


def test_enforce_limits_preserves_excess_tags_for_diagnosis():
    tags = tuple(f"#t{i}" for i in range(20))
    draft = _draft("xiaohongshu", title="标题", body="正文", hashtags=tags)
    assert enforce_limits(draft, PLATFORM_STYLES["xiaohongshu"]) == draft


# --- 一次调用产出全部平台 -------------------------------------------------


def _payload_for(keys, body="见 https://github.com/acme/agent-kit ，4200 stars"):
    out = {}
    for key in keys:
        style = PLATFORM_STYLES[key]
        tags = ["#AI", "#Agent", "#开源"] if style.copy.allow_hashtags else []
        out[key] = {"title": "标题" if style.copy.title_max_chars else "", "body": body, "hashtags": tags}
    return out


def _run(monkeypatch, payload, *, platforms=None, enabled=True, raiser=None):
    keys = platforms or ["xiaohongshu", "wechat", "x", "instagram", "zhihu", "reddit"]
    monkeypatch.setattr("app.publishers.copy_generator.settings.publishers_enabled", enabled)
    monkeypatch.setattr(
        "app.publishers.copy_generator.settings.publish_platforms", ",".join(keys)
    )
    calls = {"count": 0}

    async def _generate(prompt):
        calls["count"] += 1
        if raiser:
            raise raiser
        return json.dumps(payload, ensure_ascii=False)

    result = asyncio.run(generate_platform_copy(ITEMS, "2026-08-01", generate=_generate))
    return result, calls


def test_one_call_returns_copy_for_every_enabled_platform(monkeypatch):
    keys = ["xiaohongshu", "wechat", "x", "instagram", "zhihu", "reddit"]
    result, calls = _run(monkeypatch, _payload_for(keys, body="见 https://github.com/acme/agent-kit"))
    assert calls["count"] == 1
    assert set(result.accepted) == set(keys)


def test_failed_platform_gets_one_targeted_repair(monkeypatch):
    keys = ["x", "wechat"]
    monkeypatch.setattr("app.publishers.copy_generator.settings.publishers_enabled", True)
    monkeypatch.setattr(
        "app.publishers.copy_generator.settings.publish_platforms", ",".join(keys)
    )
    prompts = []
    first = _payload_for(keys, body="见 https://github.com/acme/agent-kit")
    first["x"]["body"] = "见 https://github.com/fake/repo"
    repaired = _payload_for(["x"], body="见 https://github.com/acme/agent-kit")

    async def _generate(prompt):
        prompts.append(prompt)
        payload = first if len(prompts) == 1 else repaired
        return json.dumps(payload, ensure_ascii=False)

    result = asyncio.run(
        generate_platform_copy(ITEMS, "2026-08-01", generate=_generate)
    )

    assert len(prompts) == 2
    assert set(result.accepted) == set(keys)
    assert result.failed == {}
    assert "### x（" in prompts[1]
    assert "### wechat（" not in prompts[1]
    assert "grounding" in prompts[1]


def test_disabled_platform_is_not_reported_as_failure(monkeypatch):
    result, _ = _run(monkeypatch, _payload_for(["x"], body="ok"), platforms=["x"])
    assert "reddit" in result.skipped
    assert "reddit" not in result.failed


def test_publishers_disabled_produces_nothing_and_no_failures(monkeypatch):
    result, calls = _run(monkeypatch, {}, enabled=False)
    assert calls["count"] == 0
    assert result.accepted == {}
    assert result.failed == {}


def test_fabricated_url_in_one_platform_fails_only_that_platform(monkeypatch):
    payload = _payload_for(["x", "wechat"], body="见 https://github.com/acme/agent-kit")
    payload["x"]["body"] = "见 https://github.com/fake/repo"
    result, _ = _run(monkeypatch, payload, platforms=["x", "wechat"])
    assert "x" in result.failed
    assert "wechat" in result.accepted


def test_over_limit_copy_is_rejected_without_silent_truncation(monkeypatch):
    payload = _payload_for(["x"], body="a" * 400)
    result, _ = _run(monkeypatch, payload, platforms=["x"])
    assert "x" in result.failed
    assert "x" not in result.accepted
    assert "x" not in result.truncated
    assert any(issue.field == "body" for issue in result.failed["x"])


def test_missing_platform_in_response_is_a_failure(monkeypatch):
    result, _ = _run(monkeypatch, {}, platforms=["x", "zhihu"])
    assert set(result.failed) == {"x", "zhihu"}


def test_generation_error_fails_every_platform_without_raising(monkeypatch):
    result, _ = _run(monkeypatch, {}, platforms=["x"], raiser=RuntimeError("provider down"))
    assert "x" in result.failed
    assert result.accepted == {}


def test_prompt_lists_only_the_days_links(monkeypatch):
    styles = enabled_styles(["x", "xiaohongshu"])
    prompt = build_copy_prompt(styles, ITEMS, "2026-08-01")
    assert "https://github.com/acme/agent-kit" in prompt
    assert "只能使用上面列出的链接" in prompt


def test_prompt_states_the_cjk_counting_rule():
    prompt = build_copy_prompt(enabled_styles(["x"]), ITEMS, "2026-08-01")
    assert "CJK 按两个字符计" in prompt


def test_prompt_tells_no_tag_platforms_to_return_empty_tags():
    prompt = build_copy_prompt(enabled_styles(["zhihu"]), ITEMS, "2026-08-01")
    assert "hashtags 必须是空数组" in prompt


def test_drafts_ignore_platforms_absent_from_the_payload():
    styles = enabled_styles(["x", "zhihu"])
    drafts = drafts_from_payload({"x": {"title": "", "body": "b", "hashtags": []}}, styles)
    assert set(drafts) == {"x"}
