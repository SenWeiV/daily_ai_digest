"""生图层的测试

对应 add-longimage-and-publishers §6。这里最容易写错的断言是像素约束：
直觉上 provider 只有上限，实际上 Lite 的下限是硬的，而三个画幅全在下限
以下。所以"按想要的尺寸请求"这条最自然的实现路径必须被测试挡住。
"""

import asyncio
import base64

import pytest

from app.config import Settings
from app.model_roles import Capability, RoleCapabilityError, require_capability, text_role
from app.publishers.styles import IMAGE_FRAMES, PLATFORM_STYLES
from app.services.image_generation import (
    MAX_SIDE,
    PIXEL_CEILING,
    PIXEL_FLOOR,
    GenerationSize,
    GenerationUnavailable,
    aspect_preserved,
    assert_downscale_only,
    build_background_prompt,
    build_request_payload,
    prompt_mentions_only_digest_subjects,
    resolve_backgrounds,
    select_generation_size,
    settings as image_settings,
    supports_multipage_series,
    within_run_cap,
)


def _composited(slug: str, dpr: int = 2) -> tuple[int, int]:
    w, h = IMAGE_FRAMES[slug]
    return w * dpr, h * dpr


# --- 像素下限 -------------------------------------------------------------


def test_every_logical_frame_is_below_the_pixel_floor():
    """这是整节的前提：直接按逻辑尺寸请求一定被拒。"""
    for slug, (w, h) in IMAGE_FRAMES.items():
        assert w * h < PIXEL_FLOOR, slug


def test_selected_size_always_clears_the_floor():
    for slug in IMAGE_FRAMES:
        size = select_generation_size(*_composited(slug))
        assert size.pixels >= PIXEL_FLOOR, slug


def test_selected_size_clears_the_floor_even_for_logical_sizes():
    for slug, (w, h) in IMAGE_FRAMES.items():
        assert select_generation_size(w, h).pixels >= PIXEL_FLOOR, slug


def test_selected_size_stays_within_the_ceiling():
    for slug in IMAGE_FRAMES:
        size = select_generation_size(*_composited(slug))
        assert size.pixels <= PIXEL_CEILING
        assert max(size.width, size.height) <= MAX_SIDE


def test_selected_size_is_the_smallest_that_works():
    """多余像素最终都会被缩掉，还要多付时间与钱。"""
    w, h = _composited("ig-square")
    size = select_generation_size(w, h)
    # 缩到刚好低于下限就不该再满足约束
    smaller = GenerationSize(size.width - 64, size.height - 64)
    assert smaller.pixels < PIXEL_FLOOR or smaller.width < w


def test_selected_size_preserves_the_frame_ratio():
    for slug in IMAGE_FRAMES:
        w, h = _composited(slug)
        assert aspect_preserved(select_generation_size(w, h), w, h), slug


def test_impossible_frame_raises_rather_than_returning_a_bad_size():
    with pytest.raises(GenerationUnavailable):
        select_generation_size(20000, 20000)


def test_nonpositive_target_rejected():
    with pytest.raises(ValueError):
        select_generation_size(0, 100)


# --- 只缩不放 -------------------------------------------------------------


def test_generated_size_is_never_smaller_than_the_frame():
    for slug in IMAGE_FRAMES:
        w, h = _composited(slug)
        size = select_generation_size(w, h)
        assert size.width >= w and size.height >= h
        assert_downscale_only(size, w, h)


def test_upscaling_raises():
    """放大的模糊与渲染缺陷无法区分，只能走兜底背景。"""
    with pytest.raises(GenerationUnavailable):
        assert_downscale_only(GenerationSize(1024, 1024), 2484, 3312)


# --- 水印 -----------------------------------------------------------------


def test_watermark_field_is_always_present_in_the_payload():
    """缺字段就等于交付带"AI生成"角标的图。"""
    payload = build_request_payload("p", GenerationSize(2048, 2048))
    assert "watermark" in payload


def test_watermark_defaults_to_false_in_the_payload(monkeypatch):
    monkeypatch.setattr("app.services.image_generation.settings.image_gen_watermark", False)
    assert build_request_payload("p", GenerationSize(2048, 2048))["watermark"] is False


def test_watermark_can_be_deliberately_enabled(monkeypatch):
    """默认关不等于不能开：运营要溯源标记时不该改代码。"""
    monkeypatch.setattr("app.services.image_generation.settings.image_gen_watermark", True)
    assert build_request_payload("p", GenerationSize(2048, 2048))["watermark"] is True


def test_settings_default_watermark_is_disabled():
    assert Settings(_env_file=None).image_gen_watermark is False


# --- 组图 -----------------------------------------------------------------


