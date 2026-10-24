"""视觉质检与准出闸门的测试

对应 add-longimage-and-publishers §7。这里的断言方向是刻意不对称的：
判错成失败只花一次重试，判错成通过则把豆腐块发出去。所以每一条
"不确定"的路径都必须被断言为失败，而不是通过。

§7.12 是这一节的重点：用刻意做坏的输入去打这道闸门。只被正确图片喂过的
质检等于没测过。
"""

import asyncio
import io

import pytest
from PIL import Image

from app.publishers.layout import TYPE_SCALE_STEPS, TypeScale
from app.services.qa_gate import (
    Correction,
    next_correction,
    run_gate,
    truncation_limit,
)
from app.services.visual_qa import (
    CORRECTION_FOR,
    Defect,
    InspectionPlan,
    VisionUnavailable,
    build_inspection_messages,
    build_inspection_messages_for_images,
    downscale_for_inspection,
    parse_verdict,
    plan_inspection,
    prepare_inspection_images,
    respects_resolution_floor,
    split_for_inspection,
)


def _png(width: int, height: int, color="#FFFFFF") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(width: int, height: int, color="#FFFFFF") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _verdict_json(passed: bool, *defects: str) -> str:
    entries = ", ".join(f'{{"category": "{d}", "location": "标题右侧"}}' for d in defects)
    return f'{{"pass": {str(passed).lower()}, "defects": [{entries}]}}'


# --- 结论解析：不确定必须算失败 -------------------------------------------


def test_clean_verdict_passes():
    verdict = parse_verdict(_verdict_json(True))
    assert verdict.passed is True
    assert verdict.defects == ()


def test_tofu_verdict_fails_and_names_the_category():
    verdict = parse_verdict(_verdict_json(False, "missing_glyph"))
    assert verdict.passed is False
    assert Defect.MISSING_GLYPH in verdict.categories


def test_clipped_text_verdict_fails():
    assert parse_verdict(_verdict_json(False, "clipped_at_edge")).passed is False


def test_unparseable_verdict_counts_as_failure():
    """绝不当成通过。"""
    for text in ("完全不是 JSON", "", "   ", "{不合法", "[]"):
        assert parse_verdict(text).passed is False, text


def test_verdict_missing_pass_field_fails():
    assert parse_verdict('{"defects": []}').passed is False


def test_unknown_defect_category_fails_rather_than_being_ignored():
    """忽略无法识别的类别等于把真实缺陷降级成通过。"""
    assert parse_verdict('{"pass": false, "defects": ["something_new"]}').passed is False


def test_self_contradictory_verdict_fails():
    """同时说通过又列出缺陷，按失败处理。"""
    assert parse_verdict(_verdict_json(True, "overflow")).passed is False


def test_verdict_in_a_code_fence_is_parsed():
    fenced = "```json\n" + _verdict_json(False, "overflow") + "\n```"
    assert parse_verdict(fenced).passed is False


def test_verdict_records_defect_location():
    verdict = parse_verdict(_verdict_json(False, "overflow"))
    assert verdict.defects[0].location


def test_all_six_defect_categories_are_checked():
    assert {d.value for d in Defect} == {
        "missing_glyph",
        "clipped_at_edge",
        "overflow",
        "overlap",
        "illegible",
        "missing_text",
    }


def test_every_defect_has_a_correction_action():
    """没有对应动作的缺陷会导致重试原地重放。"""
    assert set(CORRECTION_FOR) == set(Defect)


# --- 送检副本：分段而不是缩到读不出字 -------------------------------------


def test_small_image_is_inspected_at_full_resolution():
    plan = plan_inspection(1200, 1600, byte_size=1_000_000, max_bytes=10_000_000)
    assert plan.scale == 1.0
    assert plan.is_segmented is False


def test_oversized_image_is_downscaled_when_the_floor_allows():
    plan = plan_inspection(4000, 6000, byte_size=40_000_000, max_bytes=10_000_000, min_dimension=900)
    assert plan.scale < 1.0
    assert plan.is_segmented is False
    assert respects_resolution_floor(plan, 4000, 6000, min_dimension=900)


def test_image_too_large_to_fit_above_the_floor_is_segmented_not_shrunk():
    """读不出字的检查会报假通过 —— 这是本设计里最坏的结果。"""
    plan = plan_inspection(1200, 40000, byte_size=900_000_000, max_bytes=1_000_000, min_dimension=900)
    assert plan.is_segmented is True
    assert respects_resolution_floor(plan, 1200, 40000, min_dimension=900)


def test_segmented_plan_never_goes_below_the_floor():
    plan = plan_inspection(1000, 30000, byte_size=500_000_000, max_bytes=2_000_000, min_dimension=900)
    assert int(1000 * plan.scale) >= 900


def test_resolution_floor_check_rejects_a_too_small_plan():
    assert respects_resolution_floor(InspectionPlan(scale=0.1, segments=1), 4000, 6000, min_dimension=900) is False


