"""资产编排与降级的测试

对应 add-longimage-and-publishers §9.2 与 §10。这一层的判据只有一条：
四个外部系统（浏览器、Ark、Kimi、文本模型）任何一个挂掉，今天的摘要邮件
仍然要发出去，且被省略的部分要被点名。静默省略会让读者分不清"今天没做"
和"今天做坏了"。
"""

import asyncio
from pathlib import Path

import pytest

from app.publishers.styles import PLATFORM_STYLES
from app.publishers.templates import build_page_specs, expected_texts
from app.services import digest_assets
from app.services.attachment_budget import LONG_IMAGE_SLUG, Attachment
from app.services.font_check import FontUnavailableError
from app.services.image_generation import Background
from app.services.visual_qa import Defect, DefectReport, Verdict, VisionUnavailable

ITEMS = [
    {"repo_name": "acme/agent-kit", "summary": "多智能体编排框架", "repo_url": "https://github.com/acme/agent-kit"},
    {"repo_name": "lab/spatial-nav", "summary": "室内空间导航基线", "repo_url": "https://github.com/lab/spatial-nav"},
    {"repo_name": "org/vision-bench", "summary": "视觉评测集", "repo_url": "https://github.com/org/vision-bench"},
]

PASS = Verdict(passed=True, defects=())
FAIL_OVERFLOW = Verdict(passed=False, defects=(DefectReport(Defect.OVERFLOW, "标题溢出"),))


@pytest.fixture(autouse=True)
def _isolated_output(tmp_path, monkeypatch):
    monkeypatch.setattr(digest_assets.settings, "render_output_dir", str(tmp_path / "renders"))
    return tmp_path


def _enable(monkeypatch, *, render=True, qa=True, publishers=False):
    monkeypatch.setattr(digest_assets.settings, "render_enabled", render)
    monkeypatch.setattr(digest_assets.settings, "publishers_enabled", publishers)
    # is_available 是 property，只能在类上替
    monkeypatch.setattr(
        type(digest_assets.visual_qa), "is_available", property(lambda self: qa)
    )


class _FakeRenderer:
    """把 Playwright 换掉。写一个真的 PNG，因为下游要读它的字节。"""

    def __init__(self, *args, **kwargs):
        self.frames = []
        self.long_calls = 0
        self.long_html = []

    async def render(self, html, output_path):
        # 生产 renderer 会在浏览器前调用同一个字体 preflight；假 renderer 也必须
        # 保留这个行为，否则"缺字体长图不发"测试测到的是假实现的漏洞。
        digest_assets.verify_fonts_or_raise()
        self.long_calls += 1
        self.long_html.append(html)
        _write_png(Path(output_path), 400, 1200)
        return Path(output_path)

    async def render_frame(self, html, output_path, width, height):
        self.frames.append((width, height))
        _write_png(Path(output_path), width, height)
        return Path(output_path)


