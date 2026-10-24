"""长图分段与拼接的测试

对应 add-longimage-and-publishers §4。分段的正确性判据是一个等式：
拼完的高度必须精确等于整页高度×缩放。差一像素说明某段偏移算错了，
表现为接缝或丢带 —— 这两种缺陷肉眼难辨，所以用等式卡而不是靠看。
"""

import pytest
from PIL import Image

from app.services.image_renderer import (
    CHROMIUM_MAX_TEXTURE_PX,
    LongImageRenderer,
    needs_segmentation,
    segment_plan,
    stitch_vertically,
)


def _solid(width: int, height: int, color: str) -> Image.Image:
    return Image.new("RGB", (width, height), color)


# --- 分段计划 -------------------------------------------------------------


def test_segments_cover_full_height_exactly():
    plan = segment_plan(total_css_height=20000, scale=2, max_device_height=15000)
    assert sum(seg.css_height for seg in plan) == 20000
    assert sum(seg.device_height for seg in plan) == 20000 * 2


def test_segments_are_contiguous_and_non_overlapping():
    plan = segment_plan(total_css_height=20000, scale=2, max_device_height=15000)
    for previous, current in zip(plan, plan[1:]):
        assert current.css_offset == previous.css_offset + previous.css_height


def test_tall_page_requires_at_least_three_segments():
    """三段以上才会同时暴露首段、中间段、末段的偏移错误。"""
    plan = segment_plan(total_css_height=30000, scale=2, max_device_height=15000)
    assert len(plan) >= 3


def test_no_segment_exceeds_the_device_limit():
    plan = segment_plan(total_css_height=30000, scale=2, max_device_height=15000)
    assert all(seg.device_height <= 15000 for seg in plan)


def test_short_page_is_a_single_segment():
    plan = segment_plan(total_css_height=3000, scale=2, max_device_height=15000)
    assert len(plan) == 1
    assert plan[0].css_offset == 0
    assert plan[0].css_height == 3000


def test_needs_segmentation_is_decided_in_device_pixels():
    """7000 CSS 像素本身不超限，乘 2× DPR 后超限 —— 判据必须在设备空间。"""
    assert needs_segmentation(7000, scale=2, max_device_height=13000) is True
    assert needs_segmentation(7000, scale=1, max_device_height=13000) is False


def test_segment_plan_rejects_nonpositive_height():
    with pytest.raises(ValueError):
        segment_plan(0, scale=2, max_device_height=15000)


def test_configured_limit_stays_below_chromium_texture_cap():
    """超过 16384 时 Chromium 静默截断，不报错。"""
    renderer = LongImageRenderer()
    assert renderer.max_device_height < CHROMIUM_MAX_TEXTURE_PX


# --- 拼接 -----------------------------------------------------------------


def test_stitched_height_equals_sum_of_segments():
    parts = [_solid(800, 500, "#FF0000"), _solid(800, 500, "#00FF00"), _solid(800, 300, "#0000FF")]
    stitched = stitch_vertically(parts)
    assert stitched.height == 1300
    assert stitched.width == 800


def test_stitched_height_equals_page_height_times_scale():
    """整条链路的核心等式。"""
    total_css_height, scale, limit = 24000, 2, 15000
    plan = segment_plan(total_css_height, scale, limit)
    parts = [_solid(1600, seg.device_height, "#FFFFFF") for seg in plan]
    assert stitch_vertically(parts).height == total_css_height * scale


def test_stitch_preserves_segment_order():
    """错序表现为内容跳跃，靠像素颜色卡住顺序。"""
    parts = [_solid(10, 10, "#FF0000"), _solid(10, 10, "#00FF00"), _solid(10, 10, "#0000FF")]
    stitched = stitch_vertically(parts)
    assert stitched.getpixel((5, 5)) == (255, 0, 0)
    assert stitched.getpixel((5, 15)) == (0, 255, 0)
    assert stitched.getpixel((5, 25)) == (0, 0, 255)


def test_single_image_is_returned_unchanged():
    single = _solid(800, 400, "#123456")
    assert stitch_vertically([single]) is single


def test_stitch_rejects_empty_input():
    with pytest.raises(ValueError):
        stitch_vertically([])


def test_mismatched_widths_pad_rather_than_crop():
    """宽度不一致应表现为右侧空白（可见）而不是内容被裁（不可见）。"""
    stitched = stitch_vertically([_solid(800, 10, "#FF0000"), _solid(600, 10, "#00FF00")])
    assert stitched.width == 800


# --- 确定性 ---------------------------------------------------------------


