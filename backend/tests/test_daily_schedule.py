"""日报定时：提前整理前一天内容，SCHEDULE_HOUR:SCHEDULE_MINUTE 准点送达。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import scheduler as scheduler_module

TZ = ZoneInfo("Asia/Shanghai")


def _settings(monkeypatch, hour, minute, lead):
    monkeypatch.setattr(scheduler_module.settings, "schedule_hour", hour)
    monkeypatch.setattr(scheduler_module.settings, "schedule_minute", minute)
    monkeypatch.setattr(scheduler_module.settings, "digest_prepare_lead_minutes", lead)


def test_prepare_starts_lead_minutes_before_delivery(monkeypatch):
    _settings(monkeypatch, 9, 0, 30)
    assert scheduler_module.daily_prepare_time() == (8, 30)


def test_prepare_time_wraps_past_midnight(monkeypatch):
    _settings(monkeypatch, 0, 10, 30)
    assert scheduler_module.daily_prepare_time() == (23, 40)


def test_send_at_is_the_same_morning_when_prepared_early(monkeypatch):
    _settings(monkeypatch, 9, 0, 30)
    send_at = scheduler_module.daily_send_at(datetime(2026, 10, 25, 8, 30, tzinfo=TZ))
    assert send_at == datetime(2026, 10, 25, 9, 0, tzinfo=TZ)


def test_late_run_sends_immediately_instead_of_waiting_a_day(monkeypatch):
    """misfire 让任务 9:20 才跑时，送达时刻是已经过去的 9:00，而不是明天 9:00。"""
    _settings(monkeypatch, 9, 0, 30)
    send_at = scheduler_module.daily_send_at(datetime(2026, 10, 25, 9, 20, tzinfo=TZ))
    assert send_at == datetime(2026, 10, 25, 9, 0, tzinfo=TZ)


def test_send_at_crosses_midnight(monkeypatch):
    _settings(monkeypatch, 0, 10, 30)
    send_at = scheduler_module.daily_send_at(datetime(2026, 10, 25, 23, 40, tzinfo=TZ))
    assert send_at == datetime(2026, 10, 26, 0, 10, tzinfo=TZ)


def test_default_delivery_is_nine_am(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SCHEDULE_HOUR", raising=False)
    monkeypatch.delenv("SCHEDULE_MINUTE", raising=False)
    settings = Settings(_env_file=None)
    assert (settings.schedule_hour, settings.schedule_minute) == (9, 0)
    assert settings.digest_prepare_lead_minutes == 30