def test_sequential_generation_requested_for_multipage_platform():
    payload = build_request_payload("p", GenerationSize(2048, 2048), max_images=4, sequential=True)
    assert payload["sequential_image_generation"] == "auto"
    assert payload["sequential_image_generation_options"]["max_images"] == 4


def test_single_image_disables_sequential_explicitly():
    payload = build_request_payload("p", GenerationSize(2048, 2048))
    assert payload["sequential_image_generation"] == "disabled"


def test_payload_pins_the_dated_lite_model():
    """Pro 不支持组图，滚动别名会静默改风格与成本。"""
    model = build_request_payload("p", GenerationSize(2048, 2048))["model"]
    assert model == "doubao-seedream-5-0-260128"
    assert "pro" not in model


# --- 提示词 ---------------------------------------------------------------


def _prompt(platform: str, topics: list[str], label: str) -> str:
    return build_background_prompt(PLATFORM_STYLES[platform], topics, label)


def test_prompts_differ_across_days():
    a = _prompt("xiaohongshu", ["具身智能"], "2026-08-01")
    b = _prompt("xiaohongshu", ["空间智能"], "2026-08-02")
    assert a != b


def test_prompts_differ_across_platforms():
    a = _prompt("xiaohongshu", ["具身智能"], "2026-08-01")
    b = _prompt("x", ["具身智能"], "2026-08-01")
    assert a != b


def test_prompt_carries_the_platform_palette():
    prompt = _prompt("x", ["具身智能"], "2026-08-01")
    for color in PLATFORM_STYLES["x"].visual.palette:
        assert color in prompt


def test_prompt_forbids_text_in_the_generated_pixels():
    """94% 的中文可用率对一个仓库名来说等于错字。"""
    prompt = _prompt("instagram", ["spatial AI"], "2026-08-01")
    assert "不要出现任何文字" in prompt


def test_prompt_forbids_third_party_logos():
    prompt = _prompt("instagram", ["spatial AI"], "2026-08-01")
    assert "logo" in prompt


def test_prompt_asks_for_quiet_text_regions():
    """背景太吵会挂在可读性检查上，白烧一次重试。"""
    prompt = _prompt("xiaohongshu", ["具身智能"], "2026-08-01")
    assert "视觉安静" in prompt


def test_prompt_only_names_subjects_present_in_the_digest():
    topics = ["具身智能", "空间智能"]
    prompt = _prompt("xiaohongshu", topics, "2026-08-01")
    assert prompt_mentions_only_digest_subjects(prompt, topics)
    assert prompt_mentions_only_digest_subjects(prompt, ["量子计算"]) is False


def test_prompt_without_topics_still_builds():
    assert _prompt("x", [], "2026-08-01")


# --- 每轮上限与角色隔离 ---------------------------------------------------


def test_run_cap_blocks_further_generation(monkeypatch):
    monkeypatch.setattr("app.services.image_generation.settings.image_gen_max_per_run", 5)
    assert within_run_cap(4, 1) is True
    assert within_run_cap(5, 1) is False
    assert within_run_cap(0, 6) is False


def test_generation_role_cannot_be_the_text_role(monkeypatch):
    monkeypatch.setattr("app.model_roles.settings.text_api_key", "text-key")
    with pytest.raises(RoleCapabilityError):
        require_capability(text_role(), Capability.IMAGE_GEN)


def test_client_is_unavailable_when_generation_is_disabled(monkeypatch):
    from app.services.image_generation import SeedreamClient

    monkeypatch.setattr("app.services.image_generation.settings.image_gen_enabled", False)
    assert SeedreamClient().is_available is False


# --- 兜底背景 -------------------------------------------------------------


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def _isolated_background_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.image_generation.settings.image_background_cache_dir",
        str(tmp_path / "backgrounds"),
    )


class _StubClient:
    """替身生图客户端。available/失败/返回张数都可控。"""

    def __init__(self, *, available=True, images=None, error=None, model="doubao-seedream-5-0-260128"):
        self._available = available
        self._images = images if images is not None else [_PNG_BYTES]
        self._error = error
        self.calls = 0

        class _Role:
            pass

        self.role = _Role()
        self.role.model = model

    @property
    def is_available(self):
        return self._available

    async def generate(self, prompt, size, *, max_images=1, sequential=False):
        self.calls += 1
        if self._error:
            raise self._error
        return list(self._images)


def _resolve(style_key, page_count, **kwargs):
    return asyncio.run(
        resolve_backgrounds(
            PLATFORM_STYLES[style_key],
            ["具身智能"],
            "2026-08-01",
            page_count,
            **kwargs,
        )
    )


