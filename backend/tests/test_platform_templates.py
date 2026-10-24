"""平台风格、模板与画幅的测试

对应 add-longimage-and-publishers §5。这里最重要的两组断言：
画幅比例必须精确（不是近似），以及降级路径必须真的改变参数 ——
参数不变的重试只会把质检预算烧光后拿到同一个缺陷。
"""

from fractions import Fraction

import pytest

from app.publishers.layout import (
    TYPE_SCALE_STEPS,
    TypeScale,
    tightened_limit,
    truncate_to,
)
from app.publishers.styles import (
    FRAME_ASPECT_RATIOS,
    IMAGE_FRAMES,
    PLATFORM_STYLES,
    enabled_styles,
    platform_of_slug,
)
from app.publishers.templates import (
    CARD_ITEMS_PER_PAGE,
    build_page_specs,
    render_page_html,
)


def _items(count: int) -> list[dict]:
    return [
        {"repo_name": f"owner/proj-{i}", "summary": f"第 {i} 个项目的一句话说明", "repo_url": f"https://github.com/owner/proj-{i}"}
        for i in range(count)
    ]


# --- 风格数据是可检查的结构 -----------------------------------------------


def test_all_six_platforms_declared():
    assert set(PLATFORM_STYLES) == {"xiaohongshu", "wechat", "x", "instagram", "zhihu", "reddit"}


def test_style_is_structured_data_not_prompt_text():
    """风格必须是字段，运营改配色不该去改提示词。"""
    style = PLATFORM_STYLES["xiaohongshu"]
    assert style.visual.palette[0].startswith("#")
    assert style.copy.title_max_chars == 20
    assert style.copy.body_max_chars == 1000


def test_x_declares_cjk_counts_as_two():
    assert PLATFORM_STYLES["x"].copy.counts_cjk_as_two is True
    assert PLATFORM_STYLES["xiaohongshu"].copy.counts_cjk_as_two is False


def test_platforms_without_hashtags_declare_zero_range():
    for key in ("wechat", "zhihu", "reddit"):
        style = PLATFORM_STYLES[key]
        assert style.copy.allow_hashtags is False
        assert style.copy.hashtag_max == 0


def test_text_only_platforms_have_no_image_slugs():
    for key in ("wechat", "zhihu", "reddit"):
        assert PLATFORM_STYLES[key].image_slugs == ()


def test_enabled_styles_follows_config_order_and_ignores_unknown():
    styles = enabled_styles(["x", "nonexistent", "xiaohongshu"])
    assert [s.key for s in styles] == ["x", "xiaohongshu"]


def test_slug_maps_back_to_its_platform():
    assert platform_of_slug("xhs-content-2") == "xiaohongshu"
    assert platform_of_slug("xhs-content-4") == "xiaohongshu"
    assert platform_of_slug("ig-square") == "instagram"
    assert platform_of_slug("unknown") is None


# --- 画幅比例必须精确 -----------------------------------------------------


def test_every_frame_matches_its_declared_ratio_exactly():
    """精确到分数而不是近似：近似的代价是平台替我们裁边。"""
    for slug, (num, den) in FRAME_ASPECT_RATIOS.items():
        w, h = IMAGE_FRAMES[slug]
        assert Fraction(w, h) == Fraction(num, den), slug


def test_xiaohongshu_frames_are_exactly_three_by_four():
    for slug in ("xhs-cover", "xhs-content-1", "xhs-content-2", "xhs-content-3"):
        w, h = IMAGE_FRAMES[slug]
        assert Fraction(w, h) == Fraction(3, 4), slug


def test_x_card_is_exactly_sixteen_by_nine():
    w, h = IMAGE_FRAMES["x-card"]
    assert Fraction(w, h) == Fraction(16, 9)


def test_instagram_square_is_exactly_one_by_one():
    w, h = IMAGE_FRAMES["ig-square"]
    assert Fraction(w, h) == Fraction(1, 1)


def test_every_slug_has_a_frame():
    declared = {slug for style in PLATFORM_STYLES.values() for slug in style.image_slugs}
    assert declared == set(IMAGE_FRAMES)


def test_stored_dimensions_are_logical_times_dpr():
    from app.config import Settings

    dpr = Settings(_env_file=None).render_device_scale_factor
    for slug, (w, h) in IMAGE_FRAMES.items():
        assert (w * dpr, h * dpr) == (w * 2, h * 2), slug


# --- 排版而非裁剪 ---------------------------------------------------------


def test_pages_are_laid_out_at_full_frame_size():
    """每页都是完整画幅，不是从长图里抠出来的一刀。"""
    specs = build_page_specs(PLATFORM_STYLES["xiaohongshu"], _items(9), "2026-08-01")
    for spec in specs:
        assert (spec.width, spec.height) == IMAGE_FRAMES[spec.slug]


