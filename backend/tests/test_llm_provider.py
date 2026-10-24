"""LLM provider 配置与请求路径的测试

覆盖 switch-llm-to-deepseek-v4 的 llm-provider-configuration 能力：
默认指向 DeepSeek、端点构建、请求体只带必需字段、思考模式响应解析。
"""

import asyncio

import httpx
import pytest

from app.config import Settings
from app.agents.gemini_analyzer import GeminiAnalyzer


def _analyzer(monkeypatch, *, base_url="https://api.deepseek.com", model="deepseek-v4-flash",
              fallbacks="") -> GeminiAnalyzer:
    """构造一个已配置 key 的分析器，不触碰真实网络"""
    monkeypatch.setattr("app.agents.gemini_analyzer.settings.text_api_key", "test-key")
    monkeypatch.setattr("app.agents.gemini_analyzer.settings.text_base_url", base_url)
    monkeypatch.setattr("app.agents.gemini_analyzer.settings.text_model", model)
    monkeypatch.setattr("app.agents.gemini_analyzer.settings.text_fallback_models", fallbacks)
    return GeminiAnalyzer()


class _Recorder:
    """替换 httpx.AsyncClient，记录请求并返回构造好的响应"""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.url = None
        self.body = None
        self.headers = None

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.url = url
        self.headers = headers
        self.body = json
        request = httpx.Request("POST", url)
        return httpx.Response(self.status_code, json=self.payload, request=request)


def _install(monkeypatch, recorder):
    monkeypatch.setattr("app.agents.gemini_analyzer.httpx.AsyncClient", recorder)


# --- 配置默认值 -----------------------------------------------------------

def test_defaults_target_deepseek(monkeypatch):
    for name in ("TEXT_MODEL", "TEXT_BASE_URL", "GEMINI_MODEL", "GEMINI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.text_model == "deepseek-v4-flash"
    assert settings.text_base_url == "https://api.deepseek.com"
    assert settings.text_fallback_models == ""


def test_operator_override_is_used_verbatim(monkeypatch):
    monkeypatch.setenv("TEXT_MODEL", "kimi-k2.5")
    monkeypatch.setenv("TEXT_BASE_URL", "https://api.moonshot.cn/v1")
    settings = Settings(_env_file=None)

    assert settings.text_model == "kimi-k2.5"
    assert settings.text_base_url == "https://api.moonshot.cn/v1"


def test_legacy_gemini_names_still_resolve(monkeypatch):
    """服务器 .env 里还是旧名。删掉旧名会让一次部署静默退化成"密钥为空"。"""
    for name in ("TEXT_API_KEY", "TEXT_MODEL", "TEXT_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-key")
    monkeypatch.setenv("GEMINI_MODEL", "legacy-model")
    settings = Settings(_env_file=None)

    assert settings.text_api_key.get_secret_value() == "legacy-key"
    assert settings.text_model == "legacy-model"


def test_new_name_wins_over_the_legacy_one(monkeypatch):
    """两个名字同时存在时不能靠运气决定用哪个。"""
    monkeypatch.setenv("GEMINI_MODEL", "legacy-model")
    monkeypatch.setenv("TEXT_MODEL", "new-model")
    assert Settings(_env_file=None).text_model == "new-model"


def test_empty_fallback_list_yields_single_model(monkeypatch):
    analyzer = _analyzer(monkeypatch, fallbacks="")
    assert analyzer.model_names == ["deepseek-v4-flash"]


# --- 端点构建 -------------------------------------------------------------

@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com/v1/",
    ],
)
def test_endpoint_resolves_to_single_chat_completions(monkeypatch, base_url):
    analyzer = _analyzer(monkeypatch, base_url=base_url)
    endpoint = analyzer._resolve_endpoint()

    assert endpoint == "https://api.deepseek.com/v1/chat/completions"
    assert "//chat" not in endpoint
    assert endpoint.count("/v1") == 1


def test_endpoint_preserves_non_v1_vendor_path(monkeypatch):
    analyzer = _analyzer(
        monkeypatch, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert (
        analyzer._resolve_endpoint()
        == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )


# --- 请求参数 -------------------------------------------------------------

def test_request_carries_only_model_and_messages(monkeypatch):
    """不带 temperature / max_tokens。

    这两个字段一旦写死就是用我们猜的常量覆盖 provider 默认值：max_tokens 会在长
    README 上截断答案（截断的 JSON 解析失败，最终落成"分析为空"），temperature
    在部分模型上直接被拒（K3 只接受 1）。默认值同时保持思考模式开启。
    """
    recorder = _Recorder({"choices": [{"message": {"content": "ok"}}]})
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert set(recorder.body) == {"model", "messages"}
    assert recorder.body["model"] == "deepseek-v4-flash"


def test_no_output_length_cap_is_imposed(monkeypatch):
    recorder = _Recorder({"choices": [{"message": {"content": "ok"}}]})
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert "max_tokens" not in recorder.body
    assert "max_completion_tokens" not in recorder.body


# --- 思考模式响应解析 ------------------------------------------------------

def test_reasoning_and_content_returns_only_content(monkeypatch):
    recorder = _Recorder(
        {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "先考虑 A 再考虑 B，因此……",
                        "content": '{"summary": "答案"}',
                    }
                }
            ]
        }
    )
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    result = asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert result == '{"summary": "答案"}'
    assert "先考虑" not in result


def test_reasoning_with_empty_content_raises(monkeypatch):
    recorder = _Recorder(
        {
            "choices": [
                {"message": {"reasoning_content": "很长的推理链", "content": ""}}
            ]
        }
    )
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    # 推理链绝不能被当成答案返回
    assert "很长的推理链" not in str(excinfo.value)


def test_structured_part_list_is_joined(monkeypatch):
    recorder = _Recorder(
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "第一段"},
                            {"type": "text", "text": "第二段"},
                        ]
                    }
                }
            ]
        }
    )
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    result = asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert result == "第一段\n第二段"


def test_null_content_without_reasoning_returns_empty(monkeypatch):
    recorder = _Recorder({"choices": [{"message": {"content": None}}]})
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    result = asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert result == ""


# --- 凭据错误可见 ---------------------------------------------------------

def test_authentication_error_raises_with_provider_status(monkeypatch, caplog):
    recorder = _Recorder(
        {"error": {"message": "Authentication Fails", "type": "authentication_error"}},
        status_code=401,
    )
    _install(monkeypatch, recorder)
    analyzer = _analyzer(monkeypatch)

    with caplog.at_level("ERROR"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(analyzer._generate_with_openai_compatible("prompt", "deepseek-v4-flash"))

    assert any("401" in record.message for record in caplog.records)


# --- 启动日志 -------------------------------------------------------------

def test_startup_log_names_model_and_host(monkeypatch, caplog):
    with caplog.at_level("INFO"):
        _analyzer(monkeypatch)

    logged = "\n".join(record.message for record in caplog.records)
    assert "deepseek-v4-flash" in logged
    assert "api.deepseek.com" in logged
