"""Business-timezone periods shared by discovery sources."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo


def source_datetime(value: datetime | str | None) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = parsedate_to_datetime(value)
        return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class ContentWindow:
    start: datetime
    end: datetime

    def contains(self, value: datetime | str | None) -> bool:
        parsed = source_datetime(value)
        return parsed is not None and self.start <= parsed < self.end

    @property
    def github_range(self) -> str:
        def iso(value: datetime) -> str:
            return value.isoformat(timespec="seconds").replace("+00:00", "Z")
        return f"{iso(self.start)}..{iso(self.end - timedelta(seconds=1))}"

    @property
    def arxiv_range(self) -> str:
        return f"[{self.start:%Y%m%d%H%M} TO {self.end - timedelta(minutes=1):%Y%m%d%H%M}]"


def content_window(digest_type: str, target: date, timezone_name: str) -> ContentWindow:
    if digest_type not in {"daily", "weekly", "monthly"}:
        raise ValueError("digest_type must be daily, weekly, or monthly")
    first = target
    if digest_type == "weekly":
        first -= timedelta(days=first.weekday())
    elif digest_type == "monthly":
        first = first.replace(day=1)
    tz = ZoneInfo(timezone_name)
    return ContentWindow(
        datetime.combine(first, time.min, tz).astimezone(timezone.utc),
        datetime.combine(target + timedelta(days=1), time.min, tz).astimezone(timezone.utc),
    )