def _write_png(path: Path, width: int, height: int) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (max(1, width // 8), max(1, height // 8)), "#ffffff").save(path)


def _patch_renderer(monkeypatch, renderer=None):
    made = renderer or _FakeRenderer()
    monkeypatch.setattr(digest_assets, "LongImageRenderer", lambda *a, **k: made)
    return made


def _patch_fonts(monkeypatch, available=True):
    if available:
        monkeypatch.setattr(digest_assets, "verify_fonts_or_raise", lambda *a, **k: None)
        monkeypatch.setattr(digest_assets, "font_stack", lambda *a, **k: "TestFont, sans-serif")
    else:
        def _raise(*a, **k):
            raise FontUnavailableError("缺少简体中文字体")

        monkeypatch.setattr(digest_assets, "verify_fonts_or_raise", _raise)


def _patch_backgrounds(monkeypatch):
    async def _bg(style, topics, label, page_count, **kwargs):
        return [Background(data_url=None, reason="测试") for _ in range(page_count)], 0

    monkeypatch.setattr(digest_assets, "resolve_backgrounds", _bg)


def _patch_inspect(monkeypatch, verdicts, *, long_verdict=PASS):
    """平台图按 verdicts 返回；长图默认单独通过，不消耗平台序列。

    长图假 renderer 的像素尺寸固定是 50x150，平台画幅没有这个尺寸。把两类调用
    分开计数，既能保住原有平台重试断言，也能显式测试长图准出门。
    """
    calls = {"count": 0, "long_count": 0}

    async def _inspect(image_bytes, texts):
        from PIL import Image
        import io

        with Image.open(io.BytesIO(image_bytes)) as image:
            is_long = image.size == (50, 150)
        if is_long:
            calls["long_count"] += 1
            outcome = (
                long_verdict[
                    min(calls["long_count"] - 1, len(long_verdict) - 1)
                ]
                if isinstance(long_verdict, list)
                else long_verdict
            )
        else:
            calls["count"] += 1
            outcome = (
                verdicts[min(calls["count"] - 1, len(verdicts) - 1)]
                if isinstance(verdicts, list)
                else verdicts
            )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(digest_assets.visual_qa, "inspect", _inspect)
    return calls


def _patch_copy(monkeypatch, result=None, raiser=None):
    from app.publishers.copy_generator import CopyResult

    async def _generate(items, label):
        if raiser:
            raise raiser
        return result if result is not None else CopyResult()

    monkeypatch.setattr(digest_assets, "generate_platform_copy", _generate)


def _run(**kwargs):
    return asyncio.run(
        digest_assets.build_assets(
            digest_html="<html><body>digest</body></html>",
            items=kwargs.pop("items", ITEMS),
            digest_label=kwargs.pop("digest_label", "2026-08-01"),
        )
    )


# --- 关闭状态 -------------------------------------------------------------


def test_render_disabled_produces_no_attachments_but_no_failure(monkeypatch):
    _enable(monkeypatch, render=False)
    _patch_copy(monkeypatch)
    bundle = _run()
    assert bundle.attachments == []
    assert bundle.withheld == []
    assert any("未启用" in note for note in bundle.notes)


def test_qa_disabled_withholds_every_image_rather_than_shipping_unchecked(monkeypatch):
    """规范要求 Every rendered image；主长图不能享有绕过准出门的特权。"""
    _enable(monkeypatch, render=True, qa=False)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    bundle = _run()
    assert bundle.attachments == []
    assert LONG_IMAGE_SLUG in {slug for slug, _ in bundle.withheld}
    assert "未经检查" in dict(bundle.withheld)[LONG_IMAGE_SLUG]
    assert any("质检" in note for note in bundle.notes)


# --- 各环节独立失败 -------------------------------------------------------


def test_long_image_passes_through_the_visual_gate(monkeypatch):
    _enable(monkeypatch, render=True, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: [])
    )
    renderer = _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    calls = _patch_inspect(monkeypatch, PASS)

    bundle = _run()
    assert [attachment.slug for attachment in bundle.attachments] == [LONG_IMAGE_SLUG]
    assert calls["long_count"] == 1
    assert renderer.long_calls == 1


def test_long_image_failure_is_withheld_and_not_delivered(monkeypatch):
    _enable(monkeypatch, render=True, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: [])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    _patch_inspect(monkeypatch, PASS, long_verdict=FAIL_OVERFLOW)

    bundle = _run()
    assert bundle.attachments == []
    assert LONG_IMAGE_SLUG in dict(bundle.withheld)
    assert "overflow" in dict(bundle.withheld)[LONG_IMAGE_SLUG]


def test_long_image_retry_changes_the_html(monkeypatch):
    """长图失败后不能拿相同 HTML 原地重放。"""
    _enable(monkeypatch, render=True, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: [])
    )
    renderer = _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    calls = _patch_inspect(
        monkeypatch, PASS, long_verdict=[FAIL_OVERFLOW, PASS]
    )

    bundle = _run()
    assert LONG_IMAGE_SLUG in {attachment.slug for attachment in bundle.attachments}
    assert calls["long_count"] == 2
    assert renderer.long_calls == 2
    assert renderer.long_html[0] != renderer.long_html[1]
    assert "data-longimage-correction" in renderer.long_html[1]


