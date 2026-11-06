"""Small immutable domain value models shared by commands and services."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .enums import WorkStage


@dataclass(frozen=True)
class PatrolObservation:
    """A server-addressed observation captured during a session stage."""

    observation_id: str
    captured_at: datetime
    stage: WorkStage
    observation: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_non_empty_id(self.observation_id, "observation_id")
        require_aware_datetime(self.captured_at, "captured_at")
        if not isinstance(self.stage, WorkStage):
            try:
                object.__setattr__(self, "stage", WorkStage(self.stage))
            except (TypeError, ValueError) as exc:
                raise ValueError("stage must be a valid WorkStage") from exc
        if not isinstance(self.observation, Mapping):
            raise TypeError("observation must be a mapping")
        object.__setattr__(self, "observation", dict(self.observation))


def require_non_empty_id(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def require_non_negative_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
