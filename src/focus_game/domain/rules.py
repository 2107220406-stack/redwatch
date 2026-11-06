"""Pure deterministic rules for focus sessions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .enums import ObservationVerdict, ViolationType, WorkStage


def honor_level_for_seconds(seconds: int, thresholds: tuple[int, ...]) -> int:
    hours = seconds / 3600
    level = 1
    for index, threshold in enumerate(thresholds, start=1):
        if hours >= threshold:
            level = index
        else:
            break
    return level


def protected_progress_seconds(honor_level: int, thresholds: tuple[int, ...]) -> int:
    if honor_level < 1 or honor_level > len(thresholds):
        raise ValueError("honor_level is outside configured thresholds")
    return thresholds[honor_level - 1] * 3600


def apply_progress_penalty(current: int, penalty: int, protected_floor: int) -> int:
    if min(current, penalty, protected_floor) < 0:
        raise ValueError("progress values must be non-negative")
    return max(protected_floor, current - penalty)


def should_confirm_violation(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    min_confidence: float = 0.85,
) -> bool:
    if previous is None or not 0 <= min_confidence <= 1:
        return False
    if previous.get("verdict") != ObservationVerdict.SUSPECTED_VIOLATION.value:
        return False
    if current.get("verdict") != ObservationVerdict.SUSPECTED_VIOLATION.value:
        return False
    previous_type = previous.get("violation_type")
    current_type = current.get("violation_type")
    if not previous_type or previous_type != current_type:
        return False
    if previous.get("stage") not in (None, WorkStage.WORKING.value):
        return False
    if current.get("stage") not in (None, WorkStage.WORKING.value):
        return False
    return all(float(item.get("confidence", 0)) >= min_confidence for item in (previous, current))


def dungeon_until(now: datetime, duration_hours: int) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if duration_hours <= 0:
        raise ValueError("duration_hours must be positive")
    return now + timedelta(hours=duration_hours)


def observation_is_usable(observation: dict[str, Any]) -> bool:
    verdict = observation.get("verdict")
    if verdict == ObservationVerdict.UNKNOWN.value:
        return False
    if observation.get("stage") == WorkStage.RESTING.value:
        return False
    confidence = float(observation.get("confidence", 0))
    return (
        verdict
        in {
            ObservationVerdict.COMPLIANT.value,
            ObservationVerdict.SUSPECTED_VIOLATION.value,
        }
        and 0 <= confidence <= 1
    )


def violation_type(value: Any) -> ViolationType | None:
    try:
        return ViolationType(value) if value is not None else None
    except ValueError:
        return None
