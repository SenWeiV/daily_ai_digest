"""字体自检的测试

对应 add-longimage-and-publishers §3。核心断言只有一条：缺字体时必须响亮地
失败，并且在那个状态下不去渲染。因为缺字体的自然行为是静默画方框 ——
没有异常、没有警告、只有成品图里的豆腐块。
"""

import pytest

from app.services import font_check
from app.services.font_check import (
    FontReport,
    FontUnavailableError,
    font_stack,
    inspect_fonts,
    verify_fonts_or_raise,
)


def _report(cjk=("Noto Sans CJK SC",), emoji=("Noto Color Emoji",), available=True) -> FontReport:
    return FontReport(cjk_families=tuple(cjk), emoji_families=tuple(emoji), fontconfig_available=available)


# --- 缺字体必须失败 -------------------------------------------------------


def test_missing_cjk_font_raises():
    with pytest.raises(FontUnavailableError) as exc:
        verify_fonts_or_raise(_report(cjk=()))
    assert "简体中文" in str(exc.value)


def test_missing_emoji_font_raises():
    with pytest.raises(FontUnavailableError) as exc:
        verify_fonts_or_raise(_report(emoji=()))
    assert "emoji" in str(exc.value)


def test_missing_both_names_both_gaps():
    with pytest.raises(FontUnavailableError) as exc:
        verify_fonts_or_raise(_report(cjk=(), emoji=()))
    message = str(exc.value)
    assert "简体中文" in message and "emoji" in message


def test_no_fontconfig_raises_rather_than_assuming_ok():
    """无法确认不等于确认没问题。未经确认不渲染。"""
    with pytest.raises(FontUnavailableError):
        verify_fonts_or_raise(_report(available=False))


def test_complete_fonts_pass_and_report_families(caplog):
    with caplog.at_level("INFO"):
        report = verify_fonts_or_raise(_report(cjk=("Noto Sans CJK SC",), emoji=("Noto Color Emoji",)))
    assert report.is_complete
    assert "Noto Sans CJK SC" in caplog.text
    assert "Noto Color Emoji" in caplog.text


def test_renderer_does_not_render_when_fonts_are_missing(monkeypatch):
    """在缺字体状态下渲染入口必须直接抛错，不进入浏览器启动。"""
    from app.services import image_renderer

    monkeypatch.setattr(image_renderer, "inspect_fonts", lambda: _report(cjk=()))

    launched = {"called": False}

    def _fail_launch(*args, **kwargs):
        launched["called"] = True
        raise AssertionError("字体缺失时不应尝试启动浏览器")

    monkeypatch.setattr(image_renderer, "_launch_browser", _fail_launch, raising=False)

    with pytest.raises(FontUnavailableError):
        image_renderer.preflight()
    assert launched["called"] is False


# --- 逐字符回退 -----------------------------------------------------------


def test_font_stack_includes_both_cjk_and_emoji():
    """两类字体必须同时在栈里：只写中文族时 emoji 落到默认族上变方框。"""
    stack = font_stack(_report())
    assert "Noto Sans CJK SC" in stack
    assert "Noto Color Emoji" in stack


def test_emoji_family_precedes_generic_sans():
    """sans-serif 会匹配任何字符，排它后面的族永远轮不到。"""
    stack = font_stack(_report())
    assert stack.index("Noto Color Emoji") < stack.index("sans-serif")


def test_font_stack_quotes_multiword_families():
    stack = font_stack(_report())
    assert "'Noto Sans CJK SC'" in stack


def test_font_stack_has_no_duplicates():
    stack = font_stack(_report(cjk=("Arial",), emoji=("Arial",)))
    names = [part.strip() for part in stack.split(",")]
    assert len(names) == len(set(names))


