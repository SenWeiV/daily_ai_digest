"""Protect public API operations that change state or incur provider costs."""

import secrets
from fastapi import Header, HTTPException
from app.config import secret_value, settings


def require_admin(authorization: str = Header(default="")) -> None:
    expected = secret_value(settings.admin_api_key)
    if not expected:
        raise HTTPException(status_code=503, detail="管理操作未启用，请配置 ADMIN_API_KEY")
    if not authorization.startswith("Bearer ") or not secrets.compare_digest(authorization[7:].encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="需要有效的管理员密钥")