def test_plan_rejects_nonpositive_dimensions():
    with pytest.raises(ValueError):
        plan_inspection(0, 100, byte_size=10)


def test_downscale_touches_only_the_inspection_copy():
    """交付图保持全分辨率。"""
    original = _png(2000, 2000)
    shrunk = downscale_for_inspection(original, InspectionPlan(scale=0.5, segments=1))
    assert Image.open(io.BytesIO(shrunk)).width == 1000
    assert Image.open(io.BytesIO(original)).width == 2000


def test_full_scale_plan_returns_the_original_bytes():
    original = _png(800, 800)
    assert downscale_for_inspection(original, InspectionPlan(scale=1.0, segments=1)) is original


def test_tall_low_byte_image_is_segmented_for_legibility():
    """4MB 以下不代表可读；纵横比 10:1 的长图仍必须分段。"""
    plan = plan_inspection(100, 1000, byte_size=2_000, max_bytes=10_000_000)
    assert plan.scale == 1.0
    assert plan.segments == 4


def test_prepare_inspection_images_applies_the_plan_not_just_tests_it(monkeypatch):
    """回归：旧代码有 plan/downscale 单测，但 inspect() 从未调用那些函数。"""
    monkeypatch.setattr(
        "app.services.visual_qa.settings.qa_max_request_bytes", 10 * 1024 * 1024
    )
    plan, parts = prepare_inspection_images(_png(100, 1000))
    assert plan.segments == 4
    assert len(parts) == 4
    with Image.open(io.BytesIO(parts[0])) as first:
        assert first.size == (100, 250)


def test_split_segments_are_contiguous_and_reconstruct_the_original():
    image = Image.new("RGB", (12, 101))
    for y in range(image.height):
        for x in range(image.width):
            image.putpixel((x, y), (y, y, y))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    parts = split_for_inspection(buffer.getvalue(), 4)
    rows = []
    for part in parts:
        with Image.open(io.BytesIO(part)) as segment:
            rows.extend(segment.getpixel((0, y))[0] for y in range(segment.height))
    assert rows == list(range(101))


# --- 请求形状 -------------------------------------------------------------


def test_image_is_submitted_as_a_base64_data_url():
    """K3 明确不接受公网 HTTP URL。"""
    messages = build_inspection_messages(_png(10, 10), ["标题"])
    image_part = messages[1]["content"][0]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_jpeg_delivery_bytes_are_declared_as_jpeg_not_png():
    messages = build_inspection_messages(_jpeg(10, 10), ["标题"])
    image_part = messages[1]["content"][0]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_all_long_image_segments_are_in_one_request():
    parts = [_png(10, 20, "#FF0000"), _png(10, 20, "#00FF00")]
    messages = build_inspection_messages_for_images(parts, ["标题", "正文"])
    content = messages[1]["content"]
    images = [part for part in content if part["type"] == "image_url"]
    text = next(part["text"] for part in content if part["type"] == "text")
    assert len(images) == 2
    assert "从上到下" in text
    assert "标题" in text and "正文" in text


def test_content_is_a_real_typed_parts_array_not_a_string():
    messages = build_inspection_messages(_png(10, 10), ["标题"])
    assert isinstance(messages[1]["content"], list)
    assert {part["type"] for part in messages[1]["content"]} == {"image_url", "text"}


def test_expected_texts_are_listed_for_presence_checking():
    messages = build_inspection_messages(_png(10, 10), ["owner/repo", "2026-08-01"])
    text_part = next(p for p in messages[1]["content"] if p["type"] == "text")
    assert "owner/repo" in text_part["text"]
    assert "2026-08-01" in text_part["text"]


def test_prompt_enumerates_the_six_checks():
    messages = build_inspection_messages(_png(10, 10), [])
    system = messages[0]["content"]
    for category in Defect:
        assert category.value in system


# --- 定向修正：每次重试参数必须不同 ---------------------------------------


def test_font_defect_switches_to_a_fallback_font():
    advanced = next_correction(Correction(), (Defect.MISSING_GLYPH,))
    assert advanced.use_fallback_font is True


def test_overflow_tightens_truncation():
    advanced = next_correction(Correction(), (Defect.OVERFLOW,))
    assert advanced.truncation_attempt == 1
    assert truncation_limit(60, advanced) < 60


def test_overlap_reduces_the_type_scale():
    advanced = next_correction(Correction(), (Defect.OVERLAP,))
    assert advanced.type_scale.step == 1


def test_each_retry_changes_at_least_one_parameter():
    current = Correction()
    seen = {current.signature()}
    for _ in range(3):
        current = next_correction(current, (Defect.OVERFLOW,))
        assert current is not None
        assert current.signature() not in seen
        seen.add(current.signature())


def test_no_actionable_defect_stops_retrying():
    """报了失败但没有可识别类别时，瞎试只会烧预算。"""
    assert next_correction(Correction(), ()) is None