def test_disabled_generator_yields_fallback_for_every_page():
    backgrounds, produced = _resolve("xiaohongshu", 4, client=_StubClient(available=False))
    assert produced == 0
    assert len(backgrounds) == 4
    assert all(bg.is_fallback for bg in backgrounds)
    assert all(bg.reason for bg in backgrounds)


def test_failing_generator_yields_fallback_rather_than_raising():
    client = _StubClient(error=GenerationUnavailable("boom"))
    backgrounds, produced = _resolve("x", 1, client=client)
    assert produced == 0
    assert backgrounds[0].is_fallback
    assert "生图失败" in backgrounds[0].reason


def test_timeout_is_also_absorbed_into_fallback():
    client = _StubClient(error=TimeoutError("slow"))
    backgrounds, _ = _resolve("x", 1, client=client)
    assert backgrounds[0].is_fallback


def test_run_cap_forces_fallback_instead_of_more_generation(monkeypatch):
    monkeypatch.setattr("app.services.image_generation.settings.image_gen_max_per_run", 5)
    client = _StubClient()
    backgrounds, produced = _resolve("xiaohongshu", 4, already_generated=3, client=client)
    assert produced == 0
    assert client.calls == 0
    assert all(bg.is_fallback for bg in backgrounds)
    assert "上限" in backgrounds[0].reason


def test_model_without_series_support_falls_back_for_multipage():
    """Pro 不支持组图；四张不相干的图比四张统一的兜底更糟。"""
    client = _StubClient(model="doubao-seedream-5-0-pro-260628")
    backgrounds, produced = _resolve("xiaohongshu", 4, client=client)
    assert produced == 0
    assert client.calls == 0
    assert "组图" in backgrounds[0].reason


def test_single_page_still_works_on_a_non_series_model():
    client = _StubClient(model="doubao-seedream-5-0-pro-260628")
    backgrounds, produced = _resolve("x", 1, client=client)
    assert produced == 1
    assert backgrounds[0].generated is True


def test_successful_generation_returns_data_urls():
    backgrounds, produced = _resolve("x", 1, client=_StubClient())
    assert produced == 1
    assert backgrounds[0].data_url.startswith("data:image/png;base64,")


def test_short_return_pads_with_fallback_not_duplicates():
    """复用同一张会让"组图"退化成重复图。"""
    client = _StubClient(images=[_PNG_BYTES, _PNG_BYTES])
    backgrounds, produced = _resolve("xiaohongshu", 4, client=client)
    assert produced == 2
    assert [bg.is_fallback for bg in backgrounds] == [False, False, True, True]


def test_series_support_detection():
    assert supports_multipage_series("doubao-seedream-5-0-260128") is True
    assert supports_multipage_series("doubao-seedream-5-0-pro-260628") is False


def test_second_run_uses_cached_background_without_provider_call():
    first = _StubClient()
    backgrounds, produced = _resolve("x", 1, client=first)
    assert produced == 1
    assert first.calls == 1

    second = _StubClient(available=False)
    cached, produced = _resolve("x", 1, client=second)
    assert produced == 0
    assert second.calls == 0
    assert cached[0].data_url == backgrounds[0].data_url
    assert cached[0].reason == "固定背景缓存命中"


def test_cache_hit_does_not_consume_generation_cap(monkeypatch):
    monkeypatch.setattr("app.services.image_generation.settings.image_gen_max_per_run", 1)
    first = _StubClient()
    _resolve("x", 1, client=first)

    second = _StubClient(available=False)
    cached, produced = _resolve("x", 1, already_generated=1, client=second)
    assert produced == 0
    assert second.calls == 0
    assert cached[0].is_fallback is False


def test_corrupt_cache_entry_is_regenerated():
    first = _StubClient()
    _resolve("x", 1, client=first)

    cache_files = list(first_cache_files())
    assert len(cache_files) == 1
    cache_files[0].write_bytes(b"not-an-image")

    second = _StubClient()
    backgrounds, produced = _resolve("x", 1, client=second)
    assert produced == 1
    assert second.calls == 1
    assert backgrounds[0].data_url.startswith("data:image/png;base64,")


def test_cache_version_explicitly_invalidates_background(monkeypatch):
    first = _StubClient()
    _resolve("x", 1, client=first)

    monkeypatch.setattr(
        "app.services.image_generation.settings.image_background_cache_version", "2"
    )
    second = _StubClient(available=False)
    backgrounds, produced = _resolve("x", 1, client=second)
    assert produced == 0
    assert second.calls == 0
    assert backgrounds[0].is_fallback
    assert "缓存未命中" in backgrounds[0].reason


def first_cache_files():
    from pathlib import Path

    return Path(image_settings.image_background_cache_dir).rglob("*.img")
