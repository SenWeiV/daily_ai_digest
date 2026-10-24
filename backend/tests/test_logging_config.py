"""第三方 HTTP 日志不能泄露短期签名 URL。"""

import logging

from app.logging_config import quiet_sensitive_http_logs


def test_http_client_request_lines_are_not_logged_at_info():
    """httpx 的 INFO 请求行含完整 URL；Seedream URL 的查询串是短期凭证。"""
    targets = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    original = [logger.level for logger in targets]
    try:
        for logger in targets:
            logger.setLevel(logging.NOTSET)
        quiet_sensitive_http_logs()
        assert all(logger.level >= logging.WARNING for logger in targets)
    finally:
        for logger, level in zip(targets, original):
            logger.setLevel(level)
