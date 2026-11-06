"""Immutable game configuration and business-date calculation."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class GameConfig:
    timezone_name: str = "Asia/Shanghai"
    initial_stars: int = 3
    daily_dungeon_threshold: int = 3
    dungeon_duration_hours: int = 8
    free_daily_pardon_count: int = 1
    paid_pardon_cost: int = 20
    expulsion_progress_penalty_seconds: int = 300
    absence_progress_penalty_seconds: int = 1800
    honor_threshold_hours: tuple[int, ...] = (0, 1, 10, 50, 100, 300, 600, 1000)

    def __post_init__(self) -> None:
        if not self.timezone_name.strip():
            raise ValueError("timezone_name must not be empty")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone_name: {self.timezone_name}") from exc

        _require_integer(self.initial_stars, "initial_stars")
        if self.initial_stars < 1:
            raise ValueError("initial_stars must be at least 1")

        _require_integer(self.daily_dungeon_threshold, "daily_dungeon_threshold")
        _require_non_negative(self.daily_dungeon_threshold, "daily_dungeon_threshold")
        _require_integer(self.dungeon_duration_hours, "dungeon_duration_hours")
        if self.dungeon_duration_hours <= 0:
            raise ValueError("dungeon_duration_hours must be positive")
        _require_integer(self.free_daily_pardon_count, "free_daily_pardon_count")
        _require_non_negative(self.free_daily_pardon_count, "free_daily_pardon_count")
        _require_integer(self.paid_pardon_cost, "paid_pardon_cost")
        _require_non_negative(self.paid_pardon_cost, "paid_pardon_cost")
        _require_integer(
            self.expulsion_progress_penalty_seconds,
            "expulsion_progress_penalty_seconds",
        )
        _require_non_negative(
            self.expulsion_progress_penalty_seconds,
            "expulsion_progress_penalty_seconds",
        )
        _require_integer(
            self.absence_progress_penalty_seconds,
            "absence_progress_penalty_seconds",
        )
        _require_non_negative(
            self.absence_progress_penalty_seconds,
            "absence_progress_penalty_seconds",
        )

        if not isinstance(self.honor_threshold_hours, tuple):
            raise TypeError("honor_threshold_hours must be a tuple of integers")
        for threshold in self.honor_threshold_hours:
            _require_integer(threshold, "honor_threshold_hours")
            _require_non_negative(threshold, "honor_threshold_hours")
        if any(
            left >= right
            for left, right in zip(
                self.honor_threshold_hours,
                self.honor_threshold_hours[1:],
                strict=False,
            )
        ):
            raise ValueError("honor_threshold_hours must be strictly increasing")

    def business_date(self, instant: datetime) -> date:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("instant must be timezone-aware")
        return instant.astimezone(ZoneInfo(self.timezone_name)).date()


def _require_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
