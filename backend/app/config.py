"""
配置管理模块 - 从环境变量加载所有配置
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr, model_validator
from urllib.parse import urlparse


def secret_value(value: SecretStr | str) -> str:
    """Return a secret only at the HTTP/SMTP client boundary."""
    return value.get_secret_value() if isinstance(value, SecretStr) else value

# 文本角色的兜底默认值。放在类外是因为它们要在"新名为空则用旧名"的
# 回退之后才生效 —— 写成 Field(default=...) 会让默认值先于旧名生效，
# 于是老部署里的 GEMINI_BASE_URL 永远被这个默认值盖掉。
DEFAULT_TEXT_BASE_URL = "https://api.deepseek.com"
DEFAULT_TEXT_MODEL = "deepseek-v4-flash"


class Settings(BaseSettings):
    """应用配置类"""

    # 文本模型角色 (支持 DeepSeek/Kimi/通义等 OpenAI 兼容接口)
    # 默认 DeepSeek V4 Flash：国内直连，1M 上下文，成本约为 Kimi 的十分之一
    #
    # 名字从 GEMINI_* 改成 TEXT_*：这里跑的从来不是 Gemini，而"叫错名字的配置"
    # 会让运维在三个模型角色之间选错端点。
    #
    # 请求参数上没有 temperature / max_tokens：只发 model + messages，其余全用
    # provider 默认值。思考模式因此保持开启，上下文与输出长度按各家上限。
    text_api_key: SecretStr = Field(default=SecretStr(""), alias="TEXT_API_KEY")
    text_base_url: str = Field(default="", alias="TEXT_BASE_URL")
    text_model: str = Field(default="", alias="TEXT_MODEL")
    text_fallback_models: str = Field(default="", alias="TEXT_FALLBACK_MODELS")

    # 旧名保留为回退来源，不是直接删掉：服务器 .env、setup-server.sh 生成的文件、
    # 部署文档里都还是旧名。删掉会让一次部署变成"密钥为空"，而那表现为
    # 收集成功、每条分析失败 —— 邮件照常到达，只是内容变薄，在收件箱里
    # 几乎发现不了。回退方向是单向的：新名有值就用新名。
    gemini_api_key: SecretStr = Field(default=SecretStr(""), alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(default="", alias="GEMINI_BASE_URL")
    gemini_model: str = Field(default="", alias="GEMINI_MODEL")
    gemini_fallback_models: str = Field(default="", alias="GEMINI_FALLBACK_MODELS")

    @model_validator(mode="after")
    def _fill_text_role_from_legacy_names(self) -> "Settings":
        """新名为空时用旧名填，两者都空时才用内置默认值。

        判据是"空字符串"而不是"未设置"：docker-compose 用 ${VAR:-} 传变量，
        未设置的变量到容器里是空字符串而不是缺失，用 is None 判断会漏掉这种情况。
        """
        self.text_api_key = self.text_api_key or self.gemini_api_key
        self.text_base_url = self.text_base_url or self.gemini_base_url or DEFAULT_TEXT_BASE_URL
        self.text_model = self.text_model or self.gemini_model or DEFAULT_TEXT_MODEL
        self.text_fallback_models = self.text_fallback_models or self.gemini_fallback_models
        return self

    @model_validator(mode="after")
    def _validate_vision_endpoint(self) -> "Settings":
        """视觉角色只能走 Moonshot 的 HTTPS .cn 端点。"""
        parsed = urlparse(self.vision_base_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "moonshot.cn" or host.endswith(".moonshot.cn")):
            raise ValueError(
                "VISION_BASE_URL must be an HTTPS Moonshot .cn endpoint"
            )
        return self

    # GitHub API
    github_token: SecretStr = Field(default=SecretStr(""), alias="GITHUB_TOKEN")
    
    # GitHub 访问配置 (用于解决国内服务器无法访问 GitHub 的问题)
    github_proxy: str = Field(default="", alias="GITHUB_PROXY", description="代理地址，如 http://127.0.0.1:7890")
    github_mirror: str = Field(default="", alias="GITHUB_MIRROR", description="镜像地址，如 https://ghproxy.com")
    
    # YouTube API
    youtube_api_key: SecretStr = Field(default=SecretStr(""), alias="YOUTUBE_API_KEY")
    
    # 邮件服务配置（支持 Gmail / 163 / QQ 等）
    smtp_server: str = Field(default="smtp.163.com", alias="SMTP_SERVER")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_use_ssl: bool = Field(default=True, alias="SMTP_USE_SSL")
    
    # 发件人邮箱和授权码
    email_sender: str = Field(default="", alias="EMAIL_SENDER")
    email_password: SecretStr = Field(default=SecretStr(""), alias="EMAIL_PASSWORD")
    email_recipient: str = Field(default="", alias="EMAIL_RECIPIENT")
    
    # 保留旧字段兼容（向后兼容）
    gmail_sender: str = Field(default="", alias="GMAIL_SENDER")
    gmail_app_password: SecretStr = Field(default=SecretStr(""), alias="GMAIL_APP_PASSWORD")
    digest_recipient: str = Field(default="", alias="DIGEST_RECIPIENT")
    
    # 定时任务配置
    schedule_hour: int = Field(default=8, alias="SCHEDULE_HOUR")
    schedule_minute: int = Field(default=0, alias="SCHEDULE_MINUTE")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")
    
    # 应用配置
    debug: bool = Field(default=False, alias="DEBUG")
    database_path: str = Field(default="../data/digest.db", alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # API配置
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # CORS
    # 逗号分隔，例如："https://senweiv.github.io,http://localhost:3000"
    cors_allow_origins: str = Field(default="", alias="CORS_ALLOW_ORIGINS")
    
    # 搜索配置
    github_top_n: int = Field(default=10, alias="GITHUB_TOP_N", description="GitHub Trending基础数量")
    youtube_top_n: int = Field(default=10, alias="YOUTUBE_TOP_N", description="YouTube Top N 数量")
    github_candidate_limit: int = Field(default=24, alias="GITHUB_CANDIDATE_LIMIT")
    github_active_project_days: int = Field(default=14, alias="GITHUB_ACTIVE_PROJECT_DAYS")
    github_search_queries: str = Field(default="", alias="GITHUB_SEARCH_QUERIES")
    github_trending_attempt_timeout_seconds: float = Field(default=120.0, alias="GITHUB_TRENDING_ATTEMPT_TIMEOUT_SECONDS")
    github_trending_max_attempts: int = Field(default=10, alias="GITHUB_TRENDING_MAX_ATTEMPTS")
    github_social_window_days: int = Field(default=14, alias="GITHUB_SOCIAL_WINDOW_DAYS")
    github_recent_comment_limit: int = Field(default=100, alias="GITHUB_RECENT_COMMENT_LIMIT")
    github_min_recent_comments_a: int = Field(default=5, alias="GITHUB_MIN_RECENT_COMMENTS_A")
    github_activity_signal_threshold: int = Field(default=10, alias="GITHUB_ACTIVITY_SIGNAL_THRESHOLD")
    arxiv_categories: str = Field(default="cs.AI,cs.CL,cs.CV,cs.LG,cs.IR,cs.RO", alias="ARXIV_CATEGORIES")
    arxiv_candidate_limit: int = Field(default=24, alias="ARXIV_CANDIDATE_LIMIT")
    arxiv_timeout_seconds: float = Field(default=20.0, alias="ARXIV_TIMEOUT_SECONDS")
    target_items: int = Field(default=10, alias="TARGET_ITEMS")
    max_items: int = Field(default=24, alias="MAX_ITEMS")

    @property
    def arxiv_categories_list(self) -> list[str]:
        return [item.strip() for item in self.arxiv_categories.split(",") if item.strip()]

    # =======================================================================
    # 三个独立配置的模型角色（add-longimage-and-publishers）
    # 角色之间禁止互相 fallback：文本模型收到图会编造"通过"，
    # 假通过比没有结论更糟。
    # =======================================================================

    # 视觉质检角色。端点必须用 .cn：
    # 北京 IP 实测 api.moonshot.cn 10/10 通（~0.1s），api.moonshot.ai 6/10（4 次超时）。
    # 注意 .cn 与 .ai 是两个独立平台，账号、密钥、计价货币都不通用，双方文档互不提及。
    vision_api_key: SecretStr = Field(default=SecretStr(""), alias="VISION_API_KEY")
    vision_base_url: str = Field(default="https://api.moonshot.cn/v1", alias="VISION_BASE_URL")
    vision_model: str = Field(default="kimi-k3", alias="VISION_MODEL")

    # 生图角色（火山方舟 Seedream）。必须用 Lite 而非 Pro：
    # 5.0 Pro 不支持组图（sequential_image_generation），四张小红书图会像四个不相干的帖子。
    image_gen_api_key: SecretStr = Field(default=SecretStr(""), alias="IMAGE_GEN_API_KEY")
    image_gen_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3", alias="IMAGE_GEN_BASE_URL"
    )
    # 固定带日期的标识符，不用滚动别名：上游换模型会静默改变风格与成本
    image_gen_model: str = Field(default="doubao-seedream-5-0-260128", alias="IMAGE_GEN_MODEL")
    image_gen_timeout_seconds: float = Field(default=120.0, alias="IMAGE_GEN_TIMEOUT_SECONDS")
    # 按出图张数计费（¥0.22/张），所以上限是张数而不是 token
    image_gen_max_per_run: int = Field(default=5, alias="IMAGE_GEN_MAX_PER_RUN")
    # 生图背景是稳定槽位：首次缺失时生成，之后从数据卷复用，不按日报日期失效。
    image_background_cache_dir: str = Field(
        default="../data/backgrounds", alias="IMAGE_BACKGROUND_CACHE_DIR"
    )
    image_background_cache_version: str = Field(
        default="1", alias="IMAGE_BACKGROUND_CACHE_VERSION"
    )
    # 水印开关默认关闭。provider 默认是 true，会在右下角盖"AI生成"，
    # 请求里不显式带这个字段就等于交付带水印的图。
    image_gen_watermark: bool = Field(default=False, alias="IMAGE_GEN_WATERMARK")

    # =======================================================================
    # 长图渲染与质检
    # =======================================================================

    # 初次上线默认关闭：浏览器、生图、视觉三个独立故障域挡在"能出邮件"前面，
    # 邮件每天到达比图片更重要。容器内验证通过后再打开。
    render_enabled: bool = Field(default=False, alias="RENDER_ENABLED")
    image_gen_enabled: bool = Field(default=False, alias="IMAGE_GEN_ENABLED")
    visual_qa_enabled: bool = Field(default=False, alias="VISUAL_QA_ENABLED")

    render_output_dir: str = Field(default="../data/renders", alias="RENDER_OUTPUT_DIR")
    render_device_scale_factor: int = Field(default=2, alias="RENDER_DEVICE_SCALE_FACTOR")
    # Chromium 单张纹理上限 16384px，超过会静默截断。留出余量。
    render_segment_max_height: int = Field(default=15000, alias="RENDER_SEGMENT_MAX_HEIGHT")
    render_timeout_seconds: float = Field(default=120.0, alias="RENDER_TIMEOUT_SECONDS")
    render_retention_days: int = Field(default=14, alias="RENDER_RETENTION_DAYS")

    qa_max_attempts: int = Field(default=3, alias="QA_MAX_ATTEMPTS")
    # 送检请求体上限（字节）。K3 上限 100MB，留足余量。
    qa_max_request_bytes: int = Field(default=60 * 1024 * 1024, alias="QA_MAX_REQUEST_BYTES")
    # 送检副本的最小边长。低于这个值文字缺陷不再可辨，
    # 而"看不清所以没发现问题"会被报成通过——本设计里最坏的结果。
    # 到达下限仍超体积时必须分段送检，不能继续缩小。
    qa_min_inspect_dimension: int = Field(default=900, alias="QA_MIN_INSPECT_DIMENSION")
    qa_timeout_seconds: float = Field(default=300.0, alias="QA_TIMEOUT_SECONDS")

    # SMTP DATA 线上体积预算（正文预留 + MIME 头 + base64 + 折行）。超预算时
    # 先按固定顺序丢平台图；只剩长图仍超预算时也扣下长图，保证正式摘要正文可达。
    # 顺序见 app/services/attachment_budget.py 的 PLATFORM_DROP_ORDER。
    #
    # 12MB 不是服务商公布的上限，是实测出来的**限速拐点**。向 smtp.163.com
    # 逐级加大 DATA 载荷（不发终止符，所以那些信都被丢弃）量到：
    #   13MB → 7.22MB/s    20MB → 0.12MB/s    26MB → 0.19MB/s    35MB → 0.10MB/s
    # 163 不拒收大信，它限速，且落差是两个数量级。预算直接按 SMTP 线上字节判定，
    # 避免把 12MB 原始附件误当成 12MB DATA。
    attachment_budget_bytes: int = Field(default=12 * 1024 * 1024, alias="ATTACHMENT_BUDGET_BYTES")

    # SMTP 读超时（秒）。aiosmtplib 的默认值是 60 秒，且**每次读都用它** ——
    # 包括 DATA 命令那一次读，而那一次要等整封信上传完。带图的信在限速下
    # 远超 60 秒，于是表现为 SMTPReadTimeoutError，看起来像网络故障。
    # 300 秒是按最坏情况给的余量：预算内的载荷实测几秒钟就传完，这个值只在
    # 服务商开始限速时才起作用。
    smtp_timeout_seconds: float = Field(default=300.0, alias="SMTP_TIMEOUT_SECONDS")

    # 各平台文案开关。关闭的平台不产出文案，且不算作失败。
    publish_platforms: str = Field(
        default="xiaohongshu,wechat,x,instagram,zhihu,reddit", alias="PUBLISH_PLATFORMS"
    )
    publishers_enabled: bool = Field(default=False, alias="PUBLISHERS_ENABLED")

    @property
    def publish_platforms_list(self) -> list[str]:
        return [item.strip() for item in self.publish_platforms.split(",") if item.strip()]

    # 搜索关键词 - 聚焦 AI Agent/AGI/LLM 领域
    ai_keywords: list[str] = Field(
        default=[
            "AI agent",
            "LLM agent",
            "AGI",
            "autonomous agent",
            "multi-agent system",
            "agentic AI",
            "AI coding assistant",
            "reasoning AI",
            "GPT-4 GPT-5",
            "Claude Anthropic"
        ],
        description="AI/AGI/AI Agent 相关搜索关键词"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        # 允许按字段名赋值：测试里要能 Settings(text_model=...)，
        # 只有别名可用时那种构造会失败。
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 便捷访问
settings = get_settings()