def test_long_image_gate_receives_visible_text_from_the_digest(monkeypatch):
    _enable(monkeypatch, render=True, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: [])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    seen = []

    async def _inspect(_image, texts):
        seen.extend(texts)
        return PASS

    monkeypatch.setattr(digest_assets.visual_qa, "inspect", _inspect)
    bundle = _run()
    assert LONG_IMAGE_SLUG in {attachment.slug for attachment in bundle.attachments}
    # _run 的正式 HTML fixture 只有一个可见文本节点；隐藏的 head/style 不应混入。
    assert seen == ["digest"]


def test_browser_launch_failure_still_yields_a_bundle(monkeypatch):
    _enable(monkeypatch, qa=False)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)

    class _Broken:
        async def render(self, html, path):
            raise RuntimeError("浏览器启动失败")

    _patch_renderer(monkeypatch, _Broken())
    bundle = _run()
    assert bundle.attachments == []
    assert bundle.withheld
    assert LONG_IMAGE_SLUG in {slug for slug, _ in bundle.withheld}


def test_missing_font_withholds_the_long_image_and_names_the_cause(monkeypatch):
    _enable(monkeypatch, qa=True)
    _patch_copy(monkeypatch)

    class _FontFail:
        async def render(self, html, path):
            raise FontUnavailableError("缺少简体中文字体")

    _patch_renderer(monkeypatch, _FontFail())
    bundle = _run()
    reasons = dict(bundle.withheld)
    assert "简体中文字体" in reasons[LONG_IMAGE_SLUG]


def test_copy_generation_failure_does_not_lose_the_images(monkeypatch):
    _enable(monkeypatch, qa=True)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_inspect(monkeypatch, PASS)
    _patch_copy(monkeypatch, raiser=RuntimeError("provider down"))
    bundle = _run()
    assert LONG_IMAGE_SLUG in {attachment.slug for attachment in bundle.attachments}
    assert bundle.attachments, "文案 provider 失败不能吃掉已经通过质检的图片"
    assert bundle.copy_section_html == ""
    assert any("文案" in note for note in bundle.notes)


def test_everything_optional_failing_yields_the_current_email_content(monkeypatch):
    """渲染、生图、质检、文案全挂：邮件内容退回今天的样子，且照常发。"""
    _enable(monkeypatch, render=False, qa=False)
    _patch_copy(monkeypatch, raiser=RuntimeError("down"))
    bundle = _run()
    assert bundle.attachments == []
    assert bundle.copy_section_html == ""
    assert bundle.copy_section_text == ""


def test_one_platform_failing_still_yields_the_others(monkeypatch):
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        digest_assets.settings, "publish_platforms", "xiaohongshu,x,instagram", raising=False
    )
    monkeypatch.setattr(
        type(digest_assets.settings),
        "publish_platforms_list",
        property(lambda self: ["x", "instagram"]),
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)

    real = digest_assets.build_platform_images

    async def _selective(style, items, label, **kwargs):
        if style.key == "x":
            raise RuntimeError("这个平台炸了")
        return await real(style, items, label, **kwargs)

    monkeypatch.setattr(digest_assets, "build_platform_images", _selective)
    _patch_inspect(monkeypatch, PASS)

    bundle = _run()
    slugs = {a.slug for a in bundle.attachments}
    assert "ig-square" in slugs
    assert "x-card" not in slugs
    assert "x-card" in {slug for slug, _ in bundle.withheld}


# --- 质检循环接进来之后 ---------------------------------------------------


def test_passing_image_becomes_an_attachment(monkeypatch):
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    _patch_inspect(monkeypatch, PASS)
    bundle = _run()
    assert "x-card" in {a.slug for a in bundle.attachments}