def test_exhausted_corrections_stop_rather_than_repeat():
    current = Correction(
        use_fallback_font=True,
        truncation_attempt=0,
        type_scale=TypeScale(len(TYPE_SCALE_STEPS) - 1),
    )
    assert next_correction(current, (Defect.MISSING_GLYPH,)) is None


def test_content_reduction_is_the_last_resort():
    """砍内容是信息损失，排在字号降级之后。"""
    first = next_correction(Correction(), (Defect.ILLEGIBLE,))
    assert first.content_reduction == 0
    assert first.type_scale.step == 1


# --- 闸门循环 -------------------------------------------------------------


def _gate(verdicts, *, max_attempts=3, render=None):
    calls = {"renders": [], "inspections": 0}

    async def _render(correction):
        calls["renders"].append(correction.signature())
        if render is not None:
            return render(correction)
        return _png(100, 100)

    async def _inspect(image):
        index = calls["inspections"]
        calls["inspections"] += 1
        outcome = verdicts[min(index, len(verdicts) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = asyncio.run(run_gate("xhs-cover", _render, _inspect, max_attempts=max_attempts))
    return result, calls


def test_clean_image_passes_on_the_first_attempt():
    result, calls = _gate([parse_verdict(_verdict_json(True))])
    assert result.passed is True
    assert result.attempts == 1
    assert result.image is not None
    assert calls["inspections"] == 1


def test_failing_image_retries_with_changed_parameters_and_passes():
    result, calls = _gate(
        [parse_verdict(_verdict_json(False, "overflow")), parse_verdict(_verdict_json(True))]
    )
    assert result.passed is True
    assert result.attempts == 2
    assert calls["renders"][0] != calls["renders"][1]


def test_exhausted_attempts_withhold_and_name_the_image_and_defect():
    result, _ = _gate([parse_verdict(_verdict_json(False, "overflow"))], max_attempts=3)
    assert result.passed is False
    assert result.withheld is True
    assert result.slug == "xhs-cover"
    assert Defect.OVERFLOW in result.defect_categories


def test_withheld_image_carries_no_placeholder_substitute():
    """占位图会被读者当成今天的成品。"""
    result, _ = _gate([parse_verdict(_verdict_json(False, "missing_glyph"))], max_attempts=2)
    assert result.image is None


def test_unparseable_verdict_is_treated_as_a_failing_attempt():
    result, _ = _gate([parse_verdict("noise")], max_attempts=2)
    assert result.passed is False


def test_vision_unavailable_marks_nothing_as_passing():
    result, calls = _gate([VisionUnavailable("moonshot down")])
    assert result.passed is False
    assert result.image is None
    assert "不可达" in result.withheld_reason
    # 不可达时不该继续重试：重试打的是同一个不可达的服务
    assert calls["inspections"] == 1


def test_render_failure_is_reported_not_swallowed():
    def _boom(correction):
        raise RuntimeError("chromium crashed")

    result, _ = _gate([parse_verdict(_verdict_json(True))], render=_boom)
    assert result.passed is False
    assert "渲染失败" in result.withheld_reason


def test_no_actionable_defect_stops_the_loop_early():
    result, calls = _gate([parse_verdict('{"pass": false, "defects": []}')], max_attempts=3)
    assert result.passed is False
    assert calls["inspections"] == 1
    assert "相同参数" in result.withheld_reason


# --- §7.12 刻意做坏的输入 -------------------------------------------------


def test_gate_catches_a_missing_font_condition():
    """字体被移除时闸门必须拦住，而不是把豆腐块放行。"""
    result, _ = _gate([parse_verdict(_verdict_json(False, "missing_glyph"))], max_attempts=1)
    assert result.passed is False
    assert Defect.MISSING_GLYPH in result.defect_categories


def test_gate_catches_an_overflowing_title():
    from app.publishers.styles import PLATFORM_STYLES
    from app.publishers.templates import build_page_specs

    long_title = "超" * 400
    specs = build_page_specs(
        PLATFORM_STYLES["xiaohongshu"],
        [{"repo_name": long_title, "summary": long_title}],
        "2026-08-01",
    )
    cards = [s for s in specs if s.kind == "cards"]
    # 排版层保留完整文本；真正的溢出由视觉闸门拦截并通过字号/分页修正。
    assert all(item.name == long_title for s in cards for item in s.items)
    assert all("…" not in item.name for s in cards for item in s.items)

    result, _ = _gate([parse_verdict(_verdict_json(False, "overflow"))], max_attempts=1)
    assert result.passed is False


def test_font_check_failure_prevents_rendering_entirely():
    from app.services.font_check import FontReport, FontUnavailableError, verify_fonts_or_raise

    with pytest.raises(FontUnavailableError):
        verify_fonts_or_raise(FontReport((), ("Noto Color Emoji",), fontconfig_available=True))