def test_same_page_height_yields_identical_plan():
    first = segment_plan(18000, scale=2, max_device_height=15000)
    second = segment_plan(18000, scale=2, max_device_height=15000)
    assert first == second


def test_same_input_yields_identical_pixel_dimensions():
    def render_dimensions() -> tuple[int, int]:
        plan = segment_plan(18000, scale=2, max_device_height=15000)
        parts = [_solid(1600, seg.device_height, "#FFFFFF") for seg in plan]
        stitched = stitch_vertically(parts)
        return stitched.width, stitched.height

    assert render_dimensions() == render_dimensions()


# --- 分段截图的调用形状 ---------------------------------------------------
#
# 这一组是回归测试，起因是端到端第一次真渲染时报
# "Clipped area is either empty or outside the resulting image"：
# clip 的坐标系是相对**截出来的那张图**，不是相对文档。只给 clip 时那张图只有
# 视口大小，于是第一段以外的每一段都落在图外。容器内实测：页高 10000、视口 1200，
# y=5000 裸 clip 失败，加 full_page=True 得到 (1600, 6000)。
# 用假 page 断言调用形状，是因为真浏览器不在单测环境里 —— 而这个 bug 恰好是
# "参数漏了一个"，不需要真浏览器也能钉住。


class _RecordingPage:
    """记录 screenshot 的调用参数。行为上只满足 render() 需要的那几个方法。"""

    def __init__(self, total_height: int) -> None:
        self.total_height = total_height
        self.calls: list[dict] = []

    def set_default_timeout(self, _ms): ...
    async def set_content(self, _html, **_kw): ...

    async def evaluate(self, script):
        return self.total_height if "scrollHeight" in script else None

    async def screenshot(self, **kwargs):
        self.calls.append(kwargs)
        if "path" in kwargs:
            _solid(10, 10, "#FFFFFF").save(kwargs["path"])
            return b""
        import io

        seg_height = int(kwargs["clip"]["height"])
        buffer = io.BytesIO()
        _solid(1600, seg_height * 2, "#FFFFFF").save(buffer, format="PNG")
        return buffer.getvalue()


class _StubBrowser:
    def __init__(self, page): self._page = page
    async def new_context(self, **_kw): return self
    async def new_page(self): return self._page
    async def close(self): ...


def _run_render(monkeypatch, tmp_path, total_height: int) -> _RecordingPage:
    import sys
    import types

    page = _RecordingPage(total_height)

    class _PW:
        def __init__(self): self.chromium = self
        async def launch(self, **_kw): return _StubBrowser(page)
        async def __aenter__(self): return self
        async def __aexit__(self, *_a): return False

    module = types.ModuleType("playwright.async_api")
    module.async_playwright = lambda: _PW()
    parent = types.ModuleType("playwright")
    parent.async_api = module
    monkeypatch.setitem(sys.modules, "playwright", parent)
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)

    import asyncio

    from app.services import image_renderer

    monkeypatch.setattr(image_renderer, "preflight", lambda *a, **k: None)
    renderer = image_renderer.LongImageRenderer()
    asyncio.run(renderer.render("<html></html>", tmp_path / "out.png"))
    return page


def test_segmented_capture_passes_full_page_alongside_clip(monkeypatch, tmp_path):
    """漏掉 full_page 时，第一段以外的每一段都会落在图外。"""
    page = _run_render(monkeypatch, tmp_path, total_height=20000)
    clipped = [call for call in page.calls if "clip" in call]
    assert len(clipped) > 1, "20000px 的页面必须分段，否则这条断言测不到东西"
    for call in clipped:
        assert call.get("full_page") is True


def test_clip_offsets_are_document_relative_and_contiguous(monkeypatch, tmp_path):
    """各段偏移必须首尾相接地覆盖整页 —— 有缝隙就是丢带。"""
    page = _run_render(monkeypatch, tmp_path, total_height=20000)
    clips = [call["clip"] for call in page.calls if "clip" in call]
    assert clips[0]["y"] == 0
    for previous, current in zip(clips, clips[1:]):
        assert current["y"] == previous["y"] + previous["height"]
    assert clips[-1]["y"] + clips[-1]["height"] == 20000


def test_single_segment_page_uses_full_page_without_clip(monkeypatch, tmp_path):
    """不需要分段时不要传 clip：多一个参数就多一处能算错的地方。"""
    page = _run_render(monkeypatch, tmp_path, total_height=1000)
    assert len(page.calls) == 1
    assert page.calls[0].get("full_page") is True
    assert "clip" not in page.calls[0]
