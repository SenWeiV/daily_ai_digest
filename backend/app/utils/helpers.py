"""
工具函数
"""

import re
from datetime import datetime, date, timedelta
from typing import Optional


def get_yesterday() -> date:
    """获取昨天的日期"""
    return date.today() - timedelta(days=1)


def get_today() -> date:
    """获取今天的日期"""
    return date.today()


def format_number(num: int) -> str:
    """格式化数字显示 (如 1234 -> 1.2K)"""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def format_duration(seconds: int) -> str:
    """格式化时长 (如 3661 -> 1:01:01)"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_iso8601_duration(duration: str) -> int:
    """解析ISO 8601时长格式 (如 PT1H30M45S -> 5445秒)"""
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, duration)
    if not match:
        return 0
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    
    return hours * 3600 + minutes * 60 + seconds


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """截断文本"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def clean_text(text: str) -> str:
    """清理文本中的特殊字符"""
    if not text:
        return ""
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text)
    # 移除控制字符
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    return text.strip()


def extract_repo_name(url: str) -> Optional[str]:
    """从GitHub URL提取仓库名"""
    pattern = r'github\.com/([^/]+/[^/]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def generate_date_range_query(days_ago: int = 1) -> str:
    """生成GitHub日期范围查询字符串"""
    target_date = date.today() - timedelta(days=days_ago)
    return f"pushed:>={target_date.isoformat()}"


def safe_get(data: dict, *keys, default=None):
    """安全获取嵌套字典值"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result if result is not None else default