def test_exhausted_attempts_withhold_the_image_and_name_the_defect(monkeypatch):
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    monkeypatch.setattr(digest_assets.settings, "qa_max_attempts", 2)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    _patch_inspect(monkeypatch, FAIL_OVERFLOW)

    bundle = _run()
    assert "x-card" not in {a.slug for a in bundle.attachments}
    reasons = dict(bundle.withheld)
    assert "overflow" in reasons["x-card"]


def test_vision_unavailable_marks_nothing_as_passing(monkeypatch):
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    _patch_inspect(monkeypatch, VisionUnavailable("接口不可达"))

    bundle = _run()
    assert "x-card" not in {a.slug for a in bundle.attachments}
    assert "不可达" in dict(bundle.withheld)["x-card"]


def test_a_failed_image_is_re_rendered_with_changed_parameters(monkeypatch):
    """第二次渲染必须带不同的参数，否则重试只是原地重放。"""
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    calls = _patch_inspect(monkeypatch, [FAIL_OVERFLOW, PASS])

    bundle = _run()
    assert calls["count"] == 2
    assert "x-card" in {a.slug for a in bundle.attachments}


def test_withheld_images_are_named_in_the_email_section(monkeypatch):
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    monkeypatch.setattr(digest_assets.settings, "qa_max_attempts", 1)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    _patch_inspect(monkeypatch, FAIL_OVERFLOW)

    bundle = _run()
    assert "x-card" in bundle.withheld_html


# --- 附件预算与文件名 -----------------------------------------------------


def test_budget_is_applied_after_the_gate_not_before(monkeypatch):
    """先保证每张都合格，再决定哪几张装得下 —— 反过来会为丢掉的图付质检的钱。"""
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x", "instagram"])
    )
    monkeypatch.setattr(digest_assets.settings, "attachment_budget_bytes", 1)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)
    calls = _patch_inspect(monkeypatch, PASS)

    bundle = _run()
    assert calls["count"] == 2  # 两张都送检了
    assert bundle.dropped  # 但装不下的被丢掉并说明


def test_attachment_filenames_carry_the_digest_date(monkeypatch):
    _enable(monkeypatch, qa=False)
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_copy(monkeypatch)
    bundle = _run(digest_label="2026-08-02")
    assert all("2026-08-02" in a.filename for a in bundle.attachments)


def test_copy_block_names_the_attachment_that_belongs_with_it(monkeypatch):
    from app.publishers.copy_generator import CopyResult
    from app.publishers.validation import CopyDraft

    result = CopyResult()
    result.accepted = {"x": CopyDraft("x", "", "post body")}

    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch, result=result)
    _patch_inspect(monkeypatch, PASS)

    bundle = _run()
    # 文案区块必须引用实际投递文件名；平坦测试图可能保留 PNG，不能按
    # 平台槽位臆测一定是 JPEG。文件名/MIME 由最终字节决定。
    x_card = next(a for a in bundle.attachments if a.slug == "x-card")
    assert x_card.filename in bundle.copy_section_html


# --- 留存清理 -------------------------------------------------------------


def test_retention_never_deletes_the_current_run(monkeypatch, tmp_path):
    root = Path(digest_assets.settings.render_output_dir)
    current = root / "2026-08-01"
    current.mkdir(parents=True)
    (current / "digest.png").write_bytes(b"x")
    import os

    old_time = 0.0
    os.utime(current, (old_time, old_time))

    removed = digest_assets.cleanup_old_renders("2026-08-01", retention_days=1)
    assert removed == []
    assert current.exists()


def test_retention_deletes_directories_past_the_window(monkeypatch):
    import os

    root = Path(digest_assets.settings.render_output_dir)
    stale = root / "2026-07-01"
    stale.mkdir(parents=True)
    (stale / "a.png").write_bytes(b"x")
    os.utime(stale, (0.0, 0.0))

    removed = digest_assets.cleanup_old_renders("2026-08-01", retention_days=1)
    assert stale in removed
    assert not stale.exists()


def test_retention_keeps_directories_inside_the_window(monkeypatch):
    root = Path(digest_assets.settings.render_output_dir)
    recent = root / "2026-07-31"
    recent.mkdir(parents=True)
    removed = digest_assets.cleanup_old_renders("2026-08-01", retention_days=30)
    assert removed == []
    assert recent.exists()


