"""日志安全配置。

第三方 HTTP 客户端的 INFO 日志不适合服务端长期保留。httpx 会把完整请求 URL
写成：

    HTTP Request: GET https://...?...X-Tos-Credential=...&X-Tos-Signature=...

Seedream 返回的下载 URL 24 小时有效，查询串本身就是短期访问凭证。它不是永久
API key，但在有效期内拿到日志的人可以下载图片，所以同样不能落日志。

业务层已经记录了安全且足够的状态：provider、模型、目标尺寸、HTTP 异常类型和
最终成功/失败。把 httpx/httpcore 降到 WARNING 不会丢掉这些证据，只会去掉
原始请求行（也避免 Authorization/URL 在未来库版本改变日志格式后被带出来）。
"""

from __future__ import annotations

import logging


def quiet_sensitive_http_logs() -> None:
    """禁止第三方 HTTP 客户端在 INFO 级别记录完整请求 URL。"""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
