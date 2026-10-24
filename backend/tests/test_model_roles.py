"""三个模型角色的独立性测试

对应 add-longimage-and-publishers §2。这些测试守的是一条不能靠代码审查
守住的性质：文本模型收到图片不会报错，它会编造一个"通过"结论。所以跨能力
调用必须在构造期抛错，而不是在结果里表现为一次可疑的通过。
"""

import pytest
from pydantic import ValidationError

from pathlib import Path

from app.config import Settings
from app.model_roles import (
    Capability,
    ModelRole,
    RoleCapabilityError,
    RoleUsage,
    image_gen_role,
    require_capability,
    text_role,
    vision_role,
)


# --- 配置默认值 -----------------------------------------------------------


def test_text_role_defaults_to_deepseek():
    settings = Settings(_env_file=None)
    assert settings.text_model == "deepseek-v4-flash"
    assert settings.text_base_url == "https://api.deepseek.com"


def test_vision_role_defaults_to_kimi_k3_on_cn_endpoint():
    """必须是 .cn：北京 IP 实测 .cn 10/10 通，.ai 6/10（4 次超时）。"""
    settings = Settings(_env_file=None)
    assert settings.vision_model == "kimi-k3"
    assert settings.vision_base_url == "https://api.moonshot.cn/v1"
    assert "moonshot.ai" not in settings.vision_base_url


def test_settings_repr_masks_api_keys():
    settings = Settings(
        _env_file=None,
        TEXT_API_KEY="text-secret",
        VISION_API_KEY="vision-secret",
        IMAGE_GEN_API_KEY="image-secret",
    )
    rendered = repr(settings)
    assert "text-secret" not in rendered
    assert "vision-secret" not in rendered
    assert "image-secret" not in rendered
    assert "**********" in rendered


def test_non_moonshot_vision_endpoint_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, VISION_BASE_URL="https://api.moonshot.ai/v1")


def test_image_gen_role_defaults_to_seedream_lite_not_pro():
    """Pro 不支持组图，四张小红书图会变成四个不相干的帖子。"""
    settings = Settings(_env_file=None)
    assert settings.image_gen_model == "doubao-seedream-5-0-260128"
    assert "pro" not in settings.image_gen_model
    assert settings.image_gen_base_url == "https://ark.cn-beijing.volces.com/api/v3"


def test_watermark_defaults_to_disabled():
    """provider 默认 true 会盖"AI生成"；我们的默认必须是 false。"""
    settings = Settings(_env_file=None)
    assert settings.image_gen_watermark is False


def test_render_generation_and_qa_all_default_off():
    """三个独立故障域不能挡在"能出邮件"前面。"""
    settings = Settings(_env_file=None)
    assert settings.render_enabled is False
    assert settings.image_gen_enabled is False
    assert settings.visual_qa_enabled is False


def test_qa_and_budget_defaults():
    settings = Settings(_env_file=None)
    assert settings.qa_max_attempts == 3
    assert settings.qa_min_inspect_dimension == 900
    assert settings.qa_max_request_bytes == 60 * 1024 * 1024
    # 12MB 是实测的 163 限速拐点，不是服务商公布的上限：
    # 13MB 载荷 7.22MB/s，20MB 掉到 0.12MB/s。base64 后约 1.37 倍，
    # 12MB 原始 ≈ 16.4MB 上线，仍在快速区间。
    assert settings.attachment_budget_bytes == 12 * 1024 * 1024
    # aiosmtplib 默认 60 秒，且每次读都用它 —— 包括等整封信传完的那次读
    assert settings.smtp_timeout_seconds >= 180
    assert settings.render_retention_days == 14
    # Chromium 纹理上限 16384，配置值必须留余量
    assert settings.render_segment_max_height < 16384


def test_publish_platforms_parses_all_six():
    settings = Settings(_env_file=None)
    assert settings.publish_platforms_list == [
        "xiaohongshu",
        "wechat",
        "x",
        "instagram",
        "zhihu",
        "reddit",
    ]


# --- 角色独立解析 ---------------------------------------------------------