def test_more_items_than_pages_are_paginated_without_dropping_items():
    specs = build_page_specs(PLATFORM_STYLES["xiaohongshu"], _items(20), "2026-08-01")
    content = [s for s in specs if s.kind == "cards"]
    names = [item.name for s in content for item in s.items]
    assert names[0].startswith("owner/proj-0")
    assert len(names) == 20
    assert len(content) == 20 // CARD_ITEMS_PER_PAGE + 1


def test_fewer_items_omits_unused_pages_rather_than_blanking_them():
    """空白页会被质检判成"文字缺失"，白烧一轮预算。"""
    specs = build_page_specs(PLATFORM_STYLES["xiaohongshu"], _items(2), "2026-08-01")
    content = [s for s in specs if s.kind == "cards"]
    assert len(content) == 1
    assert all(s.items for s in content)


def test_no_page_is_emitted_with_empty_items_for_a_cards_layout():
    specs = build_page_specs(PLATFORM_STYLES["xiaohongshu"], _items(4), "2026-08-01")
    for spec in specs:
        if spec.kind == "cards":
            assert len(spec.items) >= 1


def test_text_only_platform_yields_no_pages():
    assert build_page_specs(PLATFORM_STYLES["zhihu"], _items(5), "2026-08-01") == []


def test_multipage_set_shares_palette_and_scale():
    """四张图要读起来像一个帖子。"""
    style = PLATFORM_STYLES["xiaohongshu"]
    specs = build_page_specs(style, _items(9), "2026-08-01")
    html = [render_page_html(s, style, "sans-serif") for s in specs]
    accent = style.visual.palette[0]
    assert all(accent in page for page in html)
    assert len({s.scale.step for s in specs}) == 1


def test_copy_and_images_draw_from_the_same_items_in_order():
    items = _items(6)
    specs = build_page_specs(PLATFORM_STYLES["xiaohongshu"], items, "2026-08-01")
    rendered = [it.name for s in specs if s.kind == "cards" for it in s.items]
    source = [it["repo_name"] for it in items]
    assert rendered == source[: len(rendered)]


def test_rendered_html_escapes_item_text():
    style = PLATFORM_STYLES["x"]
    specs = build_page_specs(style, [{"repo_name": "a<script>x</script>", "summary": "s & t"}], "2026-08-01")
    html = render_page_html(specs[0], style, "sans-serif")
    assert "<script>" not in html
    assert "&amp;" in html


def test_rendered_html_declares_exact_frame_size():
    style = PLATFORM_STYLES["instagram"]
    spec = build_page_specs(style, _items(3), "2026-08-01")[0]
    html = render_page_html(spec, style, "sans-serif")
    assert "width:1080px" in html.replace(" ", "")
    assert "height:1080px" in html.replace(" ", "")


# --- 截断与字号降级 -------------------------------------------------------


def test_layout_preserves_complete_text_instead_of_omitting_content():
    text = "这是一段很长的中文标题需要被截断处理"
    for limit in range(1, 40):
        assert truncate_to(text, limit) == text
        assert "…" not in truncate_to(text, limit)
        assert "..." not in truncate_to(text, limit)


def test_short_text_is_untouched():
    assert truncate_to("短标题", 20) == "短标题"


def test_layout_never_adds_an_ellipsis_marker():
    text = "一二三四五六七八九十"
    assert truncate_to(text, 6) == text
    assert "…" not in truncate_to(text, 6)
    assert "..." not in truncate_to(text, 6)


def test_type_scale_reduction_actually_changes_the_size():
    base = TypeScale()
    reduced = base.reduced()
    assert reduced.factor < base.factor
    assert reduced.px(100) < base.px(100)


def test_type_scale_steps_are_strictly_decreasing():
    assert list(TYPE_SCALE_STEPS) == sorted(TYPE_SCALE_STEPS, reverse=True)
    assert len(set(TYPE_SCALE_STEPS)) == len(TYPE_SCALE_STEPS)


def test_exhausted_type_scale_raises_instead_of_silently_repeating():
    """静默返回自己会让重试拿到和上次完全相同的参数。"""
    scale = TypeScale(len(TYPE_SCALE_STEPS) - 1)
    assert scale.can_reduce is False
    with pytest.raises(ValueError):
        scale.reduced()


def test_tightened_limit_is_strictly_decreasing_per_attempt():
    limits = [tightened_limit(60, attempt) for attempt in range(4)]
    assert limits == sorted(limits, reverse=True)
    assert len(set(limits)) == len(limits)


def test_tightened_limit_never_reaches_zero():
    assert tightened_limit(20, 50) >= 4
