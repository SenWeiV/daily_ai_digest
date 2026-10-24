"""三个模型角色的声明与调用计数。

角色之间禁止互相 fallback，这不是风格问题：文本模型收到图片时不会报错，
它会编造一个像样的"通过"结论。假通过会把本该被拦下的缺陷直接发出去，
比没有质检更糟。所以能力（capability）是角色的一等字段，
发请求前必须过 `require_capability()`，跨能力使用在构造期就抛错。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from urllib.parse import urlparse

from app.config import secret_value, settings

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """角色能做什么。不是标签，是发请求前的准入条件。"""

    TEXT = "text"
    VISION = "vision"
    IMAGE_GEN = "image_gen"


class RoleCapabilityError(RuntimeError):
    """把请求发给了能力不匹配的角色。"""


@dataclass(frozen=True)
class ModelRole:
    name: str
    capability: Capability
    model: str
    base_url: str
    api_key: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or self.base_url


def text_role() -> ModelRole:
    """纯文本分析与文案生成。默认 DeepSeek V4 Flash。"""
    return ModelRole(
        name="text",
        capability=Capability.TEXT,
        model=settings.text_model,
        base_url=settings.text_base_url.rstrip("/"),
        api_key=secret_value(settings.text_api_key),
    )


def vision_role() -> ModelRole:
    """看图质检。默认 kimi-k3，端点必须是 .cn。"""
    return ModelRole(
        name="vision",
        capability=Capability.VISION,
        model=settings.vision_model,
        base_url=settings.vision_base_url.rstrip("/"),
        api_key=secret_value(settings.vision_api_key),
    )


def image_gen_role() -> ModelRole:
    """生图。默认 Seedream 5.0 Lite（Pro 不支持组图）。"""
    return ModelRole(
        name="image_gen",
        capability=Capability.IMAGE_GEN,
        model=settings.image_gen_model,
        base_url=settings.image_gen_base_url.rstrip("/"),
        api_key=secret_value(settings.image_gen_api_key),
    )


def require_capability(role: ModelRole, capability: Capability) -> ModelRole:
    """能力不匹配就抛错，绝不"退而求其次"地照发。"""
    if role.capability is not capability:
        raise RoleCapabilityError(
            f"角色 {role.name}（能力 {role.capability.value}）不能承担 "
            f"{capability.value} 请求：跨能力调用会得到编造的结论而不是错误"
        )
    return role


class RoleUsage:
    """按角色累计调用次数。

    视觉角色按"图片数 × 尝试次数"计数，不是条目数：一张图重试两次就是两次
    调用，成本也是两次。用条目数记账会把重试的钱算丢。
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._calls: dict[str, int] = {}

    def record(self, role: ModelRole | str, calls: int = 1) -> None:
        name = role if isinstance(role, str) else role.name
        with self._lock:
            self._calls[name] = self._calls.get(name, 0) + calls

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._calls)

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()

    def format_summary(self) -> str:
        counts = self.snapshot()
        if not counts:
            return "本次运行未调用任何模型角色"
        parts = [f"{name}={counts[name]}" for name in sorted(counts)]
        return "模型角色调用次数 | " + " | ".join(parts)

    def log_summary(self) -> None:
        logger.info(self.format_summary())


# 全局实例：一次 digest 运行开始时 reset，结束时 log_summary
role_usage = RoleUsage()