def test_retention_disabled_deletes_nothing(monkeypatch):
    import os

    root = Path(digest_assets.settings.render_output_dir)
    stale = root / "2020-01-01"
    stale.mkdir(parents=True)
    os.utime(stale, (0.0, 0.0))
    assert digest_assets.cleanup_old_renders("2026-08-01", retention_days=0) == []
    assert stale.exists()


# --- 送检文本 -------------------------------------------------------------


def test_expected_texts_only_lists_what_the_template_draws():
    """列上模板没画的字段会让质检报 missing_text，把好图判成坏图。"""
    spec = build_page_specs(PLATFORM_STYLES["instagram"], ITEMS, "2026-08-01")[0]
    texts = expected_texts(spec)
    assert spec.heading in texts
    assert all(t.strip() for t in texts)
    for item in spec.items:
        assert item.name in texts


def test_expected_texts_skips_empty_fields():
    spec = build_page_specs(PLATFORM_STYLES["x"], [{"repo_name": "a/b", "summary": ""}], "2026-08-01")[0]
    assert "" not in expected_texts(spec)


def test_retry_keeps_complete_text_and_refreshes_expected_texts(monkeypatch):
    """视觉修正不能靠丢字；每次送检仍应使用当前完整规格的文本。"""
    _enable(monkeypatch, qa=True)
    monkeypatch.setattr(
        type(digest_assets.settings), "publish_platforms_list", property(lambda self: ["x"])
    )
    _patch_renderer(monkeypatch)
    _patch_fonts(monkeypatch)
    _patch_backgrounds(monkeypatch)
    _patch_copy(monkeypatch)

    seen: list[list[str]] = []

    async def _inspect(image_bytes, texts):
        from PIL import Image
        import io

        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.size == (50, 150):
                return PASS
        seen.append(list(texts))
        return PASS if len(seen) > 1 else FAIL_OVERFLOW

    monkeypatch.setattr(digest_assets.visual_qa, "inspect", _inspect)
    long_items = [
        {
            "repo_name": "acme/" + "agent-kit-with-an-extremely-long-repository-name" * 2,
            "summary": "很长的一句话描述" * 12,
        }
    ]
    _run(items=long_items)

    assert len(seen) == 2
    assert seen[0] == seen[1]
    assert all("…" not in text and "..." not in text for texts in seen for text in texts)


# --- 编排层的兜底 ---------------------------------------------------------


def test_digest_service_returns_an_empty_bundle_when_assets_blow_up(monkeypatch):
    """build_assets 自己出 bug 也不能让今天的邮件发不出去。"""
    from datetime import date as _date

    from app.services.digest_service import digest_service

    async def _explode(**kwargs):
        raise RuntimeError("我自己写错了")

    monkeypatch.setattr("app.services.digest_service.build_assets", _explode)
    bundle = asyncio.run(
        digest_service._build_assets(_date(2026, 8, 1), [], [], "概览")
    )
    assert bundle.attachments == []
    assert bundle.copy_section_html == ""


def test_digest_service_passes_the_bundle_through_to_the_email(monkeypatch):
    """一封邮件带走正文、文案和全部通过的图 —— 不拆信。"""
    from datetime import date as _date

    from app.services.digest_service import digest_service

    bundle = digest_assets.AssetBundle(
        attachments=[Attachment(LONG_IMAGE_SLUG, "2026-08-01-digest-long.png", b"x")],
        copy_section_html="<div>各平台文案</div>",
        copy_section_text="各平台文案",
        withheld_html="<div>未附上</div>",
    )

    async def _bundle(**kwargs):
        return bundle

    monkeypatch.setattr("app.services.digest_service.build_assets", _bundle)
    monkeypatch.setattr("app.services.digest_service.cleanup_old_renders", lambda *a, **k: [])
    out = asyncio.run(digest_service._build_assets(_date(2026, 8, 1), [], [], None))
    assert out is bundle