def test_roles_resolve_independently(monkeypatch):
    """三套 key/endpoint/model 互不影响，改一个不会串到另一个。"""
    monkeypatch.setattr("app.model_roles.settings.text_api_key", "text-key")
    monkeypatch.setattr("app.model_roles.settings.text_base_url", "https://api.deepseek.com")
    monkeypatch.setattr("app.model_roles.settings.text_model", "deepseek-v4-flash")
    monkeypatch.setattr("app.model_roles.settings.vision_api_key", "vision-key")
    monkeypatch.setattr("app.model_roles.settings.vision_base_url", "https://api.moonshot.cn/v1")
    monkeypatch.setattr("app.model_roles.settings.vision_model", "kimi-k3")
    monkeypatch.setattr("app.model_roles.settings.image_gen_api_key", "ark-key")
    monkeypatch.setattr("app.model_roles.settings.image_gen_model", "doubao-seedream-5-0-260128")

    text, vision, gen = text_role(), vision_role(), image_gen_role()

    assert {text.api_key, vision.api_key, gen.api_key} == {"text-key", "vision-key", "ark-key"}
    assert text.host == "api.deepseek.com"
    assert vision.host == "api.moonshot.cn"
    assert gen.host == "ark.cn-beijing.volces.com"
    assert text.capability is Capability.TEXT
    assert vision.capability is Capability.VISION
    assert gen.capability is Capability.IMAGE_GEN


def test_missing_credential_leaves_role_unconfigured(monkeypatch):
    """未配置视觉 key 时角色是"未配置"，不是"退回文本角色"。"""
    monkeypatch.setattr("app.model_roles.settings.vision_api_key", "")
    assert vision_role().is_configured is False


# --- 跨能力调用必须抛错 ---------------------------------------------------


def test_image_request_to_text_role_raises(monkeypatch):
    """文本模型收到图不会报错，它会编造通过结论。所以必须在这里拦。"""
    monkeypatch.setattr("app.model_roles.settings.text_api_key", "text-key")
    with pytest.raises(RoleCapabilityError):
        require_capability(text_role(), Capability.VISION)


def test_text_analysis_to_vision_role_raises(monkeypatch):
    monkeypatch.setattr("app.model_roles.settings.vision_api_key", "vision-key")
    with pytest.raises(RoleCapabilityError):
        require_capability(vision_role(), Capability.TEXT)


def test_generation_role_cannot_be_used_for_inspection(monkeypatch):
    monkeypatch.setattr("app.model_roles.settings.image_gen_api_key", "ark-key")
    with pytest.raises(RoleCapabilityError):
        require_capability(image_gen_role(), Capability.VISION)


def test_matching_capability_returns_the_role(monkeypatch):
    monkeypatch.setattr("app.model_roles.settings.vision_api_key", "vision-key")
    role = vision_role()
    assert require_capability(role, Capability.VISION) is role


def test_no_two_roles_share_a_capability(monkeypatch):
    caps = [text_role().capability, vision_role().capability, image_gen_role().capability]
    assert len(set(caps)) == 3


# --- 调用计数 -------------------------------------------------------------


def test_vision_count_tracks_images_times_attempts():
    """一张图重试两次是两次调用、两份钱。按条目数记账会把重试算丢。"""
    usage = RoleUsage()
    # 3 张图，分别 1 / 2 / 3 次尝试
    for attempts in (1, 2, 3):
        for _ in range(attempts):
            usage.record("vision")
    assert usage.snapshot()["vision"] == 6


def test_usage_counts_roles_separately():
    usage = RoleUsage()
    usage.record(ModelRole("text", Capability.TEXT, "m", "https://h", "k"), calls=10)
    usage.record("vision", calls=4)
    usage.record("image_gen", calls=5)
    snapshot = usage.snapshot()
    assert snapshot == {"text": 10, "vision": 4, "image_gen": 5}


def test_usage_summary_names_every_role_and_count():
    usage = RoleUsage()
    usage.record("text", calls=12)
    usage.record("vision", calls=7)
    summary = usage.format_summary()
    assert "text=12" in summary
    assert "vision=7" in summary


def test_usage_summary_when_nothing_was_called():
    assert "未调用" in RoleUsage().format_summary()


def test_usage_reset_clears_counts():
    usage = RoleUsage()
    usage.record("text", calls=3)
    usage.reset()
    assert usage.snapshot() == {}


# --- 结构性检查：文本调用路径不含任何图片载荷 -----------------------------


def test_text_analyzer_source_carries_no_image_payload():
    """文本角色的请求构造里不应出现图片载荷字段。

    这是源码级断言而不是行为断言，因为"把图发给文本模型"的后果不是异常，
    而是一个看起来正常的通过结论 —— 行为测试抓不到，只能在构造处禁止。
    """
    source = (Path(__file__).resolve().parents[1] / "app" / "agents" / "gemini_analyzer.py").read_text(
        encoding="utf-8"
    )
    for token in ("image_url", "input_image", "data:image/", "base64"):
        assert token not in source, f"文本分析路径出现图片载荷字段: {token}"