def test_font_stack_falls_back_to_generic_names_without_fontconfig():
    """本地开发（无 fontconfig）仍要产出可用的栈，只是不做存在性保证。"""
    stack = font_stack(_report(cjk=(), emoji=(), available=False))
    assert "Noto Sans CJK SC" in stack or "PingFang SC" in stack
    assert "Noto Color Emoji" in stack or "Apple Color Emoji" in stack


# --- 存在性判断方式 -------------------------------------------------------


def test_inspect_uses_fc_list_not_fc_match(monkeypatch):
    """fc-match 永远返回一个结果，用它判断存在性会得到假通过。"""
    source = (font_check.__file__)
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "fc-list" in text
    assert 'which("fc-match")' not in text


def test_inspect_reports_unavailable_when_fc_list_missing(monkeypatch):
    monkeypatch.setattr(font_check.shutil, "which", lambda name: None)
    report = inspect_fonts()
    assert report.fontconfig_available is False
    assert report.has_cjk is False


def test_inspect_parses_family_names_from_fc_list(monkeypatch):
    class _Result:
        stdout = "Noto Sans CJK SC,思源黑体\nNoto Sans CJK SC,思源黑体\nNoto Serif CJK SC\n"

    monkeypatch.setattr(font_check.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(font_check.subprocess, "run", lambda *a, **k: _Result())
    report = inspect_fonts()
    assert report.cjk_families == ("Noto Sans CJK SC", "Noto Serif CJK SC")


# --- 简体中文族的优先级 ---------------------------------------------------
#
# 这一组的动机来自容器里的实测：fonts-noto-cjk 一个包装出 15 个匹配
# :lang=zh-cn 的族，fc-list 交回来的前三个是 Noto Serif CJK JP / KR / HK，
# 于是简体正文会用日文字形变体渲染。每个字都有字形，所以豆腐块检测放它过去，
# 视觉质检也大概率报通过 —— 缺陷只表现为"字看着有点怪"。


def test_simplified_chinese_family_wins_over_japanese_variant():
    """SC 必须排在 JP/KR 之前。直、骨、込 在两者里是不同字形（已逐像素证实）。"""
    report = _report(cjk=("Noto Serif CJK JP", "Noto Serif CJK KR", "Noto Sans CJK SC"))
    assert report.cjk_families[0] == "Noto Sans CJK SC"


def test_sans_wins_over_serif_for_the_same_language():
    """正文用无衬线。同为 SC 时 Sans 优先于 Serif。"""
    report = _report(cjk=("Noto Serif CJK SC", "Noto Sans CJK SC"))
    assert report.cjk_families[0] == "Noto Sans CJK SC"


def test_mono_family_is_ranked_last():
    """等宽族排最后：用等宽渲染整段正文会撑破排版宽度。"""
    report = _report(cjk=("Noto Sans Mono CJK SC", "Noto Serif CJK SC"))
    assert report.cjk_families[-1] == "Noto Sans Mono CJK SC"


def test_ordering_is_applied_to_what_fc_list_returns(monkeypatch):
    """排序必须发生在 inspect_fonts 里，而不是只在测试构造的 report 上成立。"""

    class _Result:
        # 容器里实测的真实顺序：JP 在最前面
        stdout = (
            "Noto Serif CJK JP\nNoto Serif CJK KR\nNoto Serif CJK HK\n"
            "Noto Sans CJK SC\nNoto Sans Mono CJK SC\n"
        )

    monkeypatch.setattr(font_check.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(font_check.subprocess, "run", lambda *a, **k: _Result())
    report = inspect_fonts()
    assert report.cjk_families[0] == "Noto Sans CJK SC"
    assert font_stack(report).index("Noto Sans CJK SC") < font_stack(report).index("CJK JP")


def test_unrecognized_family_names_still_survive_ordering():
    """认不出语言标记的族名不能被丢掉 —— 它可能是系统上唯一的中文字体。"""
    report = _report(cjk=("WenQuanYi Zen Hei",))
    assert report.cjk_families == ("WenQuanYi Zen Hei",)
    assert "WenQuanYi Zen Hei" in font_stack(report)